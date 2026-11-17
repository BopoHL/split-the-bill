"""Tests for editing a bill's declared headcount via PATCH /bills/{id}
(expected_people field) — STB-182."""

from fastapi.testclient import TestClient


def _setup_bill(client: TestClient, expected: int = 3) -> tuple[int, int]:
    """Returns (owner_id, bill_id) for an owner-included bill."""
    client.post("/users/", json={"telegram_id": 900, "username": "ep_owner"})
    owner_id = 1
    resp = client.post(
        "/bills/",
        json={
            "owner_id": owner_id,
            "total_sum": 100,
            "include_owner": True,
            "expected_people": expected,
        },
    )
    return owner_id, resp.json()["id"]


def test_update_expected_people(client: TestClient):
    owner_id, bill_id = _setup_bill(client, expected=3)

    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 5, "user_id": owner_id},
    )
    assert resp.status_code == 200
    assert resp.json()["expected_people"] == 5

    # Persisted
    resp = client.get(f"/bills/{bill_id}?user_id={owner_id}")
    assert resp.json()["expected_people"] == 5


def test_expected_people_must_be_positive(client: TestClient):
    owner_id, bill_id = _setup_bill(client)
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 0, "user_id": owner_id},
    )
    assert resp.status_code == 400


def test_shrinking_past_an_occupied_seat_is_refused(client: TestClient):
    """Dropping the headcount can't silently evict somebody."""
    owner_id, bill_id = _setup_bill(client, expected=3)
    client.post("/users/", json={"telegram_id": 901, "username": "ep_p2"})
    free = [
        p["id"]
        for p in client.get(f"/bills/{bill_id}?user_id={owner_id}").json()["participants"]
        if p["user_id"] is None
    ]
    # Take the LAST seat, so shrinking to 1 would have to remove it.
    client.post(f"/bills/{bill_id}/seats/{free[-1]}/claim", json={"user_id": 2})

    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 1, "user_id": owner_id},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SEATS_IN_USE"


def test_shrinking_drops_empty_seats_from_the_end(client: TestClient):
    owner_id, bill_id = _setup_bill(client, expected=4)
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 2, "user_id": owner_id},
    )
    assert resp.status_code == 200
    assert len(resp.json()["participants"]) == 2


def test_growing_adds_guest_seats(client: TestClient):
    owner_id, bill_id = _setup_bill(client, expected=2)
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 4, "user_id": owner_id},
    )
    assert resp.status_code == 200
    seats = resp.json()["participants"]
    assert len(seats) == 4
    assert sum(1 for s in seats if s["is_guest"]) == 3


def test_update_expected_people_leaves_title_alone(client: TestClient):
    owner_id, bill_id = _setup_bill(client)
    client.patch(
        f"/bills/{bill_id}",
        json={"title": "Dinner", "user_id": owner_id},
    )
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 6, "user_id": owner_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expected_people"] == 6
    assert body["title"] == "Dinner"


def test_update_expected_people_requires_owner(client: TestClient):
    owner_id, bill_id = _setup_bill(client)
    client.post("/users/", json={"telegram_id": 902, "username": "ep_intruder"})
    intruder_id = 2

    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 9, "user_id": intruder_id},
    )
    assert resp.status_code == 403


def test_create_expected_people_capped(client: TestClient):
    # A huge headcount would overflow the int column — reject with 400, not 500.
    client.post("/users/", json={"telegram_id": 903, "username": "ep_big"})
    resp = client.post(
        "/bills/",
        json={"owner_id": 1, "total_sum": 100, "expected_people": 999_999_999_999},
    )
    assert resp.status_code == 400


def test_update_expected_people_capped(client: TestClient):
    owner_id, bill_id = _setup_bill(client)
    resp = client.patch(
        f"/bills/{bill_id}",
        json={"expected_people": 999_999_999_999, "user_id": owner_id},
    )
    assert resp.status_code == 400
