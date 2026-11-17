import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.models import Bill, BillItem, BillUser, ReceiptTask, ReceiptTaskStatus
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.worker import _enrich_bill
from tests.conftest import auth_headers


def _bill_with_a_paid_guest(client):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o"}).json()["id"]
    guest = client.post("/users/", json={"telegram_id": 2, "username": "g"}).json()["id"]
    bid = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "include_owner": True, "expected_people": 2},
    ).json()["id"]
    item = client.post(f"/bills/{bid}/items", json={"name": "Plov", "price": 100, "count": 1}).json()
    seat = next(
        p for p in client.get(f"/bills/{bid}?user_id={owner}").json()["participants"]
        if p["user_id"] is None
    )
    client.post(f"/bills/{bid}/seats/{seat['id']}/claim", json={"user_id": guest})
    client.post(
        f"/bills/{bid}/items/{item['id']}/assign",
        json={"participant_id": seat["id"], "is_assigned": True},
        headers=auth_headers(2),
    )
    paid = client.post(f"/bills/{bid}/participants/{seat['id']}/payment", json={"is_paid": True, "user_id": guest})
    assert paid.status_code == 200
    return owner, bid, seat["id"]


def _scan_into(session, owner, bid, items):
    task = ReceiptTask(user_id=owner, bill_id=bid, status=ReceiptTaskStatus.STRUCTURING)
    session.add(task)
    session.commit()
    _enrich_bill(
        session, BillRepository(session), UserRepository(session), task,
        session.get(Bill, bid), {"title": "Coffee", "total_sum": 20, "items": items},
    )


def test_a_receipt_that_would_change_a_paid_share_is_refused(client, session):
    """A shared service line splits across every seat, the paid one included."""
    owner, bid, seat_id = _bill_with_a_paid_guest(client)

    with pytest.raises(HTTPException) as refused:
        _scan_into(session, owner, bid, [{"name": "Service", "count": 1, "amount": 20, "is_shared_globally": True}])
    session.rollback()

    assert refused.value.detail["code"] == "PAID_ALLOCATION_LOCKED"
    assert session.get(BillUser, seat_id).allocated_amount == 10000
    assert session.exec(select(BillItem.name).where(BillItem.bill_id == bid)).all() == ["Plov"]


def test_a_receipt_that_leaves_paid_shares_alone_goes_in(client, session):
    owner, bid, seat_id = _bill_with_a_paid_guest(client)

    _scan_into(session, owner, bid, [{"name": "Latte", "count": 1, "amount": 20}])

    assert session.get(BillUser, seat_id).allocated_amount == 10000
    assert session.get(Bill, bid).total_sum == 12000
