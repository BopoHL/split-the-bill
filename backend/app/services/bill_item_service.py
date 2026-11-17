from contextlib import contextmanager

from fastapi import HTTPException
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import BillItem
from app.utils.currency import to_tiins, from_tiins, share_step
from app.schemas.bill_schemas import (
    BillItemCreate,
    BillItemUpdate,
    BillItemResponse,
    BillItemAssign,
    BillItemAssignBatch,
    BillItemAssignOp,
)
from app.services.validator import BillValidator
from app.services.item_split import TableSplit, dish_value
from app.notifier import notifier
from app.models import SplitType, BillItemAssignment

class BillItemService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    @staticmethod
    def _position_error(status_code: int, code: str, message: str, **context):
        raise HTTPException(
            status_code=status_code,
            detail={"code": code, "message": message, **context},
        )

    def _validate_position_params(
        self, portion_index: int | None, expected_count: int | None
    ) -> None:
        if (portion_index is None) != (expected_count is None):
            self._position_error(
                422,
                "POSITION_PARAMS_REQUIRED",
                "portion_index and expected_count must be provided together",
            )

    def _validate_position_ref(
        self,
        item: BillItem,
        portion_index: int,
        expected_count: int,
    ) -> int:
        count = max(1, item.count or 1)
        if count != expected_count:
            self._position_error(
                409,
                "POSITION_STALE",
                "The item quantity changed; refresh the bill and try again",
                item_id=item.id,
                expected_count=expected_count,
                actual_count=count,
            )
        if not 0 <= portion_index < count:
            self._position_error(
                422,
                "POSITION_OUT_OF_RANGE",
                "portion_index is outside the item quantity",
                item_id=item.id,
                portion_index=portion_index,
                actual_count=count,
            )
        return count

    def _ensure_guest_may_pick(self, bill, is_owner: bool) -> None:
        """A guest picks dishes where dishes decide the split, or where nobody
        has a sum yet — the app's own rule (splitsByDishes). On a bill split by
        hand the first dish taken would turn it into a split by dishes and wipe
        every share that is not paid yet."""
        if is_owner or bill.split_type == SplitType.BY_ITEMS:
            return
        if any(p.allocated_amount for p in self.bill_repo.get_participants_by_bill_id(bill.id)):
            raise HTTPException(status_code=409, detail="SPLIT_BY_HAND")

    def _paid_allocations(self, bill_id: int) -> dict[int, int]:
        bill = self.bill_repo.get_by_id(bill_id)
        if not bill:
            return {}
        return {
            participant.id: participant.allocated_amount
            for participant in self.bill_repo.get_participants_by_bill_id(bill_id)
            if participant.is_paid and participant.user_id != bill.owner_id
        }

    def _ensure_paid_allocations_unchanged(
        self, bill_id: int, before: dict[int, int]
    ) -> None:
        if not before:
            return
        after = {
            participant.id: participant.allocated_amount
            for participant in self.bill_repo.get_participants_by_bill_id(bill_id)
            if participant.id in before
        }
        changed = sorted(
            participant_id
            for participant_id, amount in before.items()
            if after.get(participant_id) != amount
        )
        if changed:
            self._position_error(
                409,
                "PAID_ALLOCATION_LOCKED",
                "Undo payment before changing an affected allocation",
                participant_ids=changed,
            )

    def _compact_assignments_after_position(
        self,
        item: BillItem,
        portion_index: int,
        destination: BillItem | None = None,
    ) -> None:
        """Remove/move one position and compact later indexes without collisions."""
        count = max(1, item.count or 1)
        selected = [
            assignment
            for assignment in item.assignments
            if assignment.portion_index == portion_index
        ]
        later = [
            assignment
            for assignment in item.assignments
            if assignment.portion_index > portion_index
        ]

        for assignment in selected:
            if destination is None:
                self.bill_repo.session.delete(assignment)
            else:
                assignment.bill_item_id = destination.id
                assignment.portion_index = 0
                self.bill_repo.session.add(assignment)

        # Moving to a temporary, disjoint range avoids transient unique-index
        # collisions when one participant owns adjacent positions.
        for assignment in later:
            assignment.portion_index += count
            self.bill_repo.session.add(assignment)
        self.bill_repo.session.flush()

        for assignment in later:
            assignment.portion_index -= count + 1
            self.bill_repo.session.add(assignment)
        self.bill_repo.session.flush()

        self.bill_repo.session.expire(item, ["assignments"])
        if destination is not None:
            self.bill_repo.session.expire(destination, ["assignments"])

    def add_bill_item(self, bill_id: int, item_data: BillItemCreate) -> BillItemResponse:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        
        # assigned_to_user_id removed from schema, ignoring it if passed
        
        price_tiins = to_tiins(item_data.price)
        item_sum_tiins = price_tiins * item_data.count

        item = BillItem(
            bill_id=bill_id,
            name=item_data.name,
            price=price_tiins,
            count=item_data.count,
            item_sum=item_sum_tiins,
            is_shared_globally=False
        )
        created_item = self.bill_repo.add_item(item)

        self._recompute_totals_from_items(bill_id)

        notifier.broadcast(bill_id, "REFRESH")

        return BillItemResponse.from_item(created_item)

    @contextmanager
    def _paid_safe_item_change(self, bill_id: int, item_id: int):
        """Lock the bill and one of its items for a change that must leave every
        paid share as it was. When the block finishes the totals are recomputed
        and the change is committed; any error rolls all of it back."""
        session = self.bill_repo.session
        try:
            bill = self.bill_repo.get_by_id_for_update(bill_id)
            if not bill:
                raise HTTPException(status_code=404, detail="Bill not found")
            self.validator.ensure_bill_open(bill)

            item = self.bill_repo.get_item_by_id_for_update(item_id)
            if not item or item.bill_id != bill_id:
                raise HTTPException(status_code=404, detail="Item not found for this bill")

            paid_before = self._paid_allocations(bill_id)
            yield bill, item
            session.flush()

            self._recompute_totals_from_items(bill_id, commit=False)
            self._ensure_paid_allocations_unchanged(bill_id, paid_before)
            session.commit()
        except Exception:
            session.rollback()
            raise

    def update_bill_item(
        self,
        bill_id: int,
        item_id: int,
        data: BillItemUpdate,
        *,
        portion_index: int | None = None,
        expected_count: int | None = None,
    ) -> BillItemResponse:
        self._validate_position_params(portion_index, expected_count)
        if portion_index is not None and expected_count is not None:
            return self._update_bill_item_position(
                bill_id,
                item_id,
                data,
                portion_index,
                expected_count,
            )

        fields = data.model_dump(exclude_unset=True)
        with self._paid_safe_item_change(bill_id, item_id) as (bill, item):
            if fields.get("name") is not None:
                item.name = fields["name"]
            if fields.get("price") is not None:
                item.price = to_tiins(fields["price"])
            if fields.get("count") is not None:
                self._resize_line(item, fields["count"])
            if fields.get("is_shared_globally") is not None:
                item.is_shared_globally = fields["is_shared_globally"]
            # The stored unit price of a line of several dishes is rounded down,
            # so the total is only derived from it when price or quantity change.
            if fields.get("price") is not None or fields.get("count") is not None:
                item.item_sum = item.price * item.count
            self.bill_repo.session.add(item)

            # Sharing an item makes the split item-based.
            if item.is_shared_globally and bill.split_type != SplitType.BY_ITEMS:
                bill.split_type = SplitType.BY_ITEMS
                self.bill_repo.session.add(bill)

        notifier.broadcast(bill_id, "REFRESH")
        return BillItemResponse.from_item(self.bill_repo.get_item_by_id(item_id))

    def _resize_line(self, item: BillItem, count: int) -> None:
        """Give a line `count` dishes. New dishes come in free. With fewer, the
        dishes nobody has go first, then the last taken ones, and each dropped
        dish takes its assignments with it."""
        session = self.bill_repo.session
        current = max(1, item.count or 1)
        # Left behind by older quantity edits; they would come back to life as
        # soon as the line grew again.
        stale = [assignment for assignment in item.assignments if assignment.portion_index >= current]
        for assignment in stale:
            session.delete(assignment)
        if stale:
            session.flush()
            session.expire(item, ["assignments"])

        taken = {assignment.portion_index for assignment in item.assignments}
        expendable_first = sorted(range(current), key=lambda index: (index in taken, -index))
        for portion_index in sorted(expendable_first[: max(0, current - count)], reverse=True):
            self._compact_assignments_after_position(item, portion_index)
        item.count = count

    def _update_bill_item_position(
        self,
        bill_id: int,
        item_id: int,
        data: BillItemUpdate,
        portion_index: int,
        expected_count: int,
    ) -> BillItemResponse:
        fields = data.model_dump(exclude_unset=True)
        unsupported = sorted(set(fields) - {"name", "price"})
        if unsupported:
            self._position_error(
                422,
                "POSITION_UPDATE_FIELDS_UNSUPPORTED",
                "Per-position updates accept only name and price",
                fields=unsupported,
            )
        effective_fields = {key: value for key, value in fields.items() if value is not None}
        if not effective_fields:
            self._position_error(
                422,
                "POSITION_UPDATE_EMPTY",
                "A per-position update requires name or price",
            )

        session = self.bill_repo.session
        with self._paid_safe_item_change(bill_id, item_id) as (bill, item):
            count = self._validate_position_ref(item, portion_index, expected_count)
            if item.is_shared_globally and count > 1:
                self._position_error(
                    409,
                    "SHARED_POSITION_EDIT_UNSUPPORTED",
                    "Edit the whole shared item instead of one position",
                    item_id=item.id,
                )

            if count == 1:
                target = item
            else:
                selected_sum = dish_value(item, portion_index, share_step(bill.currency))
                target = BillItem(
                    bill_id=item.bill_id,
                    name=item.name,
                    price=selected_sum,
                    count=1,
                    item_sum=selected_sum,
                    is_shared_globally=False,
                    source=item.source,
                    receipt_task_id=item.receipt_task_id,
                )
                session.add(target)
                session.flush()
                self._compact_assignments_after_position(item, portion_index, target)

                item.count = count - 1
                item.item_sum -= selected_sum
                item.price = item.item_sum // item.count
                session.add(item)

            if "name" in effective_fields:
                target.name = effective_fields["name"]
            if "price" in effective_fields:
                target.price = to_tiins(effective_fields["price"])
                target.item_sum = target.price
            session.add(target)
            target_id = target.id

        notifier.broadcast(bill_id, "REFRESH")
        updated = next(
            item
            for item in self.bill_repo.get_items_by_bill_id(bill_id)
            if item.id == target_id
        )
        return BillItemResponse.from_item(updated)

    def delete_bill_item(
        self,
        bill_id: int,
        item_id: int,
        *,
        portion_index: int | None = None,
        expected_count: int | None = None,
    ):
        self._validate_position_params(portion_index, expected_count)
        with self._paid_safe_item_change(bill_id, item_id) as (bill, item):
            if portion_index is None or expected_count is None:
                self.bill_repo.session.delete(item)
            else:
                self._delete_position(item, portion_index, expected_count, share_step(bill.currency))
        notifier.broadcast(bill_id, "REFRESH")

    def _delete_position(self, item: BillItem, portion_index: int, expected_count: int, step: int) -> None:
        count = self._validate_position_ref(item, portion_index, expected_count)
        if count == 1:
            self.bill_repo.session.delete(item)
            return
        removed_sum = dish_value(item, portion_index, step)
        self._compact_assignments_after_position(item, portion_index)
        item.count = count - 1
        item.item_sum -= removed_sum
        item.price = item.item_sum // item.count
        self.bill_repo.session.add(item)

    def assign_item(self, bill_id: int, item_id: int, assign_data: BillItemAssign, requester_id: int):
        session = self.bill_repo.session
        try:
            bill = self.bill_repo.get_by_id_for_update(bill_id)
            if not bill:
                raise HTTPException(status_code=404, detail="Bill not found")
            if bill.status != "open":
                raise HTTPException(status_code=400, detail="Bill is not open")

            item = self.bill_repo.get_item_by_id_for_update(item_id)
            if not item or item.bill_id != bill_id:
                raise HTTPException(status_code=404, detail="Item not found")

            is_owner = (bill.owner_id == requester_id)
            participant = self.validator.get_participant_or_404(assign_data.participant_id, bill_id)
            # A guest can only fill their own plate; the owner fills anyone's.
            if not is_owner and participant.user_id != requester_id:
                raise HTTPException(status_code=403, detail="Only owner can assign items to others")
            self._ensure_guest_may_pick(bill, is_owner)

            count = max(1, item.count or 1)
            # A specific portion, or the whole item (every portion) when omitted.
            if assign_data.portion_index is None:
                target_portions = list(range(count))
            elif 0 <= assign_data.portion_index < count:
                target_portions = [assign_data.portion_index]
            else:
                raise HTTPException(status_code=400, detail="Invalid portion index")

            existing_by_portion = {
                assignment.portion_index: assignment
                for assignment in item.assignments
                if assignment.participant_id == participant.id
            }
            changed_portions = [
                portion
                for portion in target_portions
                if assign_data.is_assigned != (portion in existing_by_portion)
            ]
            if (
                participant.is_paid
                and participant.user_id != bill.owner_id
                and changed_portions
            ):
                self._position_error(
                    409,
                    "PAID_ASSIGNMENT_LOCKED",
                    "Undo payment before changing this participant's positions",
                    participant_ids=[participant.id],
                )

            paid_before = self._paid_allocations(bill_id)
            for portion in changed_portions:
                existing = existing_by_portion.get(portion)
                if assign_data.is_assigned:
                    session.add(BillItemAssignment(
                        bill_item_id=item.id,
                        participant_id=participant.id,
                        portion_index=portion,
                    ))
                elif existing is not None:
                    session.delete(existing)

            if bill.split_type != SplitType.BY_ITEMS:
                bill.split_type = SplitType.BY_ITEMS
            session.add(bill)
            session.flush()
            session.expire(item, ["assignments"])
            self.recalculate_by_items(bill_id, commit=False)
            self._ensure_paid_allocations_unchanged(bill_id, paid_before)
            session.commit()
        except Exception:
            session.rollback()
            raise

        notifier.broadcast(bill_id, "REFRESH")
        return {"status": "success"}

    def assign_items_batch(self, bill_id: int, batch: BillItemAssignBatch, requester_id: int):
        """Apply a whole multi-select (assign/unassign + shared flags) atomically.

        One transaction, one recalculation, one REFRESH — the router returns the
        updated bill so the client applies it directly instead of fanning out
        into N SSE-triggered refetches (the race that left portions untouched on
        iOS).
        """
        if not batch.ops and not batch.shared:
            # Nothing to hand out must change nothing: below, the bill turns to a
            # split by dishes and every share is worked out again.
            return {"status": "success"}
        session = self.bill_repo.session
        try:
            bill = self.bill_repo.get_by_id_for_update(bill_id)
            if not bill:
                raise HTTPException(status_code=404, detail="Bill not found")
            if bill.status != "open":
                raise HTTPException(status_code=400, detail="Bill is not open")

            is_owner = (bill.owner_id == requester_id)
            if batch.shared and not is_owner:
                raise HTTPException(
                    status_code=403,
                    detail="Only owner can change global item sharing",
                )
            if batch.ops:
                self._ensure_guest_may_pick(bill, is_owner)
            item_ids = sorted(
                {op.item_id for op in batch.ops}
                | {op.item_id for op in batch.shared}
            )
            item_cache: dict[int, BillItem] = {}
            for current_item_id in item_ids:
                item = self.bill_repo.get_item_by_id_for_update(current_item_id)
                if not item or item.bill_id != bill_id:
                    raise HTTPException(status_code=404, detail="Item not found")
                item_cache[current_item_id] = item

            participant_cache = {}
            expanded_ops: list[tuple[BillItemAssignOp, list[int]]] = []
            for op in batch.ops:
                item = item_cache[op.item_id]
                count = max(1, item.count or 1)
                if op.expected_count is not None and count != op.expected_count:
                    self._position_error(
                        409,
                        "POSITION_STALE",
                        "The item quantity changed; refresh the bill and try again",
                        item_id=item.id,
                        expected_count=op.expected_count,
                        actual_count=count,
                    )
                if op.portion_index is None:
                    portions = list(range(count))
                elif 0 <= op.portion_index < count:
                    portions = [op.portion_index]
                elif op.expected_count is not None:
                    self._position_error(
                        422,
                        "POSITION_OUT_OF_RANGE",
                        "portion_index is outside the item quantity",
                        item_id=item.id,
                        portion_index=op.portion_index,
                        actual_count=count,
                    )
                else:
                    raise HTTPException(status_code=400, detail="Invalid portion index")

                participant = participant_cache.get(op.participant_id)
                if participant is None:
                    participant = self.validator.get_participant_or_404(
                        op.participant_id, bill_id
                    )
                    participant_cache[op.participant_id] = participant
                if not is_owner and participant.user_id != requester_id:
                    raise HTTPException(status_code=403, detail="Only owner can assign items to others")
                expanded_ops.append((op, portions))

            initial_rows = {
                (item.id, assignment.participant_id, assignment.portion_index): assignment
                for item in item_cache.values()
                for assignment in item.assignments
            }
            desired = set(initial_rows)
            for op, portions in expanded_ops:
                for portion in portions:
                    key = (op.item_id, op.participant_id, portion)
                    if op.is_assigned:
                        desired.add(key)
                    else:
                        desired.discard(key)

            changed_keys = desired.symmetric_difference(initial_rows)
            paid_targets = sorted({
                participant_id
                for _item_id, participant_id, _portion in changed_keys
                if (
                    participant_cache[participant_id].is_paid
                    and participant_cache[participant_id].user_id != bill.owner_id
                )
            })
            if paid_targets:
                self._position_error(
                    409,
                    "PAID_ASSIGNMENT_LOCKED",
                    "Undo payment before changing this participant's positions",
                    participant_ids=paid_targets,
                )

            paid_before = self._paid_allocations(bill_id)

            # Shared-flag changes apply before the final assignment state, matching
            # the legacy batch contract while keeping validation ahead of mutation.
            shared_state = {}
            for shared_op in batch.shared:
                shared_state[shared_op.item_id] = shared_op.is_shared_globally
            for current_item_id, is_shared in shared_state.items():
                item_cache[current_item_id].is_shared_globally = is_shared
                session.add(item_cache[current_item_id])

            for key in desired - set(initial_rows):
                current_item_id, participant_id, portion = key
                session.add(BillItemAssignment(
                    bill_item_id=current_item_id,
                    participant_id=participant_id,
                    portion_index=portion,
                ))
            for key in set(initial_rows) - desired:
                session.delete(initial_rows[key])

            if bill.split_type != SplitType.BY_ITEMS:
                bill.split_type = SplitType.BY_ITEMS
            session.add(bill)
            session.flush()
            for item in item_cache.values():
                session.expire(item, ["assignments"])
            self.recalculate_by_items(bill_id, commit=False)
            self._ensure_paid_allocations_unchanged(bill_id, paid_before)
            session.commit()
        except Exception:
            session.rollback()
            raise

        notifier.broadcast(bill_id, "REFRESH")
        return {"status": "success"}

    def _recompute_totals_from_items(self, bill_id: int, *, commit: bool = True):
        """Keep the bill total in sync with its items.

        When a bill has items they are the source of truth: total_sum becomes
        the sum of item sums and unallocated is recomputed. This is only ever
        called from add/update/delete item, so "no items" means the last item
        was just deleted — the bill is now empty, so its total, remainder and
        per-person allocations all go to zero (STB: deleting the last item must
        bring the total to 0, not leave the stale sum).
        """
        bill = self.bill_repo.get_by_id(bill_id)
        if not bill:
            return
        items = self.bill_repo.get_items_by_bill_id(bill_id)
        if not items:
            for p in self.bill_repo.get_participants_by_bill_id(bill_id):
                p.allocated_amount = 0
                self.bill_repo.session.add(p)
            bill.total_sum = 0
            bill.unallocated_sum = 0
            self.bill_repo.session.add(bill)
            if commit:
                self.bill_repo.session.commit()
            return

        bill.total_sum = sum(i.item_sum for i in items)
        self.bill_repo.session.add(bill)
        if commit:
            self.bill_repo.session.commit()

        if bill.split_type == SplitType.BY_ITEMS:
            self.recalculate_by_items(bill_id, commit=commit)
        else:
            participants = self.bill_repo.get_participants_by_bill_id(bill_id)
            allocated = sum(p.allocated_amount for p in participants)
            if allocated > bill.total_sum:
                # The bill shrank under hand-set shares. Clamping the remainder
                # at zero left people owing more than the bill; what nobody has
                # paid yet goes back to be shared out again instead.
                for p in participants:
                    if not p.is_paid:
                        p.allocated_amount = 0
                        self.bill_repo.session.add(p)
                allocated = sum(p.allocated_amount for p in participants)
                if allocated > bill.total_sum:
                    # What is paid alone is more than the bill now: someone would
                    # owe more than it costs. The payment is undone first.
                    self._position_error(
                        409,
                        "PAID_ALLOCATION_LOCKED",
                        "Undo payment before changing an affected allocation",
                    )
            bill.unallocated_sum = max(0, bill.total_sum - allocated)
            self.bill_repo.session.add(bill)
            if commit:
                self.bill_repo.session.commit()

    def recalculate_by_items(self, bill_id: int, *, commit: bool = True):
        bill = self.bill_repo.get_by_id(bill_id)
        if not bill or bill.split_type != SplitType.BY_ITEMS:
            return

        participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        if not participants:
            return

        items = self.bill_repo.get_items_by_bill_id(bill_id)

        for p in participants:
            p.allocated_amount = 0

        # Keyed by participant id, so guest seats take part in the split exactly
        # like people with accounts. «Split among all» divides by the seats,
        # which exist for the whole declared headcount (STB-94); a dish nobody
        # took stays unallocated.
        participant_map = {p.id: p for p in participants}

        total_assigned = 0
        for split in TableSplit.of(bill, participants).split_items(items).values():
            for seat_id, amount in split.shares.items():
                participant_map[seat_id].allocated_amount += amount
                total_assigned += amount

        bill.unallocated_sum = bill.total_sum - total_assigned
        
        for p in participants:
            self.bill_repo.session.add(p)
        self.bill_repo.session.add(bill)
        if commit:
            self.bill_repo.session.commit()
