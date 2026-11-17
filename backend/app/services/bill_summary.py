"""What a bill adds up to, for the people reading about it in a chat.

The picture and the message of a shared bill show the same thing — who owes
what and for which dishes, what nobody has taken, how much is already in — so
both are drawn from this one summary. It follows the by-items allocator: a
seat's total is its allocated amount, and its lines are the shares that make it
up, split per dish exactly as the allocator splits them.
"""
from dataclasses import dataclass, replace
from datetime import datetime

from sqlmodel import Session

from app.models import Bill, BillItem, BillStatus, BillUser, SplitType
from app.repositories.bill_repo import BillRepository
from app.services.pro import ProService
from app.services.item_split import TableSplit
from app.services.payment_link import value_for_method


@dataclass(frozen=True)
class SummaryLine:
    name: str
    # How many of the line's dishes the seat is on; one shared with others is
    # still one, the amount carries the split.
    dishes: int
    amount: int
    # Shared by the whole table: everyone has all of it, so no count is told.
    everyone: bool = False

    @property
    def count(self) -> str | None:
        """«×3» by the dish's name; nothing for a single dish or a shared one."""
        return None if self.everyone or self.dishes == 1 else f"×{self.dishes}"


@dataclass(frozen=True)
class SummarySeat:
    participant_id: int
    # None for an unnamed guest seat: its «Guest N» label belongs to the reader's language.
    name: str | None
    seat_index: int
    amount: int
    is_owner: bool
    is_paid: bool
    lines: tuple[SummaryLine, ...]
    # Whose profile photo the picture shows; None for a seat nobody has claimed.
    telegram_id: int | None = None
    # Nobody sits here yet: the post offers the seat to whoever reads it.
    is_free: bool = False


@dataclass(frozen=True)
class BillSummary:
    title: str | None
    created_at: datetime | None
    currency: str
    total: int
    seats: tuple[SummarySeat, ...]
    unassigned: tuple[SummaryLine, ...]
    unassigned_total: int
    to_collect: int
    collected: int
    payment_details: str | None
    is_closed: bool
    # Kept by someone with Pro: the picture wears the mark.
    pro: bool = False


def seat_name(seat: BillUser) -> str | None:
    user = seat.user
    if user is not None:
        full_name = " ".join(part for part in (user.name, user.surname) if part).strip()
        if full_name:
            return full_name
        if user.username:
            return f"@{user.username}"
    return (seat.guest_name or "").strip() or None


class _Lines:
    """Per-item lines in receipt order, merged as dishes are added to them."""

    def __init__(self) -> None:
        self._by_item: dict[int, list] = {}

    def add(self, item: BillItem, amount: int, dishes: int = 1) -> None:
        line = self._by_item.setdefault(item.id, [item.name, 0, 0, item.is_shared_globally])
        line[1] += dishes
        line[2] += amount

    def lines(self) -> tuple[SummaryLine, ...]:
        return tuple(
            SummaryLine(name, dishes, amount, everyone) for name, dishes, amount, everyone in self._by_item.values()
        )


def _split_items(items: list[BillItem], table: TableSplit) -> tuple[dict[int, _Lines], _Lines]:
    per_seat = {seat_id: _Lines() for seat_id in table.seat_ids}
    unassigned = _Lines()
    splits = table.split_items(items)
    for item in sorted(items, key=lambda item: item.id or 0):
        split = splits[item.id]
        for seat_id, amount in split.shares.items():
            per_seat[seat_id].add(item, amount, split.dishes[seat_id])
        if split.open_dishes:
            unassigned.add(item, split.unassigned, split.open_dishes)
    return per_seat, unassigned


def summarize(
    bill: Bill,
    seats: list[BillUser],
    items: list[BillItem],
    payment_details: str | None,
) -> BillSummary:
    owner_seat = next((seat for seat in seats if seat.user_id == bill.owner_id), None)
    owner_seat_id = owner_seat.id if owner_seat else None
    # A bill nobody has split by hand reads by its dishes, even before the
    # first one is taken; only a manual split has amounts without dishes.
    by_items = bill.split_type == SplitType.BY_ITEMS or all(seat.allocated_amount == 0 for seat in seats)
    per_seat, unassigned = (
        _split_items(items, TableSplit.of(bill, seats))
        if by_items
        else ({}, _Lines())
    )

    # Every seat at the table is listed, an empty one too: the post is also
    # an invitation, and a free seat is what it invites to.
    rows = []
    for seat in seats:
        lines = per_seat[seat.id].lines() if seat.id in per_seat else ()
        rows.append(SummarySeat(
            participant_id=seat.id,
            name=seat_name(seat),
            seat_index=seat.seat_index,
            amount=seat.allocated_amount,
            is_owner=seat.id == owner_seat_id,
            is_paid=seat.is_paid,
            lines=lines,
            telegram_id=seat.user.telegram_id if seat.user else None,
            is_free=seat.user_id is None,
        ))
    # Whoever still owes comes first; the organiser, who owes nobody, closes the list.
    rows.sort(key=lambda row: (row.is_owner, row.seat_index))

    payers = [row for row in rows if not row.is_owner]
    unassigned_lines = unassigned.lines()
    return BillSummary(
        title=(bill.title or "").strip() or None,
        created_at=bill.created_at,
        currency=bill.currency,
        total=bill.total_sum,
        seats=tuple(rows),
        unassigned=unassigned_lines,
        unassigned_total=(
            sum(line.amount for line in unassigned_lines) if by_items else max(0, bill.unallocated_sum)
        ),
        # Everything the owner is owed, as the app counts what is left to
        # collect: the whole bill but the owner's own share, taken or not yet.
        to_collect=max(0, bill.total_sum - (owner_seat.allocated_amount if owner_seat else 0)),
        collected=sum(row.amount for row in payers if row.is_paid),
        payment_details=(payment_details or "").strip() or None,
        is_closed=bill.status == BillStatus.CLOSED,
    )


def summary_for(session: Session, bill: Bill) -> BillSummary:
    repo = BillRepository(session)
    summary = summarize(
        bill,
        repo.get_participants_by_bill_id(bill.id),
        repo.get_items_by_bill_id(bill.id),
        value_for_method(session, bill.payment_method_id),
    )
    return replace(summary, pro=ProService(session).is_pro(bill.owner_id, datetime.utcnow()))
