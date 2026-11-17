from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Bill, BillStatus
from tests.conftest import ANONYMOUS, auth_headers


def _owner_and_bill(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "owner"}).json()["id"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner, "total_sum": 100, "title": "T",
            "include_owner": True, "expected_people": 2,
        },
    ).json()
    return owner, bill


def test_bill_exposes_public_token(client: TestClient):
    owner, bill = _owner_and_bill(client)
    assert bill["public_token"]
    detail = client.get(f"/bills/{bill['id']}?user_id={owner}").json()
    assert detail["public_token"] == bill["public_token"]


def test_get_bill_requires_membership(client: TestClient):
    owner, bill = _owner_and_bill(client)
    outsider = client.post("/users/", json={"telegram_id": 2, "username": "x"}).json()["id"]
    bill_id = bill["id"]

    assert client.get(f"/bills/{bill_id}?user_id={owner}").status_code == 200
    # An outsider cannot read someone else's bill (no enumeration by id).
    assert client.get(f"/bills/{bill_id}?user_id={outsider}").status_code == 403
    # Identity comes from the signed header, so an anonymous caller is refused.
    assert client.get(f"/bills/{bill_id}", headers=ANONYMOUS).status_code == 401


def test_join_by_token(client: TestClient):
    owner, bill = _owner_and_bill(client)
    joiner = client.post("/users/", json={"telegram_id": 2, "username": "joiner"}).json()["id"]

    # A newcomer must pick a seat — the bill was laid out with one per person.
    r = client.post(
        "/bills/join-by-token", json={"token": bill["public_token"], "user_id": joiner}
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "SEAT_REQUIRED"

    seats = client.get(
        f"/bills/public/{bill['public_token']}/seats", headers=auth_headers(2)
    ).json()["seats"]
    free = next(s for s in seats if not s["is_taken"])
    claimed = client.post(
        f"/bills/{bill['id']}/seats/{free['id']}/claim", json={"user_id": joiner}
    )
    assert claimed.status_code == 200

    # Having joined, the user can now view the bill.
    assert client.get(f"/bills/{bill['id']}?user_id={joiner}").status_code == 200

    # An unknown token is rejected.
    assert (
        client.post(
            "/bills/join-by-token", json={"token": "does-not-exist", "user_id": joiner}
        ).status_code
        == 404
    )


def test_join_closed_bill(client: TestClient, session: Session):
    """STB-230: a newcomer can't join a closed bill (gets a clear 409 the client
    turns into a dedicated screen), but an existing participant still gets back in."""
    owner, bill = _owner_and_bill(client)
    joiner = client.post("/users/", json={"telegram_id": 2, "username": "joiner"}).json()["id"]

    stored = session.get(Bill, bill["id"])
    stored.status = BillStatus.CLOSED
    session.add(stored)
    session.commit()

    r = client.post(
        "/bills/join-by-token", json={"token": bill["public_token"], "user_id": joiner}
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "Bill is closed"

    # The owner is already a participant, so the invite link just lets them back in.
    r_owner = client.post(
        "/bills/join-by-token", json={"token": bill["public_token"], "user_id": owner}
    )
    assert r_owner.status_code == 200
    assert r_owner.json()["bill_id"] == bill["id"]


def test_owner_changes_bill_currency(client: TestClient):
    """STB-213: the owner can re-denominate the bill; bad codes and non-owners are rejected."""
    owner, bill = _owner_and_bill(client)

    r = client.patch(f"/bills/{bill['id']}", json={"currency": "usd", "user_id": owner})
    assert r.status_code == 200
    assert r.json()["currency"] == "usd"

    # An unknown currency code is rejected.
    assert (
        client.patch(
            f"/bills/{bill['id']}", json={"currency": "xxx", "user_id": owner}
        ).status_code
        == 400
    )

    # Only the owner may change the currency.
    outsider = client.post("/users/", json={"telegram_id": 3, "username": "x"}).json()["id"]
    assert (
        client.patch(
            f"/bills/{bill['id']}", json={"currency": "rub", "user_id": outsider}
        ).status_code
        == 403
    )
