"""Keeps the bills shared into chats in step with the bills themselves.

Each tick looks only at the bills that changed since the one before, as the app
announces them; now and then, and after a restart, it looks at every live post
so nothing missed stays stale. A post is rewritten only when what it shows has
changed, and only so many per tick, so a busy moment stays inside Telegram's
flood limits; the rest follow on the next tick. A closed bill gets its final
post and is left alone after that.
"""
from datetime import datetime, timedelta

from sqlmodel import Session

from app.notifier import notifier
from app.services.shared_bill_service import SharedBillService

EDITS_PER_TICK = 20
FULL_PASS_EVERY = timedelta(minutes=10)

_full_pass_at: datetime | None = None


def run(session: Session, now: datetime) -> int:
    global _full_pass_at
    if _full_pass_at is None or now - _full_pass_at >= FULL_PASS_EVERY:
        _full_pass_at = now
        return SharedBillService(session).refresh_due(now, EDITS_PER_TICK)
    changed = notifier.take_changed()
    if not changed:
        return 0
    try:
        return SharedBillService(session).refresh_due(now, EDITS_PER_TICK, changed)
    finally:
        notifier.mark_changed(changed)
