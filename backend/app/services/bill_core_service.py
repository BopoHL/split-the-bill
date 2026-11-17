import json
import logging
import os
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import delete, update
from sqlmodel import or_, select
from app.utils.telegram import is_unreachable_chat
from app.models import InviteChannel
from app.repositories.invite_repo import InviteRepository
from app.services.badges import BadgeService
from app.services.pro import ProService
from app.services.invite_service import InviteService
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import (
    Bill, BillUser, BillStatus, FileAsset, Invite, ManualReminder, PaymentReminder, ReceiptTask,
    SharedBillMessage, SplitType, User,
)
from app.utils.currency import (
    to_tiins,
    from_tiins,
    normalize_currency,
    DEFAULT_CURRENCY,
)
from app.utils.scan_check import reconcile_scan_many
from app.schemas.bill_schemas import BillCreate, BillUpdate, BillResponse, BillDetailResponse, BillItemResponse, BillParticipantResponse, ParticipantPreview, ParticipantReminder, ReceiptSummary, ReceiptDeleteImpact, ViewerSeat, BillOwner, BillCollection, BillCounts
from app.services.validator import BillValidator
from app.services.bill_participant_service import BillParticipantService
from app.repositories.file_repo import FileAssetRepository
from app.repositories.receipt_repo import ReceiptRepository
from app.notifier import notifier
from app.services.payment_link import value_for_method, values_for_methods, resolve_or_create_method_id
from app.services.reminder_policy import next_reminder_at
from app.services.reminder_service import Collecting, ReminderService
from app.services.places import name_of
from app.services.share_message import PostKind
from app.services.shared_bill_service import SharedBillService
from app.services.themes import theme_of
from app.utils.bot_copy import resolve_language

# Upper bound for a bill's declared headcount — guards the Postgres int column
# (and sanity) so a huge value can't overflow it and 500 the endpoint.
MAX_EXPECTED_PEOPLE = 1000


logger = logging.getLogger(__name__)

# How many people the assign picker offers at once, and how much of a username
# has to be typed before we look strangers up by it.
ASSIGNABLE_LIMIT = 30
USERNAME_SEARCH_MIN_LENGTH = 3


# An open bill nobody has touched this long is abandoned: its photos can go.
ABANDONED_AFTER = timedelta(days=180)

