"""A shared («split among all») item divides by the number of seats.

Seats are created for the whole declared headcount when the bill is made, so
every share lands on somebody from the start — including guests nobody has
claimed yet. This replaces STB-94, where absent people's shares had to be left
unallocated because they had no row to sit in.
"""
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.services.bill_item_service import BillItemService
from app.models import User, Bill, BillUser, BillItem, SplitType, BillStatus


def _bill_with_shared_item(session, expected_people, item_sum=10000, guest_seats=0):
    owner = User(telegram_id=1, username="o")
    p2 = User(telegram_id=2, username="p2")
    session.add(owner)
    session.add(p2)
    session.commit()
    session.refresh(owner)
    session.refresh(p2)

    bill = Bill(
        owner_id=owner.id,
        total_sum=item_sum,
        unallocated_sum=item_sum,
        split_type=SplitType.BY_ITEMS,
        expected_people=expected_people,
        status=BillStatus.OPEN,
    )
    session.add(bill)
    session.commit()
    session.refresh(bill)

    session.add(BillUser(bill_id=bill.id, user_id=owner.id, seat_index=0, allocated_amount=0))
    session.add(BillUser(bill_id=bill.id, user_id=p2.id, seat_index=1, allocated_amount=0))
    for i in range(guest_seats):
        session.add(BillUser(bill_id=bill.id, seat_index=2 + i, allocated_amount=0))
    session.add(
        BillItem(
            bill_id=bill.id, name="Service", price=item_sum, count=1,
            item_sum=item_sum, is_shared_globally=True,
        )
    )
    session.commit()
    return bill.id


def test_shared_item_divides_among_seats(session):
    # Four seats — the owner, one claimed guest and two still unclaimed. Each
    # owes 10000/4 = 2500 and nothing is left over.
    bill_id = _bill_with_shared_item(session, expected_people=4, guest_seats=2)
    BillItemService(BillRepository(session), UserRepository(session)).recalculate_by_items(bill_id)

    repo = BillRepository(session)
    seats = repo.get_participants_by_bill_id(bill_id)
    assert len(seats) == 4
    for p in seats:
        assert p.allocated_amount == 2500
    assert repo.get_by_id(bill_id).unallocated_sum == 0


def test_unclaimed_seats_still_carry_their_share(session):
    """A guest nobody has claimed owes their part — that's the point of seats."""
    bill_id = _bill_with_shared_item(session, expected_people=4, guest_seats=2)
    BillItemService(BillRepository(session), UserRepository(session)).recalculate_by_items(bill_id)

    guests = [
        p for p in BillRepository(session).get_participants_by_bill_id(bill_id)
        if p.user_id is None
    ]
    assert len(guests) == 2
    assert all(g.allocated_amount == 2500 for g in guests)
