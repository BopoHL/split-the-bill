import logging
import os
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import select
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import Bill, BillItemAssignment, BillUser, SplitType, BillStatus, User
from app.utils.currency import from_tiins
from app.utils.telegram import is_unreachable_chat, send_message
from app.schemas.bill_schemas import BillParticipantCreate, BillParticipantResponse, BillParticipantPaymentUpdate, BillDetailResponse, BillSeatsResponse, SeatPreview, SeatItemPreview
from app.services.item_split import TableSplit
from app.services.validator import BillValidator
from app.notifier import notifier

logger = logging.getLogger(__name__)

# One-time onboarding DM the bot sends the first time it can message a user
# (after they grant write access on their first invite-link join). Keyed by the
# two-letter language code; unknown codes fall back to Russian. (body, open_label)
_ONBOARDING: dict[str, tuple[str, str]] = {
    "ru": (
        "Привет! 👋 Это <b>Split Bill</b> — бот, который делит счёт за вас.\n\n"
        "Отсканируйте чек, пригласите друзей, разделите блюда и следите, кто уже "
        "оплатил. Больше не нужно считать доли в калькуляторе.\n\n"
        "Откройте приложение кнопкой ниже и попробуйте прямо сейчас. А чтобы "
        "Split Bill всегда был под рукой — добавьте его на главный экран в настройках.",
        "Открыть Split Bill",
    ),
    "uz": (
        "Salom! 👋 Bu <b>Split Bill</b> — hisobni siz uchun bo'lib beradigan bot.\n\n"
        "Chekni skanerlang, do'stlaringizni taklif qiling, taomlarni bo'ling va kim "
        "to'laganini kuzating. Endi ulushlarni kalkulyatorda sanash shart emas.\n\n"
        "Ilovani quyidagi tugma bilan oching va hoziroq sinab ko'ring. Split Bill doim "
        "qo'l ostida bo'lishi uchun uni sozlamalardan bosh ekranga qo'shing.",
        "Split Bill'ni ochish",
    ),
    "en": (
        "Hi! 👋 This is <b>Split Bill</b> — the bot that splits the check for you.\n\n"
        "Scan the receipt, invite friends, divide the dishes and see who's already "
        "paid. No more working out shares on a calculator.\n\n"
        "Tap the button below to open the app and give it a try. And add Split Bill to "
        "your home screen in settings so it's always one tap away.",
        "Open Split Bill",
    ),
}


def _onboarding_copy(lang: str | None) -> tuple[str, str]:
    """Return (message_html, open_button_label) for the one-time onboarding DM."""
    code = (lang or "").split("-")[0].lower()
    return _ONBOARDING.get(code, _ONBOARDING["ru"])

