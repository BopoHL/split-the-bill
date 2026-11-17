"""Forgetting the Telegram updates the bot is done with.

One is kept a week after it was handled or given up on: long enough to look
into what became of it, short enough to keep the table small. A payment given
up on is kept until the admin settles it by hand: its Stars were taken and no
Pro was given.
"""
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, not_
from sqlmodel import Session

from app.models import TelegramUpdate
from app.services.telegram_updates import PAYMENT_LANE

KEPT_FOR = timedelta(days=7)


def run(session: Session, now: datetime) -> int:
    unsettled = and_(
        TelegramUpdate.lane.startswith(PAYMENT_LANE),
        TelegramUpdate.error.is_not(None),
        TelegramUpdate.settled_at.is_(None),
    )
    forgotten = session.execute(
        delete(TelegramUpdate).where(TelegramUpdate.done_at < now - KEPT_FOR, not_(unsettled))
    )
    session.commit()
    return forgotten.rowcount
