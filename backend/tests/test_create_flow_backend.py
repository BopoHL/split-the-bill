"""STB-87 backend foundation: expected_people on bills + scan cancellation."""
from fastapi.testclient import TestClient

from app.models import ReceiptTask, ReceiptTaskStatus
from tests.conftest import auth_headers


def test_create_bill_persists_expected_people(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "expected_people": 5}
    ).json()
    assert bill["expected_people"] == 5
    detail = client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()
    assert detail["expected_people"] == 5


def test_create_bill_expected_people_optional(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 2, "username": "o2"}).json()
    bill = client.post("/bills/", json={"owner_id": owner["id"], "total_sum": 50}).json()
    assert bill["expected_people"] is None


# --- currency binding ---------------------------------------------------

def test_create_bill_binds_explicit_currency(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 40, "username": "cur1"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "currency": "usd"}
    ).json()
    assert bill["currency"] == "usd"
    detail = client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()
    assert detail["currency"] == "usd"


def test_create_bill_defaults_currency_to_uzs(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 41, "username": "cur2"}).json()
    # Omitted and invalid both fall back to the default.
    b1 = client.post("/bills/", json={"owner_id": owner["id"], "total_sum": 10}).json()
    b2 = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 10, "currency": "xyz"}
    ).json()
    assert b1["currency"] == "uzs"
    assert b2["currency"] == "uzs"


def test_create_bill_falls_back_to_owner_setting(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 42, "username": "cur3"}).json()
    client.patch(f"/users/{owner['id']}/settings", json={"currency": "rub"})
    # No currency in the payload → use the owner's saved setting.
    bill = client.post("/bills/", json={"owner_id": owner["id"], "total_sum": 100}).json()
    assert bill["currency"] == "rub"


def test_settings_currency_change_does_not_redenominate_existing_bill(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 43, "username": "cur4"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "currency": "usd"}
    ).json()
    # The owner later switches their default currency.
    client.patch(f"/users/{owner['id']}/settings", json={"currency": "rub"})
    detail = client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()
    # The existing bill keeps the currency it was created with.
    assert detail["currency"] == "usd"


def test_cancel_in_flight_task(client: TestClient, session):
    uploader = client.post(
        "/users/", json={"telegram_id": 71, "username": "c1"}
    ).json()["id"]
    task = ReceiptTask(
        user_id=uploader, filename="x.jpg", status=ReceiptTaskStatus.PROCESSING
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    resp = client.post(f"/receipts/tasks/{task.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_completed_task_is_noop(client: TestClient, session):
    uploader = client.post(
        "/users/", json={"telegram_id": 72, "username": "c2"}
    ).json()["id"]
    task = ReceiptTask(
        user_id=uploader, filename="x.jpg", status=ReceiptTaskStatus.COMPLETED
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    resp = client.post(f"/receipts/tasks/{task.id}/cancel")
    assert resp.status_code == 200
    # A finished scan keeps its bill; cancelling must not rewrite it.
    assert resp.json()["status"] == "completed"


def test_cancel_missing_task_404(client: TestClient):
    client.post("/users/", json={"telegram_id": 73, "username": "c3"})
    assert (
        client.post("/receipts/tasks/999999/cancel", headers=auth_headers(73)).status_code
        == 404
    )


def test_cancel_deletes_provisional_bill(client: TestClient, session):
    # A scan is uploaded → a provisional bill is created up front and the task
    # points at it. Cancelling the scan must delete that still-empty bill.
    owner = client.post("/users/", json={"telegram_id": 60, "username": "cb"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 0, "include_owner": True}
    ).json()
    task = ReceiptTask(
        user_id=owner["id"],
        filename="x.jpg",
        status=ReceiptTaskStatus.PROCESSING,
        bill_id=bill["id"],
        owns_bill=True,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    resp = client.post(f"/receipts/tasks/{task.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    # The provisional bill is gone (404).
    assert client.get(f"/bills/{bill['id']}?user_id={owner['id']}").status_code == 404


def test_cancel_keeps_the_bill_a_scan_was_added_to(client: TestClient, session):
    # A receipt scanned INTO an existing bill: giving up on the scan (the phase
    # timeout, or the Abort button) must not take the bill — with its items and
    # the people already on it — down with the receipt.
    owner = client.post("/users/", json={"telegram_id": 61, "username": "keep"}).json()
    bill = client.post(
        "/bills/",
        json={"owner_id": owner["id"], "total_sum": 0, "include_owner": True, "expected_people": 3},
    ).json()
    client.post(f"/bills/{bill['id']}/items", json={"name": "Plov", "price": 50, "count": 1})
    task = ReceiptTask(
        user_id=owner["id"],
        filename="y.jpg",
        status=ReceiptTaskStatus.STRUCTURING,
        bill_id=bill["id"],
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    resp = client.post(f"/receipts/tasks/{task.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    detail = client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()
    assert [item["name"] for item in detail["items"]] == ["Plov"]
    assert len(detail["participants"]) == 3


# --- STB-92: headcount cap on join -------------------------------------

def test_join_respects_headcount_cap(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 10, "username": "own"}).json()
    bill = client.post(
        "/bills/",
        json={"owner_id": owner["id"], "total_sum": 100, "expected_people": 2, "include_owner": True},
    ).json()
    bid = bill["id"]
    u2 = client.post("/users/", json={"telegram_id": 11, "username": "u2"}).json()
    u3 = client.post("/users/", json={"telegram_id": 12, "username": "u3"}).json()

    # The table was laid for 2: the owner in seat 0 and one guest seat waiting.
    free = [
        p["id"]
        for p in client.get(f"/bills/{bid}?user_id={owner['id']}").json()["participants"]
        if p["user_id"] is None
    ]
    assert len(free) == 1

    # u2 has to say which seat is theirs, then takes the only free one.
    resp = client.post("/bills/join-by-token", json={"token": bill["public_token"], "user_id": u2["id"]})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SEAT_REQUIRED"
    assert client.post(
        f"/bills/{bid}/seats/{free[0]}/claim", json={"user_id": u2["id"]}
    ).status_code == 200

    # u3 has nowhere to sit.
    resp = client.post("/bills/join-by-token", json={"token": bill["public_token"], "user_id": u3["id"]})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "BILL_FULL"


def test_existing_participant_rejoins_full_bill(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 20, "username": "o"}).json()
    bill = client.post(
        "/bills/",
        json={"owner_id": owner["id"], "total_sum": 100, "expected_people": 1, "include_owner": True},
    ).json()
    bid = bill["id"]
    # The bill is already at its cap (owner), but re-joining as an existing
    # participant is idempotent and must not be blocked.
    assert client.post("/bills/join-by-token", json={"token": bill["public_token"], "user_id": owner["id"]}).status_code == 200


def test_join_unlimited_without_headcount(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 30, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
    ).json()
    bid = bill["id"]
    for tid in (31, 32, 33):
        u = client.post("/users/", json={"telegram_id": tid, "username": f"u{tid}"}).json()
        assert client.post("/bills/join-by-token", json={"token": bill["public_token"], "user_id": u["id"]}).status_code == 200
