
from app.models import Bill, BillItem, BillItemAssignment, BillStatus, BillUser, SplitType, User
from app.services.bill_summary import SummaryLine, summarize


def _bill(**overrides) -> Bill:
    values = dict(id=1, owner_id=10, total_sum=0, title="Dinner", split_type=SplitType.BY_ITEMS, currency="uzs")
    values.update(overrides)
    return Bill(**values)


def _seat(seat_id: int, user_id: int | None, name: str | None, amount: int, *, paid=False, index=None, guest=None) -> BillUser:
    user = User(id=user_id, telegram_id=user_id * 100, name=name) if user_id else None
    return BillUser(
        id=seat_id, bill_id=1, user_id=user_id, user=user, guest_name=guest,
        seat_index=seat_id - 1 if index is None else index, allocated_amount=amount, is_paid=paid,
    )


def _item(item_id: int, name: str, item_sum: int, count=1, dishes: dict[int, list[int]] | None = None, shared=False) -> BillItem:
    assignments = [
        BillItemAssignment(bill_item_id=item_id, participant_id=seat_id, portion_index=portion)
        for portion, seat_ids in (dishes or {}).items()
        for seat_id in seat_ids
    ]
    return BillItem(
        id=item_id, bill_id=1, name=name, price=item_sum // count, count=count,
        item_sum=item_sum, is_shared_globally=shared, assignments=assignments,
    )


def test_seats_carry_their_dishes_and_whatever_nobody_took_stays_apart():
    seats = [_seat(1, 10, "Leonid", 1_010_000), _seat(2, 20, "Alice", 320_000, paid=True), _seat(3, 30, "Bob", 1_160_000)]
    items = [
        _item(1, "Samsa", 480_000, count=4, dishes={0: [2], 1: [2], 2: [3]}),
        _item(2, "Plov", 1_010_000, dishes={0: [1]}),
        _item(3, "Shashlik", 840_000, count=3, dishes={0: [3], 1: [3]}),
        _item(4, "Tea", 80_000, dishes={0: [2]}),
    ]

    summary = summarize(_bill(total_sum=2_410_000), seats, items, " 8600 1234 5678 9012 ")

    assert [(seat.name, seat.amount, seat.is_owner, seat.is_paid) for seat in summary.seats] == [
        ("Alice", 320_000, False, True),
        ("Bob", 1_160_000, False, False),
        ("Leonid", 1_010_000, True, False),
    ]
    assert summary.seats[0].lines == (SummaryLine("Samsa", 2, 240_000), SummaryLine("Tea", 1, 80_000))
    assert summary.seats[1].lines == (SummaryLine("Samsa", 1, 120_000), SummaryLine("Shashlik", 2, 560_000))
    assert summary.unassigned == (SummaryLine("Samsa", 1, 120_000), SummaryLine("Shashlik", 1, 280_000))
    assert summary.unassigned_total == 400_000
    # The whole bill but the owner's own share, whether anyone has taken it yet or not.
    assert (summary.to_collect, summary.collected) == (1_400_000, 320_000)
    assert summary.payment_details == "8600 1234 5678 9012"
    assert summary.is_closed is False


def test_dishes_shared_by_the_same_seats_even_out_their_odd_cents_across_lines():
    seats = [_seat(1, 10, "Leonid", 34), _seat(2, 20, "Alice", 33)]
    items = [_item(1, "Bread", 101, count=2, dishes={0: [1, 2]}), _item(2, "Service", 15, shared=True)]

    summary = summarize(_bill(currency="usd"), seats, items, None)

    alice, leonid = summary.seats
    assert alice.lines == (SummaryLine("Bread", 1, 25), SummaryLine("Service", 1, 8, everyone=True))
    assert leonid.lines == (SummaryLine("Bread", 1, 26), SummaryLine("Service", 1, 7, everyone=True))
    assert summary.unassigned == (SummaryLine("Bread", 1, 50),)


def test_a_seat_counts_the_dishes_it_is_on_and_a_shared_line_is_not_counted():
    seats = [_seat(1, 10, "Leonid", 0), _seat(2, 20, "Alice", 0), _seat(3, 30, "Bob", 0)]
    items = [
        _item(1, "Beer", 90_000, count=3, dishes={0: [1, 2, 3], 1: [1, 2, 3], 2: [1, 2, 3]}),
        _item(2, "Bread", 30_000, count=2, shared=True),
    ]

    summary = summarize(_bill(), seats, items, None)

    beer, bread = summary.seats[0].lines
    assert (beer.dishes, beer.count) == (3, "×3")
    assert (bread.everyone, bread.count) == (True, None)


def test_every_seat_is_listed_empty_ones_too_and_unnamed_guests_keep_their_seat():
    seats = [
        _seat(1, 10, "Leonid", 0),
        _seat(2, None, None, 50_000, index=3),
        _seat(3, None, None, 0, index=4, guest="Rustam"),
        _seat(4, None, None, 10_000, index=5, guest="  Dilya "),
    ]

    summary = summarize(_bill(), seats, [_item(1, "Soup", 60_000, count=2, dishes={0: [2], 1: [4]})], None)

    assert [(seat.name, seat.seat_index, seat.amount) for seat in summary.seats] == [
        (None, 3, 50_000), ("Rustam", 4, 0), ("Dilya", 5, 10_000), ("Leonid", 0, 0),
    ]


def test_a_fresh_bill_lists_its_dishes_as_not_taken_yet():
    summary = summarize(
        _bill(split_type=SplitType.MANUAL, total_sum=80_000, unallocated_sum=80_000),
        [_seat(1, 10, "Leonid", 0)],
        [_item(1, "Soup", 80_000, count=2)],
        None,
    )

    assert [(seat.name, seat.lines) for seat in summary.seats] == [("Leonid", ())]
    assert (summary.unassigned, summary.unassigned_total) == ((SummaryLine("Soup", 2, 80_000),), 80_000)
    assert summary.to_collect == 80_000


def test_a_manual_split_shows_amounts_and_the_unallocated_rest_without_dishes():
    seats = [_seat(1, 10, "Leonid", 0), _seat(2, 20, "Alice", 50_000)]

    summary = summarize(
        _bill(split_type=SplitType.MANUAL, total_sum=80_000, unallocated_sum=30_000, status=BillStatus.CLOSED),
        seats,
        [_item(1, "Soup", 80_000)],
        None,
    )

    assert [(seat.name, seat.lines) for seat in summary.seats] == [("Alice", ()), ("Leonid", ())]
    assert (summary.unassigned, summary.unassigned_total) == ((), 30_000)
    assert summary.is_closed is True
