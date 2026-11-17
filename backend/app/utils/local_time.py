"""Where the app's people are: days, dates and the clock on its pictures and in
its numbers are read in this zone."""
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DEFAULT_ZONE = "Asia/Tashkent"
logger = logging.getLogger(__name__)


def local_zone() -> ZoneInfo:
    try:
        return ZoneInfo(os.getenv("REMINDER_TZ", DEFAULT_ZONE))
    except Exception:
        logger.warning("Unknown REMINDER_TZ; falling back to %s", DEFAULT_ZONE)
        return ZoneInfo(DEFAULT_ZONE)


def as_utc(moment: datetime) -> datetime:
    """Everything stored and passed around is naive UTC. Without this,
    `astimezone` would read a naive value as the SERVER's local time — so on a
    machine that isn't on UTC every local reading would shift by the offset."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def naive_utc(moment: datetime) -> datetime:
    """The database keeps naive UTC: an aware moment is moved to UTC, a naive
    one is taken as UTC already."""
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment
