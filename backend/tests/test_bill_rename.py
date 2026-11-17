"""Tests for renaming a bill via PATCH /bills/{id} (title field)."""

from fastapi.testclient import TestClient


def _setup_bill(client: TestClient, title: str = "Original") -> tuple[int, int]:
    """Returns (user_id, bill_id)."""
    client.post("/users/", json={"telegram_id": 800, "username": "rename_owner"})
    user_id = 1
    resp = client.post(
        "/bills/",
        json={"owner_id": user_id, "total_sum": 100, "title": title, "include_owner": True},
    )
    return user_id, resp.json()["id"]


def test_rename_bill_updates_title(client: TestClient):
    user_id, bill_id = _setup_bill(client, title="Original")

    resp = client.patch(
        f"/bills/{bill_id}",
        json={"title": "Renamed", "user_id": user_id},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"

    # Persisted
    resp = client.get(f"/bills/{bill_id}?user_id=1")
    assert resp.json()["title"] == "Renamed"


def test_rename_trims_whitespace(client: TestClient):
    user_id, bill_id = _setup_bill(client)
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"title": "   Trimmed   ", "user_id": user_id},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Trimmed"


def test_empty_title_clears_to_null(client: TestClient):
    user_id, bill_id = _setup_bill(client, title="Will be cleared")
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"title": "", "user_id": user_id},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] is None


def test_rename_leaves_payment_details_alone(client: TestClient):
    user_id, bill_id = _setup_bill(client)
    # First set payment_details
    client.patch(
        f"/bills/{bill_id}",
        json={"payment_details": "Card 9999", "user_id": user_id},
    )
    # Now rename only — payment_details must not be wiped
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"title": "Only rename", "user_id": user_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Only rename"
    assert body["payment_details"] == "Card 9999"


def test_rename_requires_owner(client: TestClient):
    user_id, bill_id = _setup_bill(client)
    # Make a second user
    client.post("/users/", json={"telegram_id": 801, "username": "intruder"})
    intruder_id = 2

    resp = client.patch(
        f"/bills/{bill_id}",
        json={"title": "Hacked", "user_id": intruder_id},
    )
    assert resp.status_code == 403
