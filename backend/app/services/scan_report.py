"""Telling a chat that its receipt has been read.

The Mini App watches a bill over SSE and needs no message. A chat has nothing
to watch, so a scan started there has to end with an answer: the receipt back
as a photo, with the items, the total and whoever has joined so far.
"""
import logging
import os

from sqlmodel import Session

from app.models import Bill, ReceiptTask
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.services.bill_core_service import BillCoreService
from app.services.receipt_service import STORAGE_DIR
from app.utils.bill_card import invite_button, open_bill_button, render_bill_card
from app.utils.bot_copy import resolve_language
from app.utils.telegram import send_message, send_photo

logger = logging.getLogger(__name__)

# Telegram caps a photo caption at 1024 characters. A card longer than that
# travels as its own message under a bare photo rather than being cut off.
MAX_CAPTION = 1024


def report_scan(session: Session, task: ReceiptTask, bill: Bill) -> None:
    """No-op unless the scan came from a chat that is waiting on it."""
    if not task.notify_chat_id:
        return

    try:
        bill_repo = BillRepository(session)
        user_repo = UserRepository(session)
        owner = user_repo.get_by_id(bill.owner_id)
        language = resolve_language((owner.settings or {}).get("language") if owner else None)

        detail = BillCoreService(bill_repo, user_repo).get_bill_details(
            bill.id, requester_id=bill.owner_id
        )
        card = render_bill_card(detail, language)
        keyboard = {"inline_keyboard": [
            [invite_button(bill.public_token, language)],
            [open_bill_button(bill.public_token, language)],
        ]}

        _deliver(task.notify_chat_id, task.filename, card, keyboard)
    except Exception:
        # The bill is correct either way; a message that failed to send must not
        # roll the scan back or stop the worker taking the next task.
        logger.exception("Could not report scan %s to chat %s", task.id, task.notify_chat_id)


def _deliver(chat_id: int, filename: str | None, card: str, keyboard: dict) -> None:
    path = os.path.join(STORAGE_DIR, filename) if filename else None
    # QR imports have no image, and a photo Telegram won't take should still
    # leave the user with the card.
    if path and os.path.exists(path) and len(card) <= MAX_CAPTION:
        try:
            send_photo(chat_id, photo_path=path, caption=card, reply_markup=keyboard)
            return
        except RuntimeError as e:
            logger.warning("Scan report photo failed, sending text: %s", e)

    send_message(chat_id, card, keyboard)