class BillCoreService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    def delete_bill(self, bill_id: int, requester_id: int) -> None:
        """Soft-delete a bill (owner only).

        Nothing is erased: items, participants, assignments, scan tasks and the
        stored photo all stay put, hidden by the bill's `deleted_at`. Keeping the
        rows is what makes restore possible and keeps the scan logs attached to
        the bill they came from. Disk space is reclaimed separately by the
        receipt-file purge, which is time-based rather than delete-based.
        """
        bill = self.validator.get_bill_or_404(bill_id)
        if bill.owner_id != requester_id:
            raise HTTPException(status_code=403, detail="Only the owner can delete the bill")

        session = self.bill_repo.session
        bill.deleted_at = datetime.utcnow()
        session.add(bill)
        session.commit()

        # Anyone with the bill open on another device should be bounced out.
        notifier.broadcast(bill_id, "DELETED")

    def discard_provisional_bill(self, bill_id: int, requester_id: int) -> None:
        """Hard-delete a bill that never became one (owner only).

        Used only to roll back a failed or cancelled scan: the user never saw
        this bill, so leaving a soft-deleted shell behind would litter the table
        and make it restorable, which makes no sense for a bill that was never
        valid. A real delete keeps the scan logs by detaching the task.
        """
        bill = self.validator.get_bill_or_404(bill_id)
        if bill.owner_id != requester_id:
            raise HTTPException(status_code=403, detail="Only the owner can delete the bill")
        self.erase(bill)

    def erase(self, bill: Bill) -> None:
        """Remove a bill and everything hanging off it for good — for bills that
        were never real to anyone, so there is nothing to restore."""
        bill_id = bill.id
        session = self.bill_repo.session

        # Detach AI-scan tasks (keep their logs/ratings) — they reference the bill.
        for task in session.exec(select(ReceiptTask).where(ReceiptTask.bill_id == bill_id)).all():
            task.bill_id = None
            session.add(task)

        # Remove the stored receipt files and their metadata rows.
        for asset in session.exec(select(FileAsset).where(FileAsset.bill_id == bill_id)).all():
            try:
                if asset.path and os.path.exists(asset.path):
                    os.remove(asset.path)
            except OSError:
                pass
            session.delete(asset)

        # What sharing and reminding left behind points at the bill and its seats.
        for model in (Invite, SharedBillMessage, PaymentReminder, ManualReminder):
            session.exec(delete(model).where(model.bill_id == bill_id))

        # Items (+ their assignments) and participants, then the bill itself.
        for item in self.bill_repo.get_items_by_bill_id(bill_id):
            for assignment in item.assignments:
                session.delete(assignment)
            session.delete(item)
        for participant in self.bill_repo.get_participants_by_bill_id(bill_id):
            session.delete(participant)

        session.delete(bill)
        session.commit()

    def restore_bill(self, bill_id: int) -> Bill:
        """Undo a soft delete. Admin-only — the mini app has no restore UI."""
        bill = self.bill_repo.get_by_id_including_deleted(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")

        bill.deleted_at = None
        session = self.bill_repo.session
        session.add(bill)
        session.commit()
        session.refresh(bill)
        return bill

    def purge_receipt_files(self, older_than_days: int, pro_older_than_days: int) -> int:
        """Delete stored receipt photos older than the cutoff; returns how many.

        Only bills that are finished or deleted are touched — an open bill may
        still need its photo, unless nobody has touched it for half a year
        (unpaid bills never close on their own). A bill whose owner has Pro keeps its photos for
        the longer Pro term. The FileAsset row goes with the file, so the
        receipt card falls back to its drawn placeholder instead of a broken
        image.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=older_than_days)
        pro_cutoff = now - timedelta(days=pro_older_than_days)
        session = self.bill_repo.session

        old = session.exec(
            select(FileAsset, Bill.owner_id)
            .join(Bill, FileAsset.bill_id == Bill.id)
            .where(
                FileAsset.created_at < cutoff,
                or_(
                    Bill.deleted_at.is_not(None),
                    Bill.status != BillStatus.OPEN,
                    Bill.updated_at < now - ABANDONED_AFTER,
                ),
            )
        ).all()
        pro = ProService(session).pro_among({owner_id for _, owner_id in old}, now)
        stale = [asset for asset, owner_id in old if owner_id not in pro or asset.created_at < pro_cutoff]

        for asset in stale:
            try:
                if asset.path and os.path.exists(asset.path):
                    os.remove(asset.path)
            except OSError:
                pass
            session.delete(asset)

        session.commit()
        return len(stale)

    def reopen_bill(self, bill_id: int, requester_id: int) -> BillDetailResponse:
        """Reopen a closed bill (owner only): CLOSED → OPEN."""
        bill = self.validator.get_bill_or_404(bill_id)
        if bill.owner_id != requester_id:
            raise HTTPException(status_code=403, detail="Only the owner can reopen the bill")
        if bill.status == BillStatus.CLOSED:
            bill.status = BillStatus.OPEN
            self.bill_repo.session.add(bill)
            self.bill_repo.session.commit()
            notifier.broadcast(bill_id, "REFRESH")
        return self.get_bill_details(bill_id, requester_id)

    def _seed_seats(self, bill: Bill, include_owner: bool) -> int:
        """Lay the table: one seat per expected person, filled in up front.

        The owner takes seat 0; the rest start as ephemeral guests with no
        account behind them. Creating them now is what lets the owner assign
        dishes and rename people before anyone has opened the invite — joining
        later is just claiming one of these seats.

        Without a declared headcount there is nothing to lay out, so only the
        owner's seat is created and the bill grows the old way.
        """
        seats: list[BillUser] = []
        if include_owner:
            seats.append(
                BillUser(
                    bill_id=bill.id,
                    user_id=bill.owner_id,
                    seat_index=0,
                    claimed_at=datetime.utcnow(),
                    allocated_amount=0,
                )
            )

        if bill.expected_people:
            for seat_index in range(len(seats), bill.expected_people):
                seats.append(
                    BillUser(bill_id=bill.id, seat_index=seat_index, allocated_amount=0)
                )

        for seat in seats:
            self.bill_repo.session.add(seat)
        self.bill_repo.session.commit()
        return len(seats)

    def _resize_seats(self, bill: Bill, expected_people: int) -> None:
        """Add or drop seats so the table matches the new headcount.

        Growing just appends guests. Shrinking only ever removes seats from the
        end, and only if they are empty in both senses — nobody sitting there and
        nothing on the plate. Anything else would silently delete a person or
        their dishes, so it's refused with the offending seats named.
        """
        session = self.bill_repo.session
        seats = self.bill_repo.get_participants_by_bill_id(bill.id)

        if expected_people >= len(seats):
            for seat_index in range(len(seats), expected_people):
                session.add(
                    BillUser(bill_id=bill.id, seat_index=seat_index, allocated_amount=0)
                )
            session.flush()
            return

        doomed = seats[expected_people:]
        assigned_ids = {
            a.participant_id
            for item in self.bill_repo.get_items_by_bill_id(bill.id)
            for a in item.assignments
        }
        # A seat holding money is in use too: paid, or owing a sum set by hand.
        by_hand = bill.split_type != SplitType.BY_ITEMS
        blocked = [
            s for s in doomed
            if s.user_id is not None or s.id in assigned_ids or s.is_paid or (by_hand and s.allocated_amount)
        ]
        if blocked:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "SEATS_IN_USE",
                    "seat_indexes": [s.seat_index for s in blocked],
                },
            )

        for seat in doomed:
            session.delete(seat)
        session.flush()

    def create_bill(self, bill_data: BillCreate, *, is_demo: bool = False) -> BillResponse:
        owner = self.user_repo.get_by_id(bill_data.owner_id)
        if not owner:
            raise HTTPException(status_code=404, detail="Owner user not found")

        ep = bill_data.expected_people
        if ep is not None and not (1 <= ep <= MAX_EXPECTED_PEOPLE):
            raise HTTPException(
                status_code=400,
                detail=f"expected_people must be between 1 and {MAX_EXPECTED_PEOPLE}",
            )

        # Bind the currency to the bill: prefer the value the client sent, then
        # the owner's saved setting, then the default. Bills keep their own
        # currency, so a later settings change never re-denominates them.
        currency = (
            normalize_currency(bill_data.currency)
            or normalize_currency((owner.settings or {}).get("currency"))
            or DEFAULT_CURRENCY
        )

        payment_method_id = resolve_or_create_method_id(
            self.bill_repo.session, bill_data.owner_id, bill_data.payment_details
        )
        bill = Bill(
            owner_id=bill_data.owner_id,
            total_sum=to_tiins(bill_data.total_sum),
            unallocated_sum=to_tiins(bill_data.total_sum),
            title=bill_data.title,
            payment_method_id=payment_method_id,
            expected_people=bill_data.expected_people,
            currency=currency,
            is_demo=is_demo,
        )
        created_bill = self.bill_repo.create(bill)

        participants_count = self._seed_seats(created_bill, bill_data.include_owner)

        return BillResponse(
            id=created_bill.id,
            owner_id=created_bill.owner_id,
            total_sum=from_tiins(created_bill.total_sum),
            title=created_bill.title,
            payment_details=value_for_method(self.bill_repo.session, created_bill.payment_method_id),
            split_type=created_bill.split_type,
            status=created_bill.status,
            currency=created_bill.currency,
            unallocated_sum=from_tiins(created_bill.unallocated_sum),
            created_at=created_bill.created_at,
            participants_count=participants_count,
            public_token=created_bill.public_token,
            expected_people=created_bill.expected_people,
        )


    def prepare_share_message(self, bill_id: int, requester_id: int, language: str | None) -> str:
        """Register the bill's chat post with Telegram (savePreparedInlineMessage)
        and return the prepared message id the Mini App passes to
        WebApp.shareMessage. Owner or participant only; the post itself is
        written by SharedBillService, which also keeps it current."""
        bill = self.validator.get_bill_or_404(bill_id)
        if bill.status != BillStatus.OPEN:
            raise HTTPException(status_code=409, detail="Only open bills can be shared")
        is_owner = bill.owner_id == requester_id
        is_participant = (
            self.bill_repo.get_participant_by_bill_and_user(bill_id, requester_id)
            is not None
        )
        if not (is_owner or is_participant):
            raise HTTPException(status_code=403, detail="Not authorized to share this bill")

        user = self.user_repo.get_by_id(requester_id)
        if not user or not user.telegram_id:
            raise HTTPException(status_code=400, detail="User has no Telegram account")

        language = resolve_language(language or (user.settings or {}).get("language"))
        try:
            return SharedBillService(self.bill_repo.session).prepare(bill, user, language)
        except RuntimeError as e:
            # Telegram unavailable/misconfigured — the client falls back to the
            # plain share link, so surface a clear (non-5xx-crash) error.
            raise HTTPException(status_code=502, detail=str(e))

    def prepare_personal_seat_invite(
        self,
        bill_id: int,
        participant_id: int,
        requester_id: int,
        lang: str | None,
    ) -> str:
        """The bill's post, for the owner to send one person: the same post as
        any share, but its link sits whoever follows it on this empty seat."""
        bill, seat, owner = self._seat_invite_context(bill_id, participant_id, requester_id)
        language = resolve_language(lang or (owner.settings or {}).get("language"))
        try:
            return SharedBillService(self.bill_repo.session).prepare(bill, owner, language, seat=seat)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))

    def assign_seat_user(
        self,
        bill_id: int,
        participant_id: int,
        requester_id: int,
        target_user_id: int,
        lang: str | None,
    ) -> BillDetailResponse:
        """Seat somebody the owner knows, and send them the bill's post in the
        bot — the same post as any share, already showing them on the seat.

        Both or neither. A person put on a bill without being told has no way to
        find out, so the message goes out while the seat change is still
        uncommitted: a bot that cannot write to them leaves the seat exactly as
        it was, and the owner can fall back to sending the invite by hand.

        The post is written in the language the person reads, not the one
        the owner's screen happens to be in; `lang` only fills in for somebody
        who has not chosen one yet.
        """
        bill, seat, owner = self._seat_invite_context(bill_id, participant_id, requester_id)

        target = self.user_repo.get_by_id(target_user_id)
        # Only someone the picker could have shown: met before, or found by
        # their @name. Any id would let an owner have the bot write to anyone.
        if not target or not target.telegram_id or not (
            target.username or self.bill_repo.have_met(requester_id, target.id)
        ):
            raise HTTPException(status_code=404, detail="User not found")
        if self.bill_repo.get_participant_by_bill_and_user(bill_id, target_user_id):
            raise HTTPException(status_code=409, detail="ALREADY_IN_BILL")
        invite_lang = resolve_language((target.settings or {}).get("language") or lang)

        # Minted before the seat is touched. An unused code is litter; a seat
        # committed without one loses the attribution the invite carries.
        invite = self._invites().create(
            bill.id, requester_id, InviteChannel.SEAT, seat_participant_id=participant_id
        )

        session = self.bill_repo.session
        # One statement, conditional on the seat still being free: the check in
        # _seat_invite_context and this write are separated by a commit, and a
        # claim landing in between must win rather than be overwritten.
        # The split does not move: the seat already existed and already counted.
        claimed = session.exec(
            update(BillUser)
            .where(BillUser.id == seat.id, BillUser.user_id.is_(None))
            .values(
                user_id=target.id,
                claimed_at=datetime.utcnow(),
                guest_name=None,
                invited_by_user_id=requester_id,
            )
            .execution_options(synchronize_session="fetch")
        )
        if claimed.rowcount != 1:
            session.rollback()
            raise HTTPException(status_code=409, detail="SEAT_TAKEN")

        # Reloaded, so the post names the person on their seat.
        session.expire(seat)
        try:
            SharedBillService(session).send(
                bill, invite.code, invite_lang, target.telegram_id, PostKind.DIRECT, theme_of(session, owner, datetime.utcnow())
            )
        except RuntimeError as exc:
            session.rollback()
            if is_unreachable_chat(exc):
                target.settings = {**(target.settings or {}), "bot_blocked": True}
                session.add(target)
                session.commit()
                raise HTTPException(status_code=409, detail="BOT_BLOCKED")
            raise HTTPException(status_code=502, detail=str(exc))

        if (target.settings or {}).get("bot_blocked"):
            target.settings = {**target.settings, "bot_blocked": False}
            session.add(target)

        session.commit()
        notifier.broadcast(bill_id, "REFRESH")
        return self.get_bill_details(bill_id)

    def list_assignable_users(
        self, bill_id: int, requester_id: int, query: str | None
    ) -> list[User]:
        """People the owner can put on a seat.

        Whether the bot may write to someone is not a question Telegram answers.
        A past failure is only a hint for admins and broadcasts: the user may
        have unblocked the bot since then, so the invite flow must stay retryable.
        """
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_owner(bill, requester_id)

        taken = {
            seat.user_id
            for seat in self.bill_repo.get_participants_by_bill_id(bill_id)
            if seat.user_id
        }
        taken.add(requester_id)
        # Exclusions are applied after the query, so ask for enough rows that
        # they can't empty the list.
        headroom = ASSIGNABLE_LIMIT + len(taken)

        term = (query or "").strip().lstrip("@")
        if term:
            if len(term) < USERNAME_SEARCH_MIN_LENGTH:
                return []
            candidates = self.bill_repo.search_users_by_username(term, headroom)
        else:
            candidates = self.bill_repo.get_acquaintances(requester_id, headroom)

        allowed = [user for user in candidates if user.id not in taken]
        return allowed[:ASSIGNABLE_LIMIT]

    def _seat_invite_context(
        self, bill_id: int, participant_id: int, requester_id: int
    ) -> tuple[Bill, BillUser, User]:
        """The three things every seat invite needs, and the reasons to refuse."""
        bill = self.validator.get_bill_or_404(bill_id)
        if bill.status != BillStatus.OPEN:
            raise HTTPException(status_code=409, detail="Only open bills can be shared")
        if bill.owner_id != requester_id:
            raise HTTPException(status_code=403, detail="Only the owner can invite a guest seat")

        owner = self.user_repo.get_by_id(requester_id)
        if not owner or not owner.telegram_id:
            raise HTTPException(status_code=400, detail="User has no Telegram account")

        seat = self.validator.get_participant_or_404(participant_id, bill_id)
        if seat.user_id is not None:
            raise HTTPException(status_code=409, detail="SEAT_TAKEN")
        return bill, seat, owner


    def _invites(self) -> InviteService:
        session = self.bill_repo.session
        return InviteService(
            InviteRepository(session), self.bill_repo, self.user_repo
        )

    def update_bill(self, bill_id: int, update_data: BillUpdate) -> BillDetailResponse:
        # Held like every other money change: a payment marked meanwhile would
        # miss the paid-share check below and see its share moved.
        bill = self.bill_repo.get_by_id_for_update(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        self.validator.ensure_bill_open(bill)
        
        if bill.owner_id != update_data.user_id:
            raise HTTPException(status_code=403, detail="Only owner can update bill")
        
        if "payment_details" in update_data.model_fields_set:
            bill.payment_method_id = resolve_or_create_method_id(
                self.bill_repo.session, bill.owner_id, update_data.payment_details
            )

        if "title" in update_data.model_fields_set:
            # Empty string is treated as 'clear it' to keep API symmetric;
            # the frontend prevents accidental blanks at the UI layer.
            new_title = (update_data.title or "").strip() or None
            if new_title != bill.title and not bill.place_by_owner:
                # The new title may name the place: the labeling job asks again.
                bill.place_checked_at = None
            bill.title = new_title

        if "currency" in update_data.model_fields_set:
            new_currency = normalize_currency(update_data.currency)
            if new_currency is None:
                raise HTTPException(status_code=400, detail="Invalid currency")
            # Only the label changes — amounts stay in the same minor units, so
            # nothing is re-denominated (STB-213).
            bill.currency = new_currency

        from app.services.bill_item_service import BillItemService

        items_service = BillItemService(self.bill_repo, self.user_repo)
        paid_before = None
        recompute_split = False
        if "expected_people" in update_data.model_fields_set:
            ep = update_data.expected_people
            if ep is not None:
                if ep < 1:
                    raise HTTPException(
                        status_code=400, detail="expected_people must be at least 1"
                    )
                if ep > MAX_EXPECTED_PEOPLE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"expected_people can't exceed {MAX_EXPECTED_PEOPLE}",
                    )
                paid_before = items_service._paid_allocations(bill_id)
                self._resize_seats(bill, ep)
            bill.expected_people = ep
            recompute_split = True

        # One commit for the seats and what they now owe: a headcount change
        # re-splits the «among all» lines, and a paid part of one must not move.
        try:
            self.bill_repo.session.add(bill)
            if recompute_split and bill.split_type == SplitType.BY_ITEMS:
                items_service.recalculate_by_items(bill_id, commit=False)
            if paid_before is not None:
                items_service._ensure_paid_allocations_unchanged(bill_id, paid_before)
            self.bill_repo.session.commit()
        except Exception:
            self.bill_repo.session.rollback()
            raise

        from app.notifier import notifier
        notifier.broadcast(bill_id, "REFRESH")

        return self.get_bill_details(bill_id)

    def get_bill_details(
        self,
        bill_id: int,
        requester_id: int | None = None,
        include_deleted: bool = False,
    ) -> BillDetailResponse:
        if include_deleted:
            bill = self.bill_repo.get_by_id_including_deleted(bill_id)
            if not bill:
                raise HTTPException(status_code=404, detail="Bill not found")
        else:
            bill = self.validator.get_bill_or_404(bill_id)

        if requester_id is not None:
            is_owner = bill.owner_id == requester_id
            is_participant = (
                self.bill_repo.get_participant_by_bill_and_user(bill_id, requester_id)
                is not None
            )
            if not (is_owner or is_participant):
                raise HTTPException(
                    status_code=403, detail="Not authorized to view this bill"
                )

        items = self.bill_repo.get_items_by_bill_id(bill_id)
        participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        tasks = ReceiptRepository(self.bill_repo.session).list_tasks_by_bill(bill_id)
        receipts = self._receipt_summaries(bill_id, items, tasks)
        # A photo can also be attached to a hand-made bill without any scan
        # behind it, so this asks the files, not the scans.
        has_receipt = bool(FileAssetRepository(self.bill_repo.session).list_by_bill(bill_id))
        # Reconciliation spans the whole bill: with several receipts, the printed
        # totals add up and so do the items each of them produced.
        receipt_total_sum, scan_total_mismatch = reconcile_scan_many(tasks, items)

        return BillDetailResponse(
            id=bill.id,
            owner_id=bill.owner_id,
            total_sum=from_tiins(bill.total_sum),
            title=bill.title,
            payment_details=value_for_method(self.bill_repo.session, bill.payment_method_id),
            split_type=bill.split_type,
            status=bill.status,
            currency=bill.currency,
            unallocated_sum=from_tiins(bill.unallocated_sum),
            allocated_sum=from_tiins(max(0, bill.total_sum - bill.unallocated_sum)),
            paid_count=sum(1 for p in participants if p.is_paid),
            left_to_collect=from_tiins(sum(seat.allocated_amount for seat in ReminderService.owing(bill, participants))),
            created_at=bill.created_at,
            public_token=bill.public_token,
            expected_people=bill.expected_people,
            is_demo=bill.is_demo,
            place=name_of(self.bill_repo.session, bill),
            has_receipt=has_receipt,
            is_ai_scanned=bool(tasks),
            scan_quality=next((t.scan_quality for t in tasks if t.scan_quality), None),
            receipt_total_sum=receipt_total_sum,
            scan_total_mismatch=scan_total_mismatch,
            receipts=receipts,
            items=[BillItemResponse.from_item(item) for item in items],
            participants=self._with_badges(self._with_reminders(bill_id, [BillParticipantService.map_to_response(p) for p in participants])),
        )

    def _with_badges(self, participants: list[BillParticipantResponse]) -> list[BillParticipantResponse]:
        badges = BadgeService(self.bill_repo.session).shown_for(
            {participant.user_id for participant in participants if participant.user_id}, datetime.utcnow(),
        )
        for participant in participants:
            participant.badge = badges.get(participant.user_id)
        return participants

    def _with_reminders(self, bill_id: int, participants: list[BillParticipantResponse]) -> list[BillParticipantResponse]:
        """Each seat with the last reminder the owner sent it, so the app can say
        how it went and when the next one may go."""
        now = datetime.utcnow()
        latest = ReminderService(self.bill_repo.session).latest_by_seat([bill_id])
        for participant in participants:
            reminder = latest.get(participant.id)
            if reminder:
                next_at = next_reminder_at(reminder, now)
                # Naive UTC in the database; said as UTC, the app counts minutes from it.
                participant.reminder = ParticipantReminder(
                    status=reminder.status,
                    at=reminder.created_at.replace(tzinfo=timezone.utc),
                    failure=reminder.failure,
                    next_at=next_at.replace(tzinfo=timezone.utc) if next_at else None,
                )
        return participants

    def _receipt_summaries(self, bill_id: int, items, tasks) -> list[ReceiptSummary]:
        """One row per receipt, numbered by position.

        The number is derived rather than stored: deleting the second of three
        receipts should leave ①② rather than a gap.

        Takes the tasks it was already given and looks the photos up in one go —
        this runs on every SSE refresh for every participant.
        """
        photo_task_ids = {
            asset.receipt_task_id
            for asset in FileAssetRepository(self.bill_repo.session).list_by_bill(bill_id)
            if asset.receipt_task_id is not None
        }

        summaries: list[ReceiptSummary] = []
        for position, task in enumerate(tasks, start=1):
            own_items = [i for i in items if i.receipt_task_id == task.id]
            merchant = None
            if task.llm_response:
                try:
                    merchant = json.loads(task.llm_response).get("title")
                except (ValueError, TypeError):
                    merchant = None

            summaries.append(
                ReceiptSummary(
                    task_id=task.id,
                    index=position,
                    source=task.source,
                    status=task.status,
                    merchant_name=merchant,
                    total=from_tiins(sum(i.item_sum for i in own_items)) if own_items else None,
                    items_count=len(own_items),
                    quality=task.scan_quality,
                    has_photo=task.id in photo_task_ids,
                    created_at=task.created_at,
                )
            )
        return summaries

    def get_receipt_delete_impact(
        self, bill_id: int, task_id: int, requester_id: int
    ) -> ReceiptDeleteImpact:
        """What removing this receipt would take with it.

        The confirmation quotes the price of the decision, and the count of
        already-assigned portions can't be worked out on the client — it doesn't
        know how portions are shared.
        """
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_owner(bill, requester_id)

        task = ReceiptRepository(self.bill_repo.session).get_task_for_bill(bill_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Receipt not found for this bill")

        own_items = [
            i for i in self.bill_repo.get_items_by_bill_id(bill_id)
            if i.receipt_task_id == task.id
        ]
        return ReceiptDeleteImpact(
            items_count=len(own_items),
            total=from_tiins(sum(i.item_sum for i in own_items)),
            assigned_count=sum(len(i.assignments) for i in own_items),
        )

    def delete_receipt(
        self, bill_id: int, task_id: int, requester_id: int, keep_items: bool
    ) -> BillDetailResponse:
        """Remove one receipt from the bill.

        `keep_items` decides the fate of what it brought in: dropping them undoes
        the whole scan, keeping them detaches the lines so they live on in the
        «no receipt» group. Either way only this receipt is touched — the others
        keep their items.
        """
        from app.services.bill_item_service import BillItemService

        items_service = BillItemService(self.bill_repo, self.user_repo)
        session = self.bill_repo.session
        files: list[str] = []
        # One transaction under the bill's lock, held to the rule every edit
        # follows: a share somebody already paid stays as it was. Deleting a
        # receipt took its dishes off paid plates and was not undone on error.
        try:
            bill = self.bill_repo.get_by_id_for_update(bill_id)
            if not bill:
                raise HTTPException(status_code=404, detail="Bill not found")
            self.validator.ensure_bill_open(bill)
            self.validator.ensure_owner(bill, requester_id)
            task = ReceiptRepository(session).get_task_for_bill(bill_id, task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Receipt not found for this bill")
            paid_before = items_service._paid_allocations(bill_id)

            for item in self.bill_repo.get_items_by_bill_id(bill_id):
                if item.receipt_task_id != task.id:
                    continue
                if keep_items:
                    item.receipt_task_id = None
                    session.add(item)
                else:
                    session.delete(item)

            for asset in FileAssetRepository(session).list_by_bill(bill_id):
                if asset.receipt_task_id != task.id:
                    continue
                if asset.path:
                    files.append(asset.path)
                session.delete(asset)

            # The scan's logs and rating outlive the receipt, so the task is detached
            # rather than deleted — same as when a bill goes away.
            task.bill_id = None
            session.add(task)
            session.flush()
            items_service._recompute_totals_from_items(bill_id, commit=False)
            items_service._ensure_paid_allocations_unchanged(bill_id, paid_before)
            session.commit()
        except Exception:
            session.rollback()
            raise

        # Off the disk only once the rows are gone for good.
        for path in files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        notifier.broadcast(bill_id, "REFRESH")
        return self.get_bill_details(bill_id)

    def get_user_bills(
        self,
        user_id: int,
        offset: int = 0,
        limit: int = 10,
        status_filter: str | None = None,
        query: str | None = None,
        role: str | None = None,
    ) -> list[BillResponse]:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        results = self.bill_repo.get_user_bills(
            user_id, offset=offset, limit=limit, status_filter=status_filter, query=query, role=role
        )

        # One lookup for every linked card on the page, so the list endpoint
        # keeps its single-query shape.
        cards = values_for_methods(
            self.bill_repo.session, [bill.payment_method_id for bill, *_ in results]
        )

        # Build a small participant preview (initial + avatar) for the page in
        # one extra query, then group by bill.
        PREVIEW_LIMIT = 4
        bill_ids = [bill.id for bill, *_ in results]
        preview_by_bill: dict[int, list[ParticipantPreview]] = {}
        for bid, guest_name, name, username, avatar_url in (
            self.bill_repo.get_participants_for_bills(bill_ids)
        ):
            bucket = preview_by_bill.setdefault(bid, [])
            if len(bucket) >= PREVIEW_LIMIT:
                continue
            label = (name or username or guest_name or "").strip()
            bucket.append(
                ParticipantPreview(
                    initial=(label[:1].upper() or "?"),
                    avatar_url=avatar_url,
                )
            )

        seats_by_bill = self.bill_repo.get_seats_by_bill(bill_ids)
        own_seats = {
            bill_id: seat for bill_id, seats in seats_by_bill.items() for seat in seats if seat.user_id == user_id
        }
        owners = self.user_repo.get_many({bill.owner_id for bill, *_ in results})
        collecting = ReminderService(self.bill_repo.session).collecting(
            [bill for bill, *_ in results if bill.owner_id == user_id], seats_by_bill, datetime.utcnow()
        )

        return [
            BillResponse(
                id=bill.id,
                owner_id=bill.owner_id,
                total_sum=from_tiins(bill.total_sum),
                title=bill.title,
                payment_details=cards.get(bill.payment_method_id),
                split_type=bill.split_type,
                status=bill.status,
                currency=bill.currency,
                unallocated_sum=from_tiins(bill.unallocated_sum),
                created_at=bill.created_at,
                participants_count=participants_count,
                items_count=items_count,
                paid_count=paid_count,
                payers_count=payers_count,
                payers_paid=payers_paid,
                participants_preview=preview_by_bill.get(bill.id, []),
                public_token=bill.public_token,
                expected_people=bill.expected_people,
                my_seat=self._viewer_seat(own_seats.get(bill.id)),
                owner=self._owner_of(owners.get(bill.owner_id)),
                collection=self._collection(collecting.get(bill.id)),
            )
            for (
                bill,
                participants_count,
                items_count,
                paid_count,
                payers_count,
                payers_paid,
            ) in results
        ]

    def count_user_bills(self, user_id: int, status_filter: str | None, query: str | None) -> BillCounts:
        found, owned = self.bill_repo.count_user_bills(user_id, status_filter=status_filter, query=query)
        return BillCounts(all=found, owned=owned, joined=found - owned)

    @staticmethod
    def _viewer_seat(seat: BillUser | None) -> ViewerSeat | None:
        if seat is None:
            return None
        return ViewerSeat(id=seat.id, amount=from_tiins(seat.allocated_amount), is_paid=seat.is_paid)

    @staticmethod
    def _owner_of(user: User | None) -> BillOwner | None:
        if user is None:
            return None
        return BillOwner(name=user.name or user.username, avatar_url=user.avatar_url)

    @staticmethod
    def _collection(collecting: Collecting | None) -> BillCollection | None:
        if collecting is None:
            return None
        # Naive UTC in the database; said as UTC, the app counts minutes from it.
        return BillCollection(
            left=from_tiins(collecting.left),
            remindable=collecting.remindable,
            reminded_at=collecting.reminded_at.replace(tzinfo=timezone.utc) if collecting.reminded_at else None,
            next_reminder_at=collecting.next_at.replace(tzinfo=timezone.utc) if collecting.next_at else None,
        )
