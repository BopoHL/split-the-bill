"""Reminders the owner of a bill sends by hand.

Asking is instant: a pending row per person, and the app moves on. A job
delivers them — from the bot first, and when the person has blocked the bot,
through the sender accounts one after another until one gets through. An
account Telegram held back is rested or retired on the way; a person no account
can reach ends the chain at once, since every other account would fail alike.

How often one person may be reminded is reminder_policy's.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from enum import Enum

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    Bill,
    BillStatus,
    BillUser,
    FreeReminderUse,
    Invite,
    InviteChannel,
    ManualReminder,
    ManualReminderStatus,
    ReminderChannel,
    ReminderFailure,
    User,
)
from app.notifier import notifier
from app.repositories.bill_repo import BillRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.user_repo import UserRepository
from app.services import sender_telegram
from app.services.pro import ProService, pro_required
from app.services.invite_service import InviteService
from app.services.product_events import ProductEvent, Surface, capture
from app.services.reminder_policy import holds_cooldown, next_reminder_at
from app.services.sender_accounts import SenderAccountService
from app.utils.local_time import local_zone
from app.services.shared_bill_service import SharedBillService
from app.utils.telegram import is_unreachable_chat

logger = logging.getLogger(__name__)


class Skip(str, Enum):
    """Why a seat got no reminder."""

    GUEST = "guest"
    OWNER = "owner"
    PAID = "paid"
    NOTHING_OWED = "nothing_owed"
    COOLDOWN = "cooldown"


class WhyNobody(str, Enum):
    """Why the owner's open bills have nobody to remind, and nobody to wait for:
    what they would do first to get somebody."""

    NO_BILLS = "no_bills"
    NO_PEOPLE = "no_people"
    UNASSIGNED = "unassigned"
    GUESTS = "guests"
    ALL_PAID = "all_paid"


@dataclass
class Requested:
    queued: list[ManualReminder] = field(default_factory=list)
    skipped: dict[int, Skip] = field(default_factory=dict)


@dataclass(frozen=True)
class Owed:
    totals: dict[str, int]
    people: int
    bills: int
    remindable: int
    # When the first of those reminded lately may be reminded again.
    next_at: datetime | None = None
    why_nobody: WhyNobody | None = None


@dataclass(frozen=True)
class Collecting:
    """One open bill as its owner sees it: what is still owed, how many of the
    people owing may be reminded now, and when they last were or next may be."""

    left: int
    remindable: int
    reminded_at: datetime | None
    next_at: datetime | None


# «Remind everyone» without Pro, pressed this many times a calendar month.
FREE_REMINDERS_PER_MONTH = 3


def _month_started(now: datetime) -> datetime:
    """The first of this month where the app's people are, as naive UTC like `now`."""
    zone = local_zone()
    local = now.replace(tzinfo=timezone.utc).astimezone(zone)
    first = datetime.combine(local.date().replace(day=1), time.min, tzinfo=zone)
    return first.astimezone(timezone.utc).replace(tzinfo=None)


def free_reminders_left(session: Session, user_id: int, now: datetime) -> int | None:
    """Free «remind everyone» presses left this month; None with Pro."""
    if ProService(session).is_pro(user_id, now):
        return None
    used = session.exec(
        select(func.count()).select_from(FreeReminderUse).where(
            FreeReminderUse.user_id == user_id, FreeReminderUse.created_at >= _month_started(now),
        )
    ).one()
    return max(0, FREE_REMINDERS_PER_MONTH - used)


