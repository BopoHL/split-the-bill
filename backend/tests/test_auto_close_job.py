from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import select

from app.jobs import auto_close
from app.models import Bill, BillStatus, BillUser


NOW = datetime(2026, 8, 14, 12, 0)


def _bill_with_guest_share(client: TestClient, session, *, unallocated=False):
    owner = client.post(
        "/users/", json={"telegram_id": 930, "username": "owner"}
    ).json()["id"]
    guest = client.post(
        "/users/", json={"telegram_id": 931, "username": "guest"}
    ).json()["id"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner,
            "total_sum": 100,
            "include_owner": True,
            "expected_people": 2,
            "title": "Auto-close job",
        },
    ).json()
    bill_id = bill["id"]
    seat = next(
        p for p in client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]
        if p["user_id"] is None
    )
    client.post(f"/bills/{bill_id}/seats/{seat['id']}/claim", json={"user_id": guest})
    client.post(
        f"/bills/{bill_id}/assign-amount",
        json={"participant_id": seat["id"], "allocated_amount": 50 if unallocated else 100},
    )
    paid = client.post(
        f"/bills/{bill_id}/participants/{seat['id']}/payment",
        json={"is_paid": True, "user_id": guest},
    )
    assert paid.status_code == 200

    bill_row = session.get(Bill, bill_id)
    bill_row.created_at = NOW
    guest_row = session.get(BillUser, seat["id"])
    guest_row.updated_at = NOW - timedelta(minutes=20)
    session.add(bill_row)
    session.add(guest_row)
    session.commit()
    return bill_id, owner, seat["id"]


def test_new_fully_allocated_bill_closes_after_payment_grace(client: TestClient, session):
    bill_id, owner, _ = _bill_with_guest_share(client, session)

    assert auto_close.run(session, NOW) == 1

    bill = session.get(Bill, bill_id)
    assert bill.status == BillStatus.CLOSED
    owner_seat = session.exec(
        select(BillUser).where(BillUser.bill_id == bill_id, BillUser.user_id == owner)
    ).one()
    assert owner_seat.is_paid is True


def test_a_bill_closed_on_its_own_is_counted_for_its_owner(client: TestClient, session, product_events):
    bill_id, owner, _ = _bill_with_guest_share(client, session)

    auto_close.run(session, NOW)

    assert [sent for sent in product_events if sent[0] == "bill_closed"] == [
        ("bill_closed", str(owner), {"surface": "server", "bill_id": bill_id, "auto": True}),
    ]


def test_new_bill_waits_until_everything_is_allocated(client: TestClient, session):
    bill_id, _, _ = _bill_with_guest_share(client, session, unallocated=True)

    assert auto_close.run(session, NOW) == 0
    assert session.get(Bill, bill_id).status == BillStatus.OPEN


def test_old_bill_can_close_even_with_unallocated_remainder(client: TestClient, session):
    bill_id, _, _ = _bill_with_guest_share(client, session, unallocated=True)
    bill = session.get(Bill, bill_id)
    bill.created_at = auto_close._local_day_start(NOW) - timedelta(seconds=1)
    session.add(bill)
    session.commit()

    assert auto_close.run(session, NOW) == 1
    assert session.get(Bill, bill_id).status == BillStatus.CLOSED


def test_auto_close_waits_out_the_quiet_period_after_the_last_payment(
    client: TestClient, session
):
    bill_id, _, seat_id = _bill_with_guest_share(client, session)
    seat = session.get(BillUser, seat_id)
    seat.updated_at = NOW - timedelta(minutes=14)
    session.add(seat)
    session.commit()

    assert auto_close.run(session, NOW) == 0
    assert session.get(Bill, bill_id).status == BillStatus.PAID


def test_changing_what_a_payer_owes_restarts_the_clock(client: TestClient, session):
    """The table is still moving — someone re-assigned a dish after everyone paid."""
    bill_id, _, seat_id = _bill_with_guest_share(client, session)
    seat = session.get(BillUser, seat_id)
    seat.updated_at = NOW - timedelta(seconds=1)
    session.add(seat)
    session.commit()

    assert auto_close.run(session, NOW) == 0

    seat.updated_at = NOW - timedelta(minutes=16)
    session.add(seat)
    session.commit()
    assert auto_close.run(session, NOW) == 1


def test_a_bill_with_an_empty_seat_still_owing_stays_open(client: TestClient, session):
    """An empty seat is a payer too; its unpaid share keeps the bill open."""
    bill_id, _, _ = _bill_with_guest_share(client, session)
    session.add(BillUser(bill_id=bill_id, seat_index=2, allocated_amount=5000))
    session.commit()

    assert auto_close.run(session, NOW) == 0
    assert session.get(Bill, bill_id).status != BillStatus.CLOSED