class BillParticipantService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    def add_bill_participant(self, bill_id: int, participant_data: BillParticipantCreate) -> list[BillParticipantResponse]:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        
        user = self.user_repo.get_by_id(participant_data.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        seats = self.bill_repo.get_participants_by_bill_id(bill_id)
        if any(p.user_id == participant_data.user_id for p in seats):
            return [self.map_to_response(p) for p in seats]

        # The owner adding someone by hand fills the first free seat. If the table
        # is full they've decided it needs one more chair, so it grows — unlike an
        # invite join, which must take an existing seat.
        seat = next((p for p in seats if p.user_id is None), None)
        if seat is None:
            seat = BillUser(
                bill_id=bill_id,
                seat_index=(seats[-1].seat_index + 1) if seats else 0,
                allocated_amount=0,
            )
            if bill.expected_people is not None:
                bill.expected_people = len(seats) + 1

        seat.user_id = participant_data.user_id
        seat.claimed_at = datetime.utcnow()
        seat.guest_name = None
        self.bill_repo.session.add(seat)
        self.bill_repo.session.commit()
        self.bill_repo.session.refresh(seat)
        
        bill.split_type = SplitType.MANUAL
        self.bill_repo.session.add(bill)
        self.bill_repo.session.commit()
        
        notifier.broadcast(bill_id, "REFRESH")
        
        all_participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        return [self.map_to_response(p) for p in all_participants]

    def update_payment_status(self, bill_id: int, participant_id: int, payment_data: BillParticipantPaymentUpdate) -> BillParticipantResponse:
        # Item and assignment mutations take this same lock. Acquire it before
        # reading the participant so payment confirmation cannot race an
        # allocation change between the paid check and commit.
        bill = self.bill_repo.get_by_id_for_update(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        participant = self.validator.get_participant_or_404(participant_id, bill_id)

        is_owner = (bill.owner_id == payment_data.user_id)
        is_self = (participant.user_id == payment_data.user_id)
        is_empty_guest = participant.user_id is None
        # The owner stands in for an empty seat, and may take back anyone's
        # payment that never arrived; confirming a person's payment is theirs.
        owner_may = is_owner and (is_empty_guest or not payment_data.is_paid)

        if not (is_self or owner_may):
            raise HTTPException(status_code=403, detail="Not authorized to change payment status")

        if participant.is_paid == payment_data.is_paid:
            return self.map_to_response(participant)

        # Payments can be freely confirmed and cancelled (by the participant
        # themselves or the owner) while the bill is open; once it's closed
        # the payment state is locked.
        if bill.status == BillStatus.CLOSED:
            raise HTTPException(status_code=409, detail="Bill is closed")

        if payment_data.is_paid and participant.allocated_amount <= 0:
            raise HTTPException(status_code=400, detail="Cannot confirm payment for zero or negative amount")

        participant.is_paid = payment_data.is_paid
        participant.updated_at = datetime.utcnow()
        participant.paid_at = participant.updated_at if payment_data.is_paid else None
        if payment_data.is_paid:
            # Someone paying their own share is news the bot takes to the owner;
            # a seat the owner marked is not.
            participant.owner_told_at = participant.updated_at if is_owner else None
        self.bill_repo.session.add(participant)

        # PAID is an intermediate state: if any confirmed payment is cancelled,
        # the bill becomes editable/joinable again.
        if not payment_data.is_paid and bill.status == BillStatus.PAID:
            bill.status = BillStatus.OPEN
            self.bill_repo.session.add(bill)

        if payment_data.is_paid:
            all_participants = self.bill_repo.get_participants_by_bill_id(bill_id)
            payers = [
                p for p in all_participants
                if p.user_id != bill.owner_id and p.allocated_amount > 0
            ]
            others_paid = bool(payers) and all(p.is_paid for p in payers)
            
            if bill.unallocated_sum == 0 and others_paid:
                bill.status = BillStatus.PAID
                self.bill_repo.session.add(bill)

        self.bill_repo.session.commit()
        self.bill_repo.session.refresh(participant)

        notifier.broadcast(bill_id, "REFRESH")

        return self.map_to_response(participant)

    def join_bill(
        self, bill_id: int, user_id: int, invited_by_user_id: int | None = None
    ) -> BillParticipantResponse:
        bill = self.validator.get_bill_or_404(bill_id)

        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # An existing participant (the owner included) always gets back in, even
        # once the bill is closed — the invite link just navigates them into it
        # instead of erroring. The open-bill check below is only for newcomers (STB-230).
        existing_participant = self.bill_repo.get_participant_by_bill_and_user(bill_id, user_id)
        if existing_participant:
            return self.map_to_response(existing_participant)

        # A newcomer can only join while the bill is open; on a closed/paid bill
        # the client shows a dedicated "bill is closed" screen (STB-230).
        if bill.status != BillStatus.OPEN:
            raise HTTPException(status_code=409, detail="Bill is closed")

        seats = self.bill_repo.get_participants_by_bill_id(bill_id)

        # A bill created without a declared headcount has no table laid out, so
        # there is nothing to choose from — joining just adds a seat, as it
        # always did. Everything created through the current flow declares a
        # headcount and takes the branch below.
        if bill.expected_people is None:
            seat = BillUser(
                bill_id=bill_id,
                user_id=user_id,
                seat_index=(seats[-1].seat_index + 1) if seats else 0,
                claimed_at=datetime.utcnow(),
                allocated_amount=0,
                invited_by_user_id=invited_by_user_id,
            )
            created = self.bill_repo.add_participant(seat)
            self._resplit(bill)
            if bill.split_type != SplitType.BY_ITEMS:
                bill.split_type = SplitType.MANUAL
                self.bill_repo.session.add(bill)
            self.bill_repo.session.commit()
            self.bill_repo.session.refresh(created)
            if created.user_id and not created.user:
                created.user = self.user_repo.get_by_id(created.user_id)
            notifier.broadcast(bill_id, "REFRESH")
            return self.map_to_response(created)

        # Otherwise the seats already exist and may already have dishes on them,
        # so the newcomer has to say which one is theirs.
        if not any(p.user_id is None for p in seats):
            raise HTTPException(status_code=409, detail="BILL_FULL")
        raise HTTPException(status_code=409, detail="SEAT_REQUIRED")

    def _resplit(self, bill: Bill) -> None:
        """Re-run whichever split the bill is using after its seats changed."""
        if bill.split_type == SplitType.BY_ITEMS:
            from app.services.bill_item_service import BillItemService

            BillItemService(self.bill_repo, self.user_repo).recalculate_by_items(bill.id)

    def get_seats_by_token(self, token: str, user_id: int | None = None) -> BillSeatsResponse:
        """Seats behind an invite link, for someone who isn't in the bill yet.

        Deliberately readable without being a participant — you cannot choose a
        seat before you have one, and the token is unguessable. It exposes only
        what the picker shows: who is sitting where and what is already on each
        plate.
        """
        bill = self.bill_repo.get_by_token(token)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")

        seats = self.bill_repo.get_participants_by_bill_id(bill.id)
        items = [item for item in self.bill_repo.get_items_by_bill_id(bill.id) if not item.is_shared_globally]
        splits = TableSplit.of(bill, seats).split_items(items)
        per_seat: dict[int, list[SeatItemPreview]] = {}
        for item in items:
            for seat_id, share in splits[item.id].shares.items():
                per_seat.setdefault(seat_id, []).append(SeatItemPreview(name=item.name, share=from_tiins(share)))

        return BillSeatsResponse(
            bill_id=bill.id,
            title=bill.title,
            currency=bill.currency,
            status=bill.status,
            seats=[
                SeatPreview(
                    id=p.id,
                    seat_index=p.seat_index,
                    guest_name=p.guest_name,
                    display_name=(p.user.username or p.user.name) if p.user else None,
                    avatar_url=p.user.avatar_url if p.user else None,
                    is_taken=p.user_id is not None,
                    is_me=user_id is not None and p.user_id == user_id,
                    allocated_amount=from_tiins(p.allocated_amount),
                    items=per_seat.get(p.id, []),
                )
                for p in seats
            ],
        )

    def claim_seat(
        self,
        bill_id: int,
        participant_id: int,
        user_id: int,
        invited_by_user_id: int | None = None,
        confirm_move: bool = False,
    ) -> BillDetailResponse:
        """Take a seat, or move to a different one.

        Moving leaves the dishes behind: a seat is a place at the table with a
        plate on it, and what moves is the person, not the plate. Somebody who
        picked the wrong seat wants the other seat's dishes — that's the whole
        reason they're moving.

        Which is also why a move is never silent. Every button in a personal
        invite claims a seat on the way in, so a link tapped out of a chat used
        to move whoever tapped it — abandoning their dishes on a seat anyone
        could then take. A move now needs `confirm_move`, and the client only
        sets it after asking. The rule lives here rather than in the four places
        that claim a seat, because a fifth one would otherwise be a fresh hole.
        """
        bill = self.validator.get_bill_or_404(bill_id)

        if not self.user_repo.get_by_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")

        seat = self.validator.get_participant_or_404(participant_id, bill_id)
        # Already sitting here: hand the bill back before asking whether it is
        # still open. Every button in a personal invite claims the seat on the
        # way in, so on a bill that has since closed — usually because this very
        # person paid — the owner of the seat was refused their own bill.
        if seat.user_id == user_id:
            return self._get_bill_details_response(bill_id)

        self.validator.ensure_bill_open(bill)
        if seat.user_id is not None:
            raise HTTPException(status_code=409, detail="SEAT_TAKEN")

        previous = self.bill_repo.get_participant_by_bill_and_user(bill_id, user_id)
        if previous:
            # The owner stays where they are. `release_seat` has always refused
            # to let them stand up — a bill with no owner at the table splits
            # wrong — but claiming another seat went around it and vacated seat
            # 0 with the owner's dishes still on it, for the next arrival to
            # take.
            if bill.owner_id == user_id:
                raise HTTPException(status_code=409, detail="OWNER_SEAT_FIXED")
            # Money already said to have changed hands is not something a seat
            # change may quietly rewrite: the payment was for THIS plate. Undo
            # the payment first, then move.
            if previous.is_paid:
                raise HTTPException(status_code=409, detail="SEAT_PAID")
            if not confirm_move:
                raise HTTPException(status_code=409, detail="SEAT_MOVE_CONFIRM")

            previous.user_id = None
            previous.claimed_at = None
            previous.guest_name = None
            self.bill_repo.session.add(previous)
            # Vacate BEFORE claiming, in its own statement. Both rows change in
            # one flush otherwise, and SQLAlchemy orders those by primary key
            # rather than by meaning — so moving to a lower-numbered seat wrote
            # the new occupant first and briefly put the same user on two seats,
            # which the (bill_id, user_id) unique index rejects. That is why
            # moving on worked and moving back failed.
            self.bill_repo.session.flush()

        # One statement, on the seat still being free: two people tapping the
        # same seat at once both passed the check above, and the second write
        # took it from the first, who was told they were seated.
        claimed = self.bill_repo.session.exec(
            update(BillUser)
            .where(BillUser.id == seat.id, BillUser.user_id.is_(None))
            .values(
                user_id=user_id,
                claimed_at=datetime.utcnow(),
                guest_name=None,
                # A move within the same bill keeps whoever brought the person here.
                invited_by_user_id=previous.invited_by_user_id if previous else invited_by_user_id,
            )
            .execution_options(synchronize_session="fetch")
        )
        if claimed.rowcount != 1:
            self.bill_repo.session.rollback()
            raise HTTPException(status_code=409, detail="SEAT_TAKEN")
        self.bill_repo.session.commit()

        self._resplit(bill)
        self.bill_repo.session.commit()
        notifier.broadcast(bill_id, "REFRESH")
        return self._get_bill_details_response(bill_id)

    def release_seat(self, bill_id: int, participant_id: int, requester_id: int) -> BillDetailResponse:
        """Free a seat without removing it — the dishes on it stay put.

        Used both when someone leaves and when the owner kicks them out. The seat
        reverts to a guest so the headcount and the split stay consistent.
        """
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)

        seat = self.validator.get_participant_or_404(participant_id, bill_id)
        if not (bill.owner_id == requester_id or seat.user_id == requester_id):
            raise HTTPException(status_code=403, detail="Not authorized to free this seat")
        if seat.user_id == bill.owner_id:
            raise HTTPException(status_code=400, detail="The owner cannot leave their own bill")
        # Leaving wiped the payment and left the sum owed on the empty seat, for
        # whoever sat there next. The payment is undone first, as for a move.
        if seat.is_paid:
            raise HTTPException(status_code=409, detail="SEAT_PAID")

        if bill.expected_people is None:
            # No declared headcount means no fixed table, so an empty seat would
            # be a phantom person in the split. Drop it; assignments go with it
            # through the FK cascade.
            if bill.split_type == SplitType.MANUAL:
                bill.unallocated_sum += seat.allocated_amount
                self.bill_repo.session.add(bill)
            self.bill_repo.delete_participant(seat)
        else:
            # The table was laid for N. Someone leaving doesn't shrink it — the
            # seat reverts to a guest and keeps whatever was assigned to it, so
            # the split stays consistent until the owner changes the headcount.
            seat.user_id = None
            seat.claimed_at = None
            seat.is_paid = False
            seat.paid_at = None
            # A freed seat is nobody in particular again, so a label the owner
            # gave the previous occupant would be misleading — back to «Guest N».
            seat.guest_name = None
            self.bill_repo.session.add(seat)
        self.bill_repo.session.commit()

        self._resplit(bill)
        self.bill_repo.session.commit()
        notifier.broadcast(bill_id, "REFRESH")
        return self._get_bill_details_response(bill_id)

    def rename_guest(
        self, bill_id: int, participant_id: int, requester_id: int, guest_name: str | None
    ) -> BillParticipantResponse:
        """Label an unclaimed seat («Wife», «Sasha»). Owner only.

        A claimed seat shows the name from Telegram, so there is nothing to
        rename there. An empty name resets to the default «Guest N» label, which
        the client builds from seat_index — no localized string is ever stored.
        """
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        self.validator.ensure_owner(bill, requester_id)

        seat = self.validator.get_participant_or_404(participant_id, bill_id)
        if seat.user_id is not None:
            raise HTTPException(status_code=400, detail="Only guest seats can be renamed")

        cleaned = (guest_name or "").strip()
        seat.guest_name = cleaned or None
        self.bill_repo.session.add(seat)
        self.bill_repo.session.commit()

        notifier.broadcast(bill_id, "REFRESH")
        return self.map_to_response(seat)

    def join_bill_by_token(
        self, token: str, user_id: int, invited_by_user_id: int | None = None
    ) -> BillParticipantResponse:
        bill = self.bill_repo.get_by_token(token)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        return self.join_bill(bill.id, user_id, invited_by_user_id)

    def send_onboarding_dm(self, bill_id: int, user_id: int, lang: str | None) -> None:
        """Send the bot's one-time onboarding DM the first time it can message a
        user — triggered after they grant write access on an invite-link join, so
        the bot lands in their chat list. Sent at most once per user (guarded by the
        `welcome_sent` flag in user settings). Best-effort and participant-only."""
        self.validator.get_bill_or_404(bill_id)
        if not self.bill_repo.get_participant_by_bill_and_user(bill_id, user_id):
            raise HTTPException(status_code=403, detail="User is not a participant of this bill")

        session = self.bill_repo.session
        user = session.exec(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        if not user or not user.telegram_id:
            session.rollback()
            return
        settings = dict(user.settings or {})
        if settings.get("welcome_sent"):
            if settings.get("bot_blocked"):
                # The client calls this only after Telegram granted write
                # access, so a previously blocked user is reachable again.
                user.settings = {**settings, "bot_blocked": False}
                session.add(user)
                session.commit()
            else:
                session.rollback()
            return  # already onboarded — never DM the same user twice

        body, open_label = _onboarding_copy(lang)

        reply_markup = None
        base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
        if base:
            reply_markup = {
                "inline_keyboard": [[{"text": open_label, "web_app": {"url": base}}]]
            }

        try:
            send_message(user.telegram_id, body, reply_markup)
        except RuntimeError as e:
            logger.warning("Failed to send onboarding DM to user %s: %s", user_id, e)
            if is_unreachable_chat(e):
                user.settings = {**(user.settings or {}), "bot_blocked": True}
                session.add(user)
                session.commit()
                return
            session.rollback()
            return  # leave the flag unset so a later join can retry

        # Persist the flag only after a successful send (reassign so SQLAlchemy
        # detects the JSON change).
        settings = {**(user.settings or {}), "welcome_sent": True}
        if settings.get("bot_blocked"):
            settings["bot_blocked"] = False
        user.settings = settings
        session.add(user)
        session.commit()

    def confirm_and_close_bill(
        self, bill_id: int, user_id: int, remainder: str | None = None
    ) -> BillDetailResponse:
        """Close the bill; with `remainder`, first hand what nobody took to the
        owner (`me`) or to every seat (`all`). One transaction: done from the app
        a request at a time, a close that failed left everyone's amounts changed
        on a bill that was still open."""
        session = self.bill_repo.session
        try:
            bill = self.bill_repo.get_by_id_for_update(bill_id)
            if not bill:
                raise HTTPException(status_code=404, detail="Bill not found")
            if bill.owner_id != user_id:
                raise HTTPException(status_code=403, detail="Only owner can finalize the bill")

            participant = self.bill_repo.get_participant_by_bill_and_user(bill_id, user_id)
            if not participant:
                raise HTTPException(status_code=404, detail="Owner is not a participant in this bill")

            if remainder and bill.status != BillStatus.CLOSED:
                self._hand_out_what_is_left(bill, participant, remainder)

            participant.is_paid = True
            participant.paid_at = participant.paid_at or datetime.utcnow()
            bill.status = BillStatus.CLOSED

            session.add(participant)
            session.add(bill)
            session.commit()
        except Exception:
            session.rollback()
            raise
        
        notifier.broadcast(bill_id, "REFRESH")
        
        return self._get_bill_details_response(bill_id)

    def _hand_out_what_is_left(self, bill: Bill, owner_seat: BillUser, mode: str) -> None:
        """Every portion nobody took goes to the takers, then any remainder is
        spread among them. A share someone already paid stays as it was."""
        from app.services.bill_item_service import BillItemService
        from app.services.bill_split_service import BillSplitService

        session = self.bill_repo.session
        items = BillItemService(self.bill_repo, self.user_repo)
        paid_before = items._paid_allocations(bill.id)
        takers = [owner_seat] if mode == "me" else self.bill_repo.get_participants_by_bill_id(bill.id)

        dishes = self.bill_repo.get_items_by_bill_id(bill.id)
        # Shares set by hand stay: handing out dishes would turn the bill into a
        # split by dishes and wipe them. What is left goes out as money instead.
        hand_split = bill.split_type != SplitType.BY_ITEMS and any(
            seat.allocated_amount for seat in self.bill_repo.get_participants_by_bill_id(bill.id)
        )
        handed_out = False
        for item in [] if hand_split else dishes:
            if item.is_shared_globally:
                continue
            taken = {assignment.portion_index for assignment in item.assignments}
            for portion in range(max(1, item.count or 1)):
                if portion in taken:
                    continue
                handed_out = True
                session.add_all(
                    BillItemAssignment(bill_item_id=item.id, participant_id=seat.id, portion_index=portion)
                    for seat in takers
                )
        if handed_out:
            bill.split_type = SplitType.BY_ITEMS
            session.flush()
            for item in dishes:
                session.expire(item, ["assignments"])
            items.recalculate_by_items(bill.id, commit=False)

        if bill.unallocated_sum > 0:
            BillSplitService.spread_remainder(bill, takers)
        items._ensure_paid_allocations_unchanged(bill.id, paid_before)

    def _get_bill_details_response(self, bill_id: int) -> BillDetailResponse:
        """Delegate to the single assembler of a bill response.

        There used to be a second copy here, and it drifted: it never filled
        `receipts[]`, so any action answering through it — leaving a seat,
        claiming one, removing a participant, closing the bill — wiped the
        receipts list on the client until the next refetch.
        """
        from app.services.bill_core_service import BillCoreService

        return BillCoreService(self.bill_repo, self.user_repo).get_bill_details(bill_id)

    @staticmethod
    def map_to_response(p: BillUser) -> BillParticipantResponse:
        username = p.guest_name
        name = None
        surname = None
        avatar_url = None
        
        if hasattr(p, "user") and p.user:
            username = p.user.username
            name = p.user.name
            surname = p.user.surname
            avatar_url = p.user.avatar_url
            
        return BillParticipantResponse(
            id=p.id,
            bill_id=p.bill_id,
            user_id=p.user_id,
            guest_name=p.guest_name,
            username=username,
            name=name,
            surname=surname,
            avatar_url=avatar_url,
            allocated_amount=from_tiins(p.allocated_amount),
            is_paid=p.is_paid,
            seat_index=p.seat_index,
            is_guest=p.user_id is None,
            claimed_at=p.claimed_at,
        )
