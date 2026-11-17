"""Reminds people who still owe money on an open bill.

Deliberately stateless between ticks: every run recomputes who is eligible from
the bills themselves rather than relying on some earlier event having created a
row. A missed webhook or a restart can't leave someone permanently un-nudged,
and conditions that stop applying (the bill closed, the share was paid, an item
came back unallocated) silently stop the reminders without anything having to
remember to cancel them.
"""
import logging
import os
from datetime import datetime, time, timedelta, timezone

from sqlmodel import Session, select

from app.models import Bill, BillStatus, BillUser, PaymentReminder, ReminderChannel, ReminderFailure, User
from app.repositories.user_repo import UserRepository
from app.services.pro import ProService
from app.services.reminder_service import ReminderService, count_reminder
from app.services.user_service import UserService
from app.utils.local_time import as_utc, local_zone
from app.utils.quiet_hours import in_quiet_hours, morning_grace, next_allowed_moment
from app.utils.telegram import is_unreachable_chat

logger = logging.getLogger(__name__)

# 15 min, then progressively less often. The last value repeats, so the cadence
# settles rather than stopping — an unpaid share doesn't stop being unpaid.
DEFAULT_INTERVALS_MIN = (15, 30, 60, 180)
# Without Pro the bot still reminds each person once, so a free bill gets paid
# too; the reminders after it are Pro, like the ones sent by hand.
FREE_AUTO_REMINDERS = 1

def _intervals() -> tuple[int, ...]:
    raw = os.getenv("REMINDER_INTERVALS_MIN")
    if not raw:
        return DEFAULT_INTERVALS_MIN
    try:
        parsed = tuple(int(part) for part in raw.split(",") if part.strip())
        return parsed or DEFAULT_INTERVALS_MIN
    except ValueError:
        return DEFAULT_INTERVALS_MIN


def local_day_start(moment: datetime) -> datetime:
    """Start of the reminder day in the configured local timezone, returned as UTC."""
    local = as_utc(moment).astimezone(local_zone())
    start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo)
    start_utc = start.astimezone(timezone.utc)
    return start_utc if moment.tzinfo else start_utc.replace(tzinfo=None)


def _interval_for(sent_count: int) -> timedelta:
    intervals = _intervals()
    return timedelta(minutes=intervals[min(sent_count, len(intervals) - 1)])


def _eligible_seats(session: Session, now: datetime) -> list[tuple[Bill, BillUser]]:
    """Everyone currently owing money on a fully-allocated open bill — for as
    long as its owner has Pro, or until the free reminders are spent.

    `unallocated_sum == 0` is the gate that makes a reminder honest: while part
    of the bill is unassigned, the amount shown could still change. Past the
    free ones, reminders go quiet without Pro and come back from where they
    were if Pro does.
    """
    bills = session.exec(
        select(Bill).where(
            Bill.status == BillStatus.OPEN,
            Bill.deleted_at.is_(None),
            Bill.unallocated_sum == 0,
            # Its day and the morning after: one put off by the night must still go out.
            Bill.created_at >= local_day_start(now - morning_grace()),
        )
    ).all()
    pro_owners = ProService(session).pro_among({bill.owner_id for bill in bills}, now)
    sent = _sent_counts(session, [bill.id for bill in bills if bill.owner_id not in pro_owners])

    pairs: list[tuple[Bill, BillUser]] = []
    for bill in bills:
        seats = session.exec(select(BillUser).where(BillUser.bill_id == bill.id)).all()
        for seat in seats:
            # Guests have no account to write to, and the owner is the one being
            # paid rather than the one paying.
            if seat.user_id is None or seat.user_id == bill.owner_id:
                continue
            if seat.is_paid or seat.allocated_amount <= 0:
                continue
            if bill.owner_id not in pro_owners and sent.get(seat.id, 0) >= FREE_AUTO_REMINDERS:
                continue
            pairs.append((bill, seat))
    return pairs


def _sent_counts(session: Session, bill_ids: list[int]) -> dict[int, int]:
    """How many reminders each seat of these bills has had, by seat."""
    if not bill_ids:
        return {}
    rows = session.exec(
        select(PaymentReminder.participant_id, PaymentReminder.sent_count).where(
            PaymentReminder.bill_id.in_(bill_ids)
        )
    ).all()
    return dict(rows)


def run(session: Session, now: datetime | None = None) -> int:
    """One tick. Returns how many reminders were sent."""
    now = now or datetime.utcnow()

    eligible = _eligible_seats(session, now)
    eligible_ids = {seat.id for _, seat in eligible}

    # Anything that stopped qualifying goes quiet on its own.
    for stale in session.exec(
        select(PaymentReminder).where(PaymentReminder.next_due_at.is_not(None))
    ).all():
        if stale.participant_id not in eligible_ids:
            stale.next_due_at = None
            session.add(stale)

    try:
        sent = _send_due(session, eligible, now)
    except Exception:
        # Keep what already went out, so a crash halfway can't resend it.
        session.commit()
        raise

    session.commit()
    return sent


def _send_due(
    session: Session,
    eligible: list[tuple[Bill, BillUser]],
    now: datetime,
) -> int:
    users = UserService(UserRepository(session))
    sent = 0
    for bill, seat in eligible:
        reminder = session.exec(
            select(PaymentReminder).where(
                PaymentReminder.bill_id == bill.id,
                PaymentReminder.participant_id == seat.id,
            )
        ).first()

        if reminder is None:
            reminder = PaymentReminder(
                bill_id=bill.id,
                participant_id=seat.id,
                next_due_at=next_allowed_moment(now + _interval_for(0)),
            )
            session.add(reminder)
            continue

        if reminder.muted_at is not None:
            continue
        if reminder.next_due_at is None:
            # It qualified again after a spell of not qualifying — restart the
            # clock rather than firing immediately.
            reminder.next_due_at = next_allowed_moment(now + _interval_for(reminder.sent_count))
            session.add(reminder)
            continue
        if reminder.next_due_at > now:
            continue
        if in_quiet_hours(now):
            reminder.next_due_at = next_allowed_moment(now)
            session.add(reminder)
            continue

        user = session.get(User, seat.user_id)
        if not user or not user.telegram_id:
            reminder.next_due_at = None
            session.add(reminder)
            continue

        try:
            # The same post the owner sends by hand: the dishes, the share, the
            # card, and «I've paid» right under it.
            ReminderService(session).remind_by_bot(bill, seat, user)
        except RuntimeError as exc:
            # Only Telegram's own refusals are swallowed. Anything else is a bug
            # in this job, and swallowing it per user would leave a log full of
            # warnings and a feature that quietly never runs — which is how a
            # missing import once went unnoticed here.
            if is_unreachable_chat(exc):
                # There is no way back from this until the user starts the bot
                # again, so stop trying rather than retrying forever.
                reminder.muted_at = now
                session.add(reminder)
                users.note_write_access(user, False)
                count_reminder(user.id, bill.id, auto=True, failure=ReminderFailure.UNREACHABLE)
            logger.warning("Payment reminder failed for user %s: %s", user.id, exc)
            continue

        users.note_write_access(user, True)
        count_reminder(user.id, bill.id, auto=True, channel=ReminderChannel.BOT)
        reminder.sent_count += 1
        reminder.last_sent_at = now
        reminder.next_due_at = next_allowed_moment(now + _interval_for(reminder.sent_count))
        session.add(reminder)
        sent += 1

    return sent
