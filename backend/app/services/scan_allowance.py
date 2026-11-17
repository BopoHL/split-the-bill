"""How many receipts someone may still read today.

Without Pro, photos and Soliq QR codes together are limited to a few a day —
the operator says how many — counted from midnight where the app's people are.
A scan that failed or was cancelled read nothing, so it does not count. Pro
reads without limit.
"""
from datetime import datetime, time, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import ReceiptSource, ReceiptTask, ReceiptTaskStatus
from app.services.app_settings import get_free_scans_per_day
from app.services.pro import ProService
from app.utils.local_time import local_zone

READING = (ReceiptSource.PHOTO.value, ReceiptSource.SOLIQ_QR.value)
READ_NOTHING = (ReceiptTaskStatus.FAILED.value, ReceiptTaskStatus.CANCELLED.value)


class ScanLimitReached(Exception):
    def __init__(self, limit: int):
        super().__init__(f"{limit} scans a day")
        self.limit = limit


def _today_started(now: datetime) -> datetime:
    """Midnight today where the app's people are, as naive UTC like `now`."""
    zone = local_zone()
    local = now.replace(tzinfo=timezone.utc).astimezone(zone)
    midnight = datetime.combine(local.date(), time.min, tzinfo=zone)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


class ScanAllowance:
    def __init__(self, session: Session):
        self.session = session

    def left_today(self, user_id: int, now: datetime) -> int | None:
        """Scans still free today; None when there is no limit."""
        if ProService(self.session).is_pro(user_id, now):
            return None
        used = self.session.exec(
            select(func.count()).select_from(ReceiptTask).where(
                ReceiptTask.user_id == user_id,
                ReceiptTask.created_at >= _today_started(now),
                ReceiptTask.source.in_(READING),
                ReceiptTask.status.not_in(READ_NOTHING),
            )
        ).one()
        return max(0, get_free_scans_per_day(self.session) - used)

    def ensure(self, user_id: int, now: datetime) -> None:
        if self.left_today(user_id, now) == 0:
            raise ScanLimitReached(get_free_scans_per_day(self.session))
