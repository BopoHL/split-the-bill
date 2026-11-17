"""Tests for the `?status=active|closed` filter on GET /users/{id}/bills."""

from fastapi.testclient import TestClient


def _create_user(client: TestClient, tg_id: int, username: str) -> int:
    resp = client.post("/users/", json={"telegram_id": tg_id, "username": username})
    assert resp.status_code == 200
    return resp.json()["id"]


def _create_bill(client: TestClient, owner_id: int, title: str) -> int:
    resp = client.post(
        "/bills/",
        json={"owner_id": owner_id, "total_sum": 100, "title": title, "include_owner": True},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def _close_bill(client: TestClient, bill_id: int, user_id: int):
    resp = client.post(f"/bills/{bill_id}/close", json={"user_id": user_id})
    assert resp.status_code == 200


def test_status_active_excludes_closed(client: TestClient):
    user_id = _create_user(client, 700, "filter_owner")
    open_id = _create_bill(client, user_id, "Open one")
    closed_id = _create_bill(client, user_id, "Closed one")
    _close_bill(client, closed_id, user_id)

    resp = client.get(f"/users/{user_id}/bills", params={"status": "active"})
    assert resp.status_code == 200
    ids = [b["id"] for b in resp.json()]
    assert open_id in ids
    assert closed_id not in ids


def test_status_closed_returns_only_closed(client: TestClient):
    user_id = _create_user(client, 701, "filter_owner_2")
    open_id = _create_bill(client, user_id, "Open one")
    closed_id = _create_bill(client, user_id, "Closed one")
    _close_bill(client, closed_id, user_id)

    resp = client.get(f"/users/{user_id}/bills", params={"status": "closed"})
    assert resp.status_code == 200
    ids = [b["id"] for b in resp.json()]
    assert closed_id in ids
    assert open_id not in ids


def test_no_status_returns_all(client: TestClient):
    user_id = _create_user(client, 702, "filter_owner_3")
    open_id = _create_bill(client, user_id, "Open one")
    closed_id = _create_bill(client, user_id, "Closed one")
    _close_bill(client, closed_id, user_id)

    resp = client.get(f"/users/{user_id}/bills")
    assert resp.status_code == 200
    ids = [b["id"] for b in resp.json()]
    assert open_id in ids
    assert closed_id in ids


def test_status_invalid_value_rejected(client: TestClient):
    user_id = _create_user(client, 703, "filter_owner_4")
    resp = client.get(f"/users/{user_id}/bills", params={"status": "garbage"})
    # FastAPI / Pydantic returns 422 for invalid Literal values
    assert resp.status_code == 422


def test_pagination_per_status(client: TestClient):
    user_id = _create_user(client, 704, "filter_owner_5")
    # 3 open bills
    for i in range(3):
        _create_bill(client, user_id, f"Open {i}")

    resp = client.get(
        f"/users/{user_id}/bills",
        params={"status": "active", "limit": 2},
    )
    assert resp.status_code == 200
    page1 = resp.json()
    assert len(page1) == 2

    resp = client.get(
        f"/users/{user_id}/bills",
        params={"status": "active", "limit": 2, "offset": 2},
    )
    assert resp.status_code == 200
    page2 = resp.json()
    assert len(page2) == 1
    # No overlap
    assert {b["id"] for b in page1}.isdisjoint({b["id"] for b in page2})
