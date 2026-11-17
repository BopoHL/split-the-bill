"""How often one person may be reminded by hand: once an hour per bill.

The sender accounts pay for every message they send in spam score, so the limit
holds whoever asks and however — one person, a whole bill, or every bill.
"""
from datetime import datetime, timedelta

from app.models import ManualReminder, ManualReminderStatus, ReminderFailure

COOLDOWN = timedelta(hours=1)
# A pending reminder this old was lost — the job died with it — and no longer
# holds the person's hour.
STALE_PENDING = timedelta(minutes=10)


def holds_cooldown(reminder: ManualReminder, now: datetime) -> bool:
    """Whether this reminder still keeps the person from another one. A failed
    send does not — unless nobody can reach them, which an hour will not change
    much but trying again would cost an account."""
    if now - reminder.created_at >= COOLDOWN:
        return False
    if reminder.status == ManualReminderStatus.PENDING:
        return now - reminder.created_at < STALE_PENDING
    if reminder.status == ManualReminderStatus.FAILED:
        return reminder.failure == ReminderFailure.UNREACHABLE
    return True


def next_reminder_at(reminder: ManualReminder | None, now: datetime) -> datetime | None:
    """When the person may be reminded again; None when they may be now. One
    still on its way counts as sent — it goes out within seconds and holds them
    for the hour; should it be lost instead, they may be reminded at once."""
    if reminder is None or not holds_cooldown(reminder, now):
        return None
    return reminder.created_at + COOLDOWN
