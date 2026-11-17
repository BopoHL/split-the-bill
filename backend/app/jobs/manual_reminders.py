"""Delivers the reminders owners asked for in the app.

A send through a sender account takes seconds, so a tick stops taking new ones
before the scheduler's timeout; whatever is left waits for the next tick.
"""
import logging
import time
from datetime import datetime

from sqlmodel import Session

from app.models import ReminderFailure
from app.services.reminder_service import ReminderService

logger = logging.getLogger(__name__)

TIME_BUDGET_SECONDS = 40


def run(session: Session, now: datetime | None = None) -> int:
    service = ReminderService(session)
    started = time.monotonic()
    delivered = 0
    for reminder in service.pending():
        if time.monotonic() - started > TIME_BUDGET_SECONDS:
            break
        try:
            service.deliver(reminder, now or datetime.utcnow())
        except Exception:  # noqa: BLE001 — one broken reminder must not hold up the queue
            logger.exception("Reminder %s could not be delivered", reminder.id)
            session.rollback()
            service.fail(reminder, ReminderFailure.ERROR)
        delivered += 1
    return delivered
