"""Telegram bot webhook.

Telegram delivers updates here via setWebhook (a one-time prod action). The
request is authenticated with the secret token Telegram echoes back in the
`X-Telegram-Bot-Api-Secret-Token` header (validated against TG_WEBHOOK_SECRET
when that env is set).

The webhook only keeps the update and wakes the bot's worker, which handles it
in the background (see services/telegram_updates.py). So it answers at once —
Telegram never waits on the bot, nor the rest of the API on Telegram. The one
exception is a checkout: it is answered right here.
"""
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlmodel import Session

from app.bot_worker import update_worker
from app.database import get_session
from app.dependencies import unsigned_init_data_allowed
from app.services.bot_updates import BotUpdates, is_payment
from app.services.telegram_updates import TelegramUpdateQueue

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)


@router.post("/webhook")
def telegram_webhook(
    update: dict = Body(...),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    secret = os.getenv("TG_WEBHOOK_SECRET")
    if secret and x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    if not secret and not unsigned_init_data_allowed():
        # Without it, anyone could post an update as any user and the bot
        # would act for them. Loud, so a deploy missing it shows at once.
        logger.error("Refusing a Telegram update: TG_WEBHOOK_SECRET is not set")
        raise HTTPException(status_code=503, detail="Webhook secret is not configured")

    if is_payment(update) and not secret:
        # Pro is granted on the word of this endpoint alone, so without the
        # secret anyone could claim a payment. Unanswered, the checkout times
        # out and nobody is charged.
        logger.error("Ignoring a payment update: TG_WEBHOOK_SECRET is not set")
        return {"ok": True}

    if "pre_checkout_query" in update:
        # Telegram calls the payment off unless this is answered within ten
        # seconds, so it does not wait its turn behind the bot's other work:
        # it is one quick call, in order with nothing.
        try:
            BotUpdates(session).handle(update)
        except Exception:  # noqa: BLE001 — unanswered, the payment is called off and nobody is charged
            logger.exception("Could not answer a checkout")
        return {"ok": True}

    # Not caught: an update we failed to keep must come again, and Telegram
    # resends what is not answered 200.
    if TelegramUpdateQueue(session).accept(update, datetime.utcnow()):
        update_worker.wake()
    return {"ok": True}