class ReminderService:
    def __init__(self, session: Session):
        self.session = session
        self.bills = BillRepository(session)

    # ── Asking ───────────────────────────────────────────────────────────────

    def request_for_bill(self, bill_id: int, requester_id: int, participant_id: int | None, now: datetime) -> Requested:
        bill = self.bills.get_by_id(bill_id)
        if bill is None:
            raise HTTPException(status_code=404, detail="Bill not found")
        if bill.owner_id != requester_id:
            raise HTTPException(status_code=403, detail="Only the owner can send reminders")
        if bill.status != BillStatus.OPEN:
            raise HTTPException(status_code=409, detail="Only open bills can be reminded of")
        # One seat is Pro's; everyone on the bill is a «remind everyone».
        free = self._allow_everyone(requester_id, now) if participant_id is None else self._require_pro(requester_id, now)

        seats = self.bills.get_participants_by_bill_id(bill_id)
        if participant_id is not None:
            seats = [seat for seat in seats if seat.id == participant_id]
            if not seats:
                raise HTTPException(status_code=404, detail="Participant not found for this bill")
        requested = self._request(bill, seats, self.latest_by_seat([bill_id]), requester_id, now)
        self._spend_free(free, requested)
        return requested

    def request_owed(self, owner_id: int, now: datetime) -> Requested:
        """Everyone who owes the owner on any of their open bills."""
        free = self._allow_everyone(owner_id, now)
        bills = self._open_bills(owner_id)
        bill_ids = [bill.id for bill in bills]
        seats_by_bill = self.bills.get_seats_by_bill(bill_ids)
        latest = self.latest_by_seat(bill_ids)
        requested = Requested()
        for bill in bills:
            outcome = self._request(bill, seats_by_bill.get(bill.id, []), latest, owner_id, now)
            requested.queued += outcome.queued
            requested.skipped |= outcome.skipped
        self._spend_free(free, requested)
        return requested

    def _require_pro(self, owner_id: int, now: datetime) -> None:
        if not ProService(self.session).is_pro(owner_id, now):
            raise pro_required("reminders")

    def _allow_everyone(self, owner_id: int, now: datetime) -> FreeReminderUse | None:
        """Whether a «remind everyone» may go — with Pro always, without it a
        few times a month — and the free press it takes, if it takes one.

        The press is written before the reminders and committed with them, the
        person's row held meanwhile: two presses at once would otherwise both
        read «one left»."""
        if ProService(self.session).is_pro(owner_id, now):
            return None
        self.session.exec(select(User).where(User.id == owner_id).with_for_update()).one()
        if free_reminders_left(self.session, owner_id, now) == 0:
            raise pro_required("reminders")
        used = FreeReminderUse(user_id=owner_id)
        self.session.add(used)
        self.session.flush()
        return used

    def _spend_free(self, used: FreeReminderUse | None, requested: "Requested") -> None:
        # A press that reminded nobody — everyone paid or was just reminded — costs nothing.
        if used is not None and not requested.queued:
            self.session.delete(used)
            self.session.commit()

    def _request(
        self, bill: Bill, seats: list[BillUser], latest: dict[int, ManualReminder], requester_id: int, now: datetime,
    ) -> Requested:
        requested = Requested()
        for seat in seats:
            reason = self.why_not(bill, seat, latest.get(seat.id), now)
            if reason:
                requested.skipped[seat.id] = reason
                continue
            lost = latest.get(seat.id)
            if lost and lost.status == ManualReminderStatus.PENDING:
                # A pending one this old went down with the job that took it;
                # the new one replaces it, so the person is not reminded twice.
                lost.status = ManualReminderStatus.FAILED
                lost.failure = ReminderFailure.ERROR
                self.session.add(lost)
            reminder = ManualReminder(bill_id=bill.id, participant_id=seat.id, requested_by_user_id=requester_id)
            self.session.add(reminder)
            requested.queued.append(reminder)
        self.session.commit()
        if requested.queued:
            notifier.broadcast(bill.id, "REFRESH")
        return requested

    @staticmethod
    def why_not(bill: Bill, seat: BillUser, latest: ManualReminder | None, now: datetime) -> Skip | None:
        if seat.user_id is None:
            return Skip.GUEST
        if seat.user_id == bill.owner_id:
            return Skip.OWNER
        if seat.is_paid:
            return Skip.PAID
        if seat.allocated_amount <= 0:
            return Skip.NOTHING_OWED
        if latest and holds_cooldown(latest, now):
            return Skip.COOLDOWN
        return None

    def latest_by_seat(self, bill_ids: list[int]) -> dict[int, ManualReminder]:
        """The last reminder each seat on these bills was sent, in one query."""
        if not bill_ids:
            return {}
        reminders = self.session.exec(
            select(ManualReminder).where(ManualReminder.bill_id.in_(bill_ids)).order_by(ManualReminder.id)
        ).all()
        return {reminder.participant_id: reminder for reminder in reminders}

    # ── What the owner is owed ───────────────────────────────────────────────

    def owed(self, owner_id: int, now: datetime) -> Owed:
        open_bills = self._open_bills(owner_id)
        bill_ids = [bill.id for bill in open_bills]
        seats_by_bill = self.bills.get_seats_by_bill(bill_ids)
        latest = self.latest_by_seat(bill_ids)
        totals: dict[str, int] = {}
        people = bills = remindable = 0
        waits: list[datetime] = []
        for bill in open_bills:
            owing = self.owing(bill, seats_by_bill.get(bill.id, []))
            if not owing:
                continue
            bills += 1
            people += len(owing)
            totals[bill.currency] = totals.get(bill.currency, 0) + sum(seat.allocated_amount for seat in owing)
            for seat in owing:
                reason = self.why_not(bill, seat, latest.get(seat.id), now)
                if reason is None:
                    remindable += 1
                elif reason is Skip.COOLDOWN:
                    waits.append(next_reminder_at(latest[seat.id], now))
        return Owed(
            totals=totals,
            people=people,
            bills=bills,
            remindable=remindable,
            next_at=min(waits, default=None),
            why_nobody=None if remindable or waits else self.why_nobody(open_bills, seats_by_bill),
        )

    @staticmethod
    def why_nobody(open_bills: list[Bill], seats_by_bill: dict[int, list[BillUser]]) -> WhyNobody:
        """For open bills with nobody to remind: the step that would bring
        somebody — the app's bill screen asks the same, in the same order."""
        if not open_bills:
            return WhyNobody.NO_BILLS
        others = [
            seat for bill in open_bills for seat in seats_by_bill.get(bill.id, []) if seat.user_id != bill.owner_id
        ]
        if not others:
            return WhyNobody.NO_PEOPLE
        unpaid = [seat for seat in others if not seat.is_paid]
        if any(seat.user_id is not None and seat.allocated_amount <= 0 for seat in unpaid):
            return WhyNobody.UNASSIGNED
        if any(seat.user_id is None and seat.allocated_amount > 0 for seat in unpaid):
            return WhyNobody.GUESTS
        if unpaid:
            return WhyNobody.UNASSIGNED
        return WhyNobody.ALL_PAID

    def collecting(self, bills: list[Bill], seats_by_bill: dict[int, list[BillUser]], now: datetime) -> dict[int, Collecting]:
        """The owner's view of each open bill among these, from the seats the
        caller already has and one look at the reminders."""
        open_bills = [bill for bill in bills if bill.status == BillStatus.OPEN]
        if not open_bills:
            return {}
        latest = self.latest_by_seat([bill.id for bill in open_bills])

        collected: dict[int, Collecting] = {}
        for bill in open_bills:
            owing = self.owing(bill, seats_by_bill.get(bill.id, []))
            remindable = sum(1 for seat in owing if self.why_not(bill, seat, latest.get(seat.id), now) is None)
            asked = [
                latest[seat.id] for seat in owing
                if seat.id in latest and latest[seat.id].status != ManualReminderStatus.FAILED
            ]
            waits = [
                next_at for seat in owing
                if seat.user_id is not None and (next_at := next_reminder_at(latest.get(seat.id), now))
            ]
            collected[bill.id] = Collecting(
                left=sum(seat.allocated_amount for seat in owing),
                remindable=remindable,
                reminded_at=max((reminder.created_at for reminder in asked), default=None),
                next_at=min(waits) if waits and remindable == 0 else None,
            )
        return collected

    @staticmethod
    def owing(bill: Bill, seats: list[BillUser]) -> list[BillUser]:
        """The seats that still owe the owner something."""
        return [
            seat for seat in seats
            if seat.user_id != bill.owner_id and not seat.is_paid and seat.allocated_amount > 0
        ]

    def _open_bills(self, owner_id: int) -> list[Bill]:
        return list(self.session.exec(
            select(Bill).where(
                Bill.owner_id == owner_id,
                Bill.status == BillStatus.OPEN,
                Bill.deleted_at.is_(None),
                Bill.is_demo.is_(False),
            ).order_by(Bill.id)
        ).all())

    # ── Delivering ───────────────────────────────────────────────────────────

    def pending(self) -> list[ManualReminder]:
        return list(self.session.exec(
            select(ManualReminder)
            .where(ManualReminder.status == ManualReminderStatus.PENDING)
            .order_by(ManualReminder.id)
        ).all())

    def deliver(self, reminder: ManualReminder, now: datetime) -> None:
        self.session.refresh(reminder)
        if reminder.status != ManualReminderStatus.PENDING:
            # Replaced by a newer one since the job picked it up.
            return
        bill = self.bills.get_by_id(reminder.bill_id)
        seat = self.session.get(BillUser, reminder.participant_id)
        recipient = self.session.get(User, seat.user_id) if seat and seat.user_id else None
        if (
            bill is None
            or bill.status != BillStatus.OPEN
            or recipient is None
            or seat.is_paid
            or seat.allocated_amount <= 0
        ):
            self.fail(reminder, ReminderFailure.SETTLED)
            return

        code = self.reminder_invite(bill, seat, reminder.requested_by_user_id)
        shared = SharedBillService(self.session)
        if (recipient.settings or {}).get("bot_blocked") is True and recipient.username and sender_telegram.is_configured():
            # Known to have blocked the bot, and an account can reach them: asked
            # again, the bot would bounce on every tick the reminder waits for one.
            self._through_accounts(reminder, bill, code, recipient, shared, now)
            return
        try:
            shared.remind_by_bot(bill, code, recipient)
        except RuntimeError as error:
            if not is_unreachable_chat(error):
                logger.warning("Reminder %s not sent by the bot: %s", reminder.id, error)
                self.fail(reminder, ReminderFailure.ERROR)
                return
            shared.users.note_write_access(recipient, False)
            self._through_accounts(reminder, bill, code, recipient, shared, now)
            return
        shared.users.note_write_access(recipient, True)
        self._sent(reminder, ReminderChannel.BOT, None, now)

    def remind_by_bot(self, bill: Bill, seat: BillUser, recipient: User) -> None:
        """The reminder post from the bot, for the automatic reminders. Raises
        RuntimeError like any bot send."""
        SharedBillService(self.session).remind_by_bot(bill, self.reminder_invite(bill, seat, bill.owner_id), recipient)

    def reminder_invite(self, bill: Bill, seat: BillUser, inviter_id: int) -> str:
        """The code a seat's reminders carry in their buttons: made with the first
        one, and the same for every reminder after it."""
        existing = self.session.exec(
            select(Invite).where(
                Invite.bill_id == bill.id,
                Invite.seat_participant_id == seat.id,
                Invite.channel == InviteChannel.REMINDER,
            )
        ).first()
        if existing:
            return existing.code
        invites = InviteService(InviteRepository(self.session), self.bills, UserRepository(self.session))
        return invites.create(bill.id, inviter_id, InviteChannel.REMINDER, seat_participant_id=seat.id).code

    def _through_accounts(
        self,
        reminder: ManualReminder,
        bill: Bill,
        invite_code: str,
        recipient: User,
        shared: SharedBillService,
        now: datetime,
    ) -> None:
        if not recipient.username:
            # An account finds a stranger by username only.
            self.fail(reminder, ReminderFailure.UNREACHABLE)
            return
        if not sender_telegram.is_configured():
            self.fail(reminder, ReminderFailure.NO_SENDERS)
            return

        senders = SenderAccountService(self.session)
        waiting = False
        for account in senders.available(now):
            if senders.catching_breath(account, now):
                waiting = True
                continue
            try:
                login = senders.session_of(account)
                prepared = shared.prepare_reminder(bill, invite_code, recipient, account.telegram_id)
                sender_telegram.send_prepared(
                    login, prepared.id, recipient.username, recipient.telegram_id, prepared.preview_url,
                )
            except sender_telegram.RecipientUnreachable as unreachable:
                logger.info("Reminder %s: nobody can reach user %s: %s", reminder.id, recipient.id, unreachable)
                self.fail(reminder, ReminderFailure.UNREACHABLE)
                return
            except sender_telegram.AccountTrouble as trouble:
                logger.warning("Sender account %s could not send reminder %s: %s", account.id, reminder.id, trouble)
                senders.record_trouble(account, trouble, now)
                continue
            except RuntimeError as error:
                # The bot could not prepare the message for this account.
                senders.record_trouble(account, sender_telegram.AccountTrouble(f"Not prepared: {error}"), now)
                continue
            senders.record_sent(account, now)
            self._sent(reminder, ReminderChannel.ACCOUNT, account.id, now)
            return
        if waiting:
            # An account is free again within the minute; the reminder stays queued for it.
            return
        self.fail(reminder, ReminderFailure.NO_SENDERS)

    def _sent(self, reminder: ManualReminder, channel: ReminderChannel, account_id: int | None, now: datetime) -> None:
        reminder.status = ManualReminderStatus.SENT
        reminder.channel = channel
        reminder.sender_account_id = account_id
        reminder.sent_at = now
        self._settle(reminder)

    def fail(self, reminder: ManualReminder, failure: ReminderFailure) -> None:
        reminder.status = ManualReminderStatus.FAILED
        reminder.failure = failure
        self._settle(reminder)

    def _settle(self, reminder: ManualReminder) -> None:
        self.session.add(reminder)
        self.session.commit()
        notifier.broadcast(reminder.bill_id, "REFRESH")
        self._count(reminder)

    def _count(self, reminder: ManualReminder) -> None:
        """For the person it was meant for, once it is settled. Counting never
        undoes what was settled: a failure here is only logged."""
        try:
            seat = self.session.get(BillUser, reminder.participant_id)
            if seat is not None and seat.user_id is not None:
                count_reminder(seat.user_id, reminder.bill_id, auto=False, channel=reminder.channel, failure=reminder.failure)
        except Exception:
            logger.exception("Reminder %s was not counted", reminder.id)


def count_reminder(
    recipient_id: int,
    bill_id: int,
    *,
    auto: bool,
    channel: ReminderChannel | str | None = None,
    failure: ReminderFailure | str | None = None,
) -> None:
    """How a reminder ended, for the person it was meant for: the channel that
    delivered it, or the failure that stopped it. A stored reminder keeps both
    as plain strings."""
    try:
        outcome = {"channel": ReminderChannel(channel).value} if channel else {"reason": ReminderFailure(failure).value}
    except ValueError:
        logger.warning("Reminder outcome %r / %r is not one to count", channel, failure)
        return
    capture(
        recipient_id,
        ProductEvent.REMINDER_RESULT,
        Surface.SERVER,
        bill_id=bill_id,
        auto=auto,
        ok=channel is not None,
        **outcome,
    )
