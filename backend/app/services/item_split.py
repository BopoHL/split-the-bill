"""How the money of a bill is owed by the seats at its table.

The allocator, the bill summary, the seat preview and the remainder split all
go through `TableSplit`, so the amounts a seat sees on its dishes always add up
to what it is asked to pay. The frontend mirrors this in itemSplit.ts.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import Iterable

from app.models import Bill, BillItem, BillUser
from app.utils.currency import share_step


@dataclass(frozen=True)
class ItemSplit:
    shares: dict[int, int]
    dishes: dict[int, int]
    unassigned: int
    open_dishes: int


def split_in_steps(total: int, parts: int, step: int) -> list[int]:
    """`total` cut into `parts` as even as whole steps allow, larger parts first.

    Tiyins that don't make up a whole step stay with the first part.
    """
    steps, odd = divmod(total, step)
    base, extra = divmod(steps, parts)
    return [(base + (1 if index < extra else 0)) * step + (odd if index == 0 else 0) for index in range(parts)]


def dish_value(item: BillItem, portion_index: int, step: int) -> int:
    count = max(1, item.count or 1)
    return split_in_steps(item.item_sum, count, step)[portion_index]


@dataclass(frozen=True)
class TableSplit:
    seat_ids: tuple[int, ...]
    owner_seat_id: int | None
    step: int

    @classmethod
    def of(cls, bill: Bill, seats: list[BillUser]) -> "TableSplit":
        """`seats` in table order."""
        owner_seat_id = next((seat.id for seat in seats if seat.user_id == bill.owner_id), None)
        return cls(tuple(seat.id for seat in seats), owner_seat_id, share_step(bill.currency))

    @cached_property
    def _payment_order(self) -> dict[int, int]:
        return {seat_id: -1 if seat_id == self.owner_seat_id else index for index, seat_id in enumerate(self.seat_ids)}

    def split_evenly(self, total: int, among: Iterable[int]) -> dict[int, int]:
        """`total` shared equally; the owner, when among them, takes the larger part."""
        recipients = sorted(among, key=self._payment_order.__getitem__)
        return dict(zip(recipients, split_in_steps(total, len(recipients), self.step)))

    def _eaters(self, item: BillItem) -> dict[int, frozenset[int]]:
        count = max(1, item.count or 1)
        if item.is_shared_globally:
            return {portion_index: frozenset(self.seat_ids) for portion_index in range(count)} if self.seat_ids else {}
        eaters: dict[int, set[int]] = defaultdict(set)
        for assignment in item.assignments:
            if assignment.participant_id in self._payment_order and 0 <= assignment.portion_index < count:
                eaters[assignment.portion_index].add(assignment.participant_id)
        return {portion_index: frozenset(seat_ids) for portion_index, seat_ids in eaters.items()}

    def split_items(self, items: Iterable[BillItem]) -> dict[int, ItemSplit]:
        """What each seat owes for each line, by item id.

        Every dish eaten by the same people, on whatever line, is added up and
        shared once: three dishes shared by the same three guests come to a
        third each, whether the receipt prints them as one line or three, and
        dishes eaten by different people never shift rounding onto each other.
        A group's shares are then laid back over its lines in receipt order,
        so each line still adds up to its own sum.
        """
        ordered = sorted(items, key=lambda item: item.id or 0)
        groups: dict[frozenset[int], dict[int, int]] = defaultdict(lambda: defaultdict(int))
        dishes: dict[int, Counter[int]] = defaultdict(Counter)
        claimed: dict[int, tuple[int, int]] = {}
        for item in ordered:
            count = max(1, item.count or 1)
            values = split_in_steps(item.item_sum, count, self.step)
            eaters = self._eaters(item)
            for portion_index, seat_ids in eaters.items():
                groups[seat_ids][item.id] += values[portion_index]
                dishes[item.id].update(seat_ids)
            claimed[item.id] = (sum(values[portion_index] for portion_index in eaters), len(eaters))

        shares: dict[int, Counter[int]] = defaultdict(Counter)
        for seat_ids, lines in groups.items():
            settled = dict.fromkeys(seat_ids, 0)
            running = 0
            for item_id, value in lines.items():
                running += value
                cumulative = self.split_evenly(running, seat_ids)
                for seat_id in seat_ids:
                    shares[item_id][seat_id] += cumulative[seat_id] - settled[seat_id]
                settled = cumulative

        return {
            item.id: ItemSplit(
                dict(shares[item.id]),
                dict(dishes[item.id]),
                item.item_sum - claimed[item.id][0],
                max(1, item.count or 1) - claimed[item.id][1],
            )
            for item in ordered
        }
