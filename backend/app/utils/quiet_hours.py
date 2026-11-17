"""The do-not-disturb night, read in the app's local zone: whatever the bot
sends on its own — reminders, nudges — waits it out."""
import os
from datetime import datetime, time, timedelta, timezone

from app.utils.local_time import as_utc, local_zone

DEFAULT_QUIET_HOURS = "23:00-09:00"


def _quiet_window() -> tuple[time, time]:
    raw = os.getenv("REMINDER_QUIET_HOURS", DEFAULT_QUIET_HOURS)
    try:
        start_raw, end_raw = raw.split("-")
        return time.fromisoformat(start_raw.strip()), time.fromisoformat(end_raw.strip())
    except (ValueError, AttributeError):
        return time(23, 0), time(9, 0)


def in_quiet_hours(moment: datetime) -> bool:
    """Whether local time falls inside the do-not-disturb window (it wraps midnight)."""
    start, end = _quiet_window()
    local = as_utc(moment).astimezone(local_zone()).time()
    if start <= end:
        return start <= local < end
    return local >= start or local < end


def morning_grace() -> timedelta:
    """How far a night reaches into the next day, and an hour more: what it put
    off goes out when it ends. Nothing for quiet hours within one day."""
    start, end = _quiet_window()
    if start <= end:
        return timedelta(0)
    return timedelta(hours=end.hour + 1, minutes=end.minute)


def next_allowed_moment(moment: datetime) -> datetime:
    """Push a due time out of the quiet window without burning a step.

    Waiting out the night must not count as a reminder — otherwise a bill created
    in the evening would spend its whole escalation asleep and wake up on the
    slowest cadence.
    """
    if not in_quiet_hours(moment):
        return moment

    _, end = _quiet_window()
    local = as_utc(moment).astimezone(local_zone())
    resume = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if resume <= local:
        resume += timedelta(days=1)

    resumed_utc = resume.astimezone(timezone.utc)
    return resumed_utc if moment.tzinfo else resumed_utc.replace(tzinfo=None)
