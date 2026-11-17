"""Admin view over payment reminders: who is being nudged and how it is going."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import PaymentReminder


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    from app.routers import admin

    admin._LOGIN_ATTEMPTS.clear()


def _login(client: TestClient) -> None:
    assert (
        client.post(
            "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
        ).status_code
        == 200
    )


def _bill_with_debtor(client: TestClient, tg: int, username: str):
    """An open bill where `username` owes the owner money."""
    owner = client.post("/users/", json={"telegram_id": tg, "username": "owner"}).json()["id"]
    debtor = client.post(
        "/users/", json={"telegram_id": tg + 1, "username": username}
    ).json()["id"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner,
            "total_sum": 0,
            "title": "Dinner",
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    seat = next(
        p
        for p in client.get(f"/bills/{bill['id']}?user_id={owner}").json()["participants"]
        if p["user_id"] is None
    )
    client.post(f"/bills/{bill['id']}/seats/{seat['id']}/claim", json={"user_id": debtor})
    return bill["id"], seat["id"]


def _reminder(session, bill_id: int, seat_id: int, **fields) -> PaymentReminder:
    reminder = PaymentReminder(bill_id=bill_id, participant_id=seat_id, **fields)
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder


def test_reminders_are_closed_without_a_session(client: TestClient):
    assert client.get("/admin/reminders").status_code == 401


def test_a_reminder_shows_who_owes_what_and_when_it_last_fired(client: TestClient, session):
    bill_id, seat_id = _bill_with_debtor(client, 700, "debtor")
    sent_at = datetime(2026, 8, 19, 10, 0)
    _reminder(
        session,
        bill_id,
        seat_id,
        sent_count=2,
        last_sent_at=sent_at,
        next_due_at=sent_at + timedelta(hours=1),
    )
    _login(client)

    page = client.get("/admin/reminders").json()

    assert page["total"] == 1
    assert page["sent_total"] == 2
    row = page["items"][0]
    assert row["username"] == "debtor"
    assert row["bill_id"] == bill_id
    assert row["bill_title"] == "Dinner"
    assert row["sent_count"] == 2
    assert row["last_sent_at"].startswith("2026-08-19T10:00")
    assert row["state"] == "scheduled"


def test_state_separates_waiting_from_muted_and_stopped(client: TestClient, session):
    first, first_seat = _bill_with_debtor(client, 710, "waiting")
    second, second_seat = _bill_with_debtor(client, 720, "blocked")
    third, third_seat = _bill_with_debtor(client, 730, "settled")
    now = datetime(2026, 8, 19, 12, 0)
    _reminder(session, first, first_seat, next_due_at=now)
    _reminder(session, second, second_seat, next_due_at=now, muted_at=now)
    _reminder(session, third, third_seat, next_due_at=None)
    _login(client)

    states = {
        row["username"]: row["state"]
        for row in client.get("/admin/reminders").json()["items"]
    }
    assert states == {"waiting": "scheduled", "blocked": "muted", "settled": "stopped"}

    muted = client.get("/admin/reminders?state=muted").json()
    assert [row["username"] for row in muted["items"]] == ["blocked"]


def test_only_sent_hides_the_ones_that_never_fired(client: TestClient, session):
    quiet, quiet_seat = _bill_with_debtor(client, 740, "quiet")
    loud, loud_seat = _bill_with_debtor(client, 750, "loud")
    _reminder(session, quiet, quiet_seat, sent_count=0)
    _reminder(session, loud, loud_seat, sent_count=3, last_sent_at=datetime(2026, 8, 19, 9, 0))
    _login(client)

    page = client.get("/admin/reminders?only_sent=true").json()

    assert [row["username"] for row in page["items"]] == ["loud"]
    assert page["sent_total"] == 3


def test_reminders_can_be_narrowed_to_one_person_or_one_bill(client: TestClient, session):
    first, first_seat = _bill_with_debtor(client, 760, "alice")
    second, second_seat = _bill_with_debtor(client, 770, "bob")
    _reminder(session, first, first_seat)
    _reminder(session, second, second_seat)
    _login(client)

    by_name = client.get("/admin/reminders?q=@ali").json()
    assert [row["username"] for row in by_name["items"]] == ["alice"]

    by_bill = client.get(f"/admin/reminders?bill_id={second}").json()
    assert [row["username"] for row in by_bill["items"]] == ["bob"]


def test_reminders_are_paged(client: TestClient, session):
    for index in range(3):
        bill_id, seat_id = _bill_with_debtor(client, 800 + index * 10, f"p{index}")
        _reminder(
            session,
            bill_id,
            seat_id,
            sent_count=1,
            last_sent_at=datetime(2026, 8, 19, 10 + index, 0),
        )
    _login(client)

    page = client.get("/admin/reminders?limit=2&offset=0").json()

    assert page["total"] == 3
    assert len(page["items"]) == 2
    # Newest activity first.
    assert [row["username"] for row in page["items"]] == ["p2", "p1"]
