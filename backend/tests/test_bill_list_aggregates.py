"""Dashboard-card aggregates on GET /users/{id}/bills:
items_count, paid_count and a compact participants_preview."""

from fastapi.testclient import TestClient


def test_list_includes_counts_and_preview(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 800, "username": "alice"}).json()["id"]
    bob = client.post("/users/", json={"telegram_id": 801, "username": "bob"}).json()["id"]

    bill_id = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 100, "title": "Dinner", "include_owner": True},
    ).json()["id"]
    client.post(f"/bills/{bill_id}/participants", json={"user_id": bob})

    # Two items
    client.post(f"/bills/{bill_id}/items", json={"name": "Plov", "price": 60, "count": 1})
    client.post(f"/bills/{bill_id}/items", json={"name": "Tea", "price": 40, "count": 1})

    # Give bob a share and mark him paid → paid_count should be 1.
    parts = client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]
    bob_pid = next(p["id"] for p in parts if p["user_id"] == bob)
    client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": bob_pid, "allocated_amount": 40.0})
    client.post(f"/bills/{bill_id}/participants/{bob_pid}/payment", json={"is_paid": True, "user_id": bob})

    bills = client.get(f"/users/{owner}/bills").json()
    bill = next(b for b in bills if b["id"] == bill_id)

    assert bill["items_count"] == 2
    assert bill["participants_count"] == 2
    assert bill["paid_count"] == 1
    preview = bill["participants_preview"]
    assert len(preview) == 2
    assert {p["initial"] for p in preview} == {"A", "B"}


def test_list_aggregates_default_zero(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 810, "username": "solo"}).json()["id"]
    bill_id = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 50, "title": "Empty", "include_owner": True},
    ).json()["id"]

    bill = next(b for b in client.get(f"/users/{owner}/bills").json() if b["id"] == bill_id)
    assert bill["items_count"] == 0
    assert bill["paid_count"] == 0
    assert len(bill["participants_preview"]) == 1  # owner only


def test_payers_counts_exclude_the_owner(client: TestClient):
    """The card's «n/x paid» chip must not count the owner paying himself."""
    owner = client.post("/users/", json={"telegram_id": 820, "username": "olga"}).json()["id"]
    bob = client.post("/users/", json={"telegram_id": 821, "username": "bob"}).json()["id"]
    bill_id = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 100, "include_owner": True, "expected_people": 2},
    ).json()["id"]
    client.post(f"/bills/{bill_id}/participants", json={"user_id": bob})

    parts = client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]
    by_user = {p["user_id"]: p["id"] for p in parts}
    for pid in by_user.values():
        client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": pid, "allocated_amount": 50.0})

    def fetch():
        return next(b for b in client.get(f"/users/{owner}/bills").json() if b["id"] == bill_id)

    bill = fetch()
    assert bill["payers_count"] == 1  # bob only
    assert bill["payers_paid"] == 0

    # The owner marking himself paid moves paid_count but not payers_paid.
    client.post(
        f"/bills/{bill_id}/participants/{by_user[owner]}/payment",
        json={"is_paid": True, "user_id": owner},
    )
    bill = fetch()
    assert bill["paid_count"] == 1
    assert bill["payers_paid"] == 0

    client.post(
        f"/bills/{bill_id}/participants/{by_user[bob]}/payment",
        json={"is_paid": True, "user_id": bob},
    )
    bill = fetch()
    assert bill["payers_paid"] == 1
