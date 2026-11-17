"""The bot's queue in the admin panel: where it stands, what is in it, and
running a failed update again or settling a payment given up on."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.bot_worker import SLOTS, update_worker
from app.database import get_session
from app.schemas.admin_schemas import AdminBotQueue, AdminBotUpdate, AdminBotUpdatesPage
from app.services.telegram_updates_admin import QueueView, TelegramUpdatesAdmin
from app.utils.admin_auth import require_admin

router = APIRouter(prefix="/admin/bot-queue", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("", response_model=AdminBotQueue)
def read_queue(session: Session = Depends(get_session)):
    return TelegramUpdatesAdmin(session).queue(datetime.utcnow(), SLOTS)


@router.get("/updates", response_model=AdminBotUpdatesPage)
def list_updates(
    view: QueueView = QueueView.QUEUE,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    return TelegramUpdatesAdmin(session).page(datetime.utcnow(), view, q, limit, offset)


@router.post("/updates/{update_id}/retry", response_model=AdminBotUpdate)
def retry_update(update_id: int, session: Session = Depends(get_session)):
    row = TelegramUpdatesAdmin(session).retry(update_id, datetime.utcnow())
    update_worker.wake()
    return row


@router.post("/updates/{update_id}/settle", response_model=AdminBotUpdate)
def settle_update(update_id: int, session: Session = Depends(get_session)):
    return TelegramUpdatesAdmin(session).settle(update_id, datetime.utcnow())
