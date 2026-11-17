"""STB-190: bills reference an encrypted payment_methods row instead of storing
the card number in the clear."""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import Bill, PaymentMethod


def _owner(client: TestClient) -> int:
    client.post("/users/", json={"telegram_id": 700, "username": "pm_owner"})
    return 1


def test_payment_details_stored_via_encrypted_method(client: TestClient, session: Session):
    owner = _owner(client)
    resp = client.post(
        "/bills/",
        json={
            "owner_id": owner,
            "total_sum": 100,
            "payment_details": "Card 4321",
            "include_owner": True,
        },
    )
    assert resp.status_code == 200
    bill_id = resp.json()["id"]
    # Response still exposes the plaintext value (resolved from the method).
    assert resp.json()["payment_details"] == "Card 4321"

    # The bill references a method and no longer carries a plaintext column.
    bill = session.get(Bill, bill_id)
    assert bill.payment_method_id is not None
    assert not hasattr(bill, "payment_details")

    # The linked method belongs to the owner and is stored encrypted.
    pm = session.get(PaymentMethod, bill.payment_method_id)
    assert pm.user_id == owner
    assert "Card 4321" not in pm.enc_value  # ciphertext, not the raw value

    # Round-trips on GET.
    got = client.get(f"/bills/{bill_id}?user_id={owner}")
    assert got.json()["payment_details"] == "Card 4321"


def test_same_payment_value_reuses_one_method(client: TestClient, session: Session):
    owner = _owner(client)
    for _ in range(2):
        client.post(
            "/bills/",
            json={
                "owner_id": owner,
                "total_sum": 50,
                "payment_details": "Card 1",
                "include_owner": True,
            },
        )
    methods = session.exec(
        select(PaymentMethod).where(PaymentMethod.user_id == owner)
    ).all()
    assert len(methods) == 1  # the same value is reused, not duplicated


def test_update_payment_details_links_method(client: TestClient, session: Session):
    owner = _owner(client)
    bill_id = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 10, "include_owner": True},
    ).json()["id"]

    resp = client.patch(
        f"/bills/{bill_id}",
        json={"payment_details": "New Card", "user_id": owner},
    )
    assert resp.status_code == 200
    assert resp.json()["payment_details"] == "New Card"
    bill = session.get(Bill, bill_id)
    assert bill.payment_method_id is not None


def test_no_payment_details_leaves_method_null(client: TestClient, session: Session):
    owner = _owner(client)
    bill_id = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 10, "include_owner": True},
    ).json()["id"]
    bill = session.get(Bill, bill_id)
    assert bill.payment_method_id is None
