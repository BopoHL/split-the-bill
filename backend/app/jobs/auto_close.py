"""Closes settled bills after a short grace period.

Participants need a moment after the last payment tick to notice or cancel a
mistake. The scheduler calls this once a minute; this job keeps the closing rule
in one place and makes old bills tolerant of leftover unallocated amounts.
"""
import logging
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, or_
from sqlmodel import Session, select

from app.models import Bill, BillStatus, BillUser
from app.notifier import notifier
from app.services.product_events import ProductEvent, Surface, capture

logger = logging.getLogger(__name__)

# Long enough for the table to keep moving after the last person pays — someone
# remembers a drink, someone re-assigns a dish — and short enough that nobody is
# left waiting on a bill that is plainly finished.
DEFAULT_GRACE_SECONDS = 15 * 60
DEFAULT_TZ = "Asia/Tashkent"


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(os.getenv("AUTO_CLOSE_TZ", os.getenv("REMINDER_TZ", DEFAULT_TZ)))
    except Exception:
        logger.warning("Unknown auto-close timezone; falling back to UTC")
        return ZoneInfo("UTC")


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _local_day_start(moment: datetime) -> datetime:
    local = _as_utc(moment).astimezone(_tz())
    start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
    start_utc = start.astimezone(timezone.utc)
    return start_utc if moment.tzinfo else start_utc.replace(tzinfo=None)


def _grace_period() -> timedelta:
    try:
        raw = int(os.getenv("AUTO_CLOSE_GRACE_SECONDS", DEFAULT_GRACE_SECONDS))
        return timedelta(seconds=max(0, raw))
    except ValueError:
        return timedelta(seconds=DEFAULT_GRACE_SECONDS)


def _payers(bill: Bill, seats: list[BillUser]) -> list[BillUser]:
    return [
        seat for seat in seats
        if seat.user_id != bill.owner_id and seat.allocated_amount > 0
    ]


def _ready_to_close(bill: Bill, seats: list[BillUser], now: datetime) -> bool:
    payers = _payers(bill, seats)
    if not payers or any(not seat.is_paid for seat in payers):
        return False

    is_new_bill = bill.created_at >= _local_day_start(now)
    if is_new_bill and bill.unallocated_sum != 0:
        return False

    last_confirmation = max(seat.updated_at for seat in payers)
    return last_confirmation + _grace_period() <= now


def run(session: Session, now: datetime | None = None) -> int:
    """One tick. Returns how many bills were closed."""
    now = now or datetime.utcnow()
    closed: list[Bill] = []
    # The same payers as _payers, so only bills they have all paid come back.
    # Abandoned bills stay open forever, and fetching every one of them with a
    # query each, every minute, grew with the whole history.
    payer = and_(
        BillUser.bill_id == Bill.id,
        or_(BillUser.user_id.is_(None), BillUser.user_id != Bill.owner_id),
        BillUser.allocated_amount > 0,
    )
    candidates = session.exec(
        select(Bill).where(
            Bill.status.in_([BillStatus.OPEN, BillStatus.PAID]),
            Bill.deleted_at.is_(None),
            exists().where(payer),
            ~exists().where(payer, BillUser.is_paid.is_(False)),
        )
    ).all()

    for bill in candidates:
        seats = session.exec(select(BillUser).where(BillUser.bill_id == bill.id)).all()
        if not _ready_to_close(bill, seats, now):
            continue

        owner_seat = next((seat for seat in seats if seat.user_id == bill.owner_id), None)
        if owner_seat is not None:
            owner_seat.is_paid = True
            owner_seat.paid_at = owner_seat.paid_at or now
            session.add(owner_seat)
        bill.status = BillStatus.CLOSED
        session.add(bill)
        closed.append(bill)

    session.commit()

    for bill in closed:
        notifier.broadcast(bill.id, "REFRESH")
        capture(bill.owner_id, ProductEvent.BILL_CLOSED, Surface.SERVER, bill_id=bill.id, auto=True)

    return len(closed)
