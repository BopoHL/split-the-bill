"""A seat remembers when it was marked paid, so analytics can say how fast
people settle up."""
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import BillUser


def test_marking_a_seat_paid_records_when_and_unmarking_forgets(client: TestClient, session: Session):
    owner = client.post("/users/", json={"telegram_id": 960, "username": "owner"}).json()["id"]
    bob = client.post("/users/", json={"telegram_id": 961, "username": "bob"}).json()["id"]
    bill_id = client.post("/bills/", json={"owner_id": owner, "total_sum": 100, "include_owner": True}).json()["id"]
    client.post(f"/bills/{bill_id}/participants", json={"user_id": bob})
    seat_id = next(p["id"] for p in client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"] if p["user_id"] == bob)
    client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": seat_id, "allocated_amount": 50.0})

    client.post(f"/bills/{bill_id}/participants/{seat_id}/payment", json={"is_paid": True, "user_id": bob})
    session.expire_all()
    assert session.get(BillUser, seat_id).paid_at is not None

    client.post(f"/bills/{bill_id}/participants/{seat_id}/payment", json={"is_paid": False, "user_id": bob})
    session.expire_all()
    assert session.get(BillUser, seat_id).paid_at is None
