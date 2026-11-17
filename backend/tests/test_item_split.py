from app.models import BillItem, BillItemAssignment
from app.services.item_split import TableSplit, split_in_steps

OWNER, A, B, C, D, E, F = range(1, 8)
SUM = 100
UZS = TableSplit((OWNER, A, B, C, D, E, F), OWNER, SUM)
USD = TableSplit((OWNER, A, B, C, D, E, F), OWNER, 1)


def _item(item_sum: int, count: int, dishes: dict[int, list[int]], shared=False) -> BillItem:
    return BillItem(
        id=1, bill_id=1, name="Raketki", price=item_sum // count, count=count, item_sum=item_sum,
        is_shared_globally=shared,
        assignments=[
            BillItemAssignment(bill_item_id=1, participant_id=seat_id, portion_index=portion)
            for portion, seat_ids in dishes.items()
            for seat_id in seat_ids
        ],
    )


def test_every_dish_shared_by_the_same_guests_splits_the_line_evenly():
    item = _item(105_000 * SUM, 3, {0: [A, B, C], 1: [A, B, C], 2: [A, B, C]})

    split = UZS.split_items([item])[1]

    assert split.shares == {A: 35_000 * SUM, B: 35_000 * SUM, C: 35_000 * SUM}
    assert split.dishes == {A: 3, B: 3, C: 3}
    assert split.unassigned == 0


def test_dishes_with_different_eaters_keep_their_rounding_to_themselves():
    item = _item(105_000 * SUM, 3, {0: [OWNER, A, B], 1: [C, D, E], 2: [C, D, E]})

    split = UZS.split_items([item])[1]

    assert split.shares[OWNER] + split.shares[A] + split.shares[B] == 35_000 * SUM
    assert split.shares[C] + split.shares[D] + split.shares[E] == 70_000 * SUM


def test_the_owner_never_carries_rounding_of_a_dish_they_are_not_on():
    split = UZS.split_items([_item(100_000 * SUM, 1, {0: [A, B, C]})])[1]

    assert split.shares == {A: 33_334 * SUM, B: 33_333 * SUM, C: 33_333 * SUM}


def test_the_owner_takes_the_larger_part_of_a_dish_they_share():
    split = UZS.split_items([_item(100_000 * SUM, 1, {0: [A, OWNER, B]})])[1]

    assert split.shares == {OWNER: 33_334 * SUM, A: 33_333 * SUM, B: 33_333 * SUM}


def test_dishes_of_a_line_in_sums_are_whole_sums():
    assert split_in_steps(100_000 * SUM, 3, SUM) == [33_334 * SUM, 33_333 * SUM, 33_333 * SUM]

    split = UZS.split_items([_item(100_000 * SUM, 3, {1: [A]})])[1]

    assert split.shares == {A: 33_333 * SUM}
    assert (split.unassigned, split.open_dishes) == (66_667 * SUM, 2)


def test_odd_tiyins_stay_with_one_eater_and_everyone_else_pays_whole_sums():
    split = UZS.split_items([_item(-1_234_560, 1, {0: [A, OWNER, B]})])[1]

    assert split.shares == {OWNER: -411_460, A: -411_500, B: -411_600}
    assert sum(split.shares.values()) == -1_234_560


def test_cents_stay_in_a_currency_that_pays_them():
    split = USD.split_items([_item(10_000, 1, {0: [A, B, C]})])[1]

    assert split.shares == {A: 3_334, B: 3_333, C: 3_333}


def test_a_shared_line_is_split_among_every_seat_with_the_owner_first():
    table = TableSplit((A, OWNER, B), OWNER, SUM)

    split = table.split_items([_item(10_000 * SUM, 2, {}, shared=True)])[1]

    assert split.shares == {OWNER: 3_334 * SUM, A: 3_333 * SUM, B: 3_333 * SUM}
    assert split.dishes == {A: 2, OWNER: 2, B: 2}


def test_split_evenly_follows_table_order_without_the_owner():
    assert UZS.split_evenly(200 * SUM, [C, A, B]) == {A: 67 * SUM, B: 67 * SUM, C: 66 * SUM}


def test_golden_cases_shared_with_the_frontend():
    # The same cases are asserted in frontend/src/lib/utils/itemSplit.test.ts.
    assert UZS.split_items([_item(100_000 * SUM, 3, {1: [A]})])[1].shares == {A: 33_333 * SUM}
    assert UZS.split_items([_item(50_000 * SUM, 2, {0: [C, D, E], 1: [A, B, OWNER]})])[1].shares == {
        OWNER: 8_334 * SUM, A: 8_333 * SUM, B: 8_333 * SUM, C: 8_334 * SUM, D: 8_333 * SUM, E: 8_333 * SUM,
    }


def test_the_same_eaters_on_separate_lines_are_shared_once_and_each_line_adds_up():
    lines = [
        BillItem(
            id=item_id, bill_id=1, name="Raketka", price=35_000 * SUM, count=1, item_sum=35_000 * SUM,
            assignments=[BillItemAssignment(bill_item_id=item_id, participant_id=seat_id, portion_index=0) for seat_id in (A, B, C)],
        )
        for item_id in (1, 2, 3)
    ]

    splits = UZS.split_items(lines)

    totals = {seat_id: sum(split.shares[seat_id] for split in splits.values()) for seat_id in (A, B, C)}
    assert totals == {A: 35_000 * SUM, B: 35_000 * SUM, C: 35_000 * SUM}
    assert all(sum(split.shares.values()) == 35_000 * SUM for split in splits.values())
