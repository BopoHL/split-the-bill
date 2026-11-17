"""The home screen's lists: each bill says where the person listing it stands —
their own seat, whose bill it is, and for the owner, what is still owed and
whom they may remind — and the archive can be searched and split by role."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import ManualReminder, ManualReminderStatus


def _user(client: TestClient, telegram_id: int, username: str, name: str | None = None) -> int:
    return client.post("/users/", json={"telegram_id": telegram_id, "username": username, "name": name}).json()["id"]


def _bill(client: TestClient, owner: int, title: str) -> int:
    return client.post("/bills/", json={"owner_id": owner, "total_sum": 1_000_000, "title": title, "include_owner": True}).json()["id"]


def _seat(client: TestClient, bill_id: int, owner: int, user_id: int, amount: float) -> int:
    client.post(f"/bills/{bill_id}/participants", json={"user_id": user_id})
    seats = client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]
    seat_id = next(seat["id"] for seat in seats if seat["user_id"] == user_id)
    client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": seat_id, "allocated_amount": amount})
    return seat_id


def _listed(client: TestClient, user_id: int, bill_id: int, **params) -> dict:
    return next(bill for bill in client.get(f"/users/{user_id}/bills", params=params).json() if bill["id"] == bill_id)


def _ids(client: TestClient, user_id: int, **params) -> list[int]:
    return [bill["id"] for bill in client.get(f"/users/{user_id}/bills", params=params).json()]


def test_a_joined_bill_says_my_share_and_whose_it_is(client: TestClient):
    alice = _user(client, 900, "alice", "Alice")
    bob = _user(client, 901, "bob")
    bill_id = _bill(client, alice, "Taxi")
    seat_id = _seat(client, bill_id, alice, bob, 42500)

    bill = _listed(client, bob, bill_id)

    assert bill["my_seat"] == {"id": seat_id, "amount": 42500.0, "is_paid": False}
    assert bill["owner"] == {"name": "Alice", "avatar_url": None}
    assert bill["collection"] is None


def test_the_owner_sees_what_is_left_and_whom_to_remind(client: TestClient):
    alice = _user(client, 910, "alice2")
    bob = _user(client, 911, "bob2")
    dana = _user(client, 912, "dana2")
    bill_id = _bill(client, alice, "Dinner")
    _seat(client, bill_id, alice, bob, 78000)
    dana_seat = _seat(client, bill_id, alice, dana, 60000)
    client.post(f"/bills/{bill_id}/participants/{dana_seat}/payment", json={"is_paid": True, "user_id": dana})

    collection = _listed(client, alice, bill_id)["collection"]

    assert collection == {"left": 78000.0, "remindable": 1, "reminded_at": None, "next_reminder_at": None}
    # The bill itself says the same, not «total less what came back».
    assert client.get(f"/bills/{bill_id}?user_id={alice}").json()["left_to_collect"] == 78000.0


def test_a_reminder_just_sent_holds_the_bell_until_the_hour_is_up(client: TestClient, session: Session):
    alice = _user(client, 920, "alice3")
    bob = _user(client, 921, "bob3")
    bill_id = _bill(client, alice, "Bowling")
    bob_seat = _seat(client, bill_id, alice, bob, 120000)
    sent = datetime.utcnow() - timedelta(minutes=20)
    session.add(ManualReminder(
        bill_id=bill_id, participant_id=bob_seat, requested_by_user_id=alice,
        status=ManualReminderStatus.SENT, created_at=sent, sent_at=sent,
    ))
    session.commit()

    collection = _listed(client, alice, bill_id)["collection"]

    assert collection["remindable"] == 0
    reminded_at = datetime.fromisoformat(collection["reminded_at"])
    next_at = datetime.fromisoformat(collection["next_reminder_at"])
    assert reminded_at == sent.replace(tzinfo=timezone.utc)
    assert next_at == (sent + timedelta(hours=1)).replace(tzinfo=timezone.utc)


def test_a_closed_bill_has_nothing_to_collect(client: TestClient):
    alice = _user(client, 930, "alice4")
    bill_id = _bill(client, alice, "Coffee")
    client.post(f"/bills/{bill_id}/close", json={"user_id": alice})

    assert _listed(client, alice, bill_id, status="closed")["collection"] is None


def test_the_archive_is_searched_by_title_and_by_anyone_at_the_table(client: TestClient):
    me = _user(client, 940, "leo")
    timur = _user(client, 941, "timur_k", "Timur")
    bowling = _bill(client, me, "Bowling night")
    karaoke = _bill(client, timur, "Karaoke")
    _seat(client, karaoke, timur, me, 19200)
    lunch = _bill(client, me, "Lunch")
    _seat(client, lunch, me, timur, 32000)
    for bill_id, owner in ((bowling, me), (karaoke, timur), (lunch, me)):
        client.post(f"/bills/{bill_id}/close", json={"user_id": owner})

    assert _ids(client, me, status="closed", q="BOWL") == [bowling]
    assert sorted(_ids(client, me, status="closed", q="timur")) == sorted([karaoke, lunch])
    assert sorted(_ids(client, me, status="closed", q="@timur_k")) == sorted([karaoke, lunch])
    assert _ids(client, me, status="closed", q="%") == []


def test_the_archive_splits_into_mine_and_joined_with_counts(client: TestClient):
    me = _user(client, 950, "leo2")
    alice = _user(client, 951, "alice5")
    mine = _bill(client, me, "Dacha")
    theirs = _bill(client, alice, "Shashlik")
    _seat(client, theirs, alice, me, 62000)
    still_open = _bill(client, me, "Pizza")
    for bill_id, owner in ((mine, me), (theirs, alice)):
        client.post(f"/bills/{bill_id}/close", json={"user_id": owner})

    assert _ids(client, me, status="closed", role="owner") == [mine]
    assert _ids(client, me, status="closed", role="participant") == [theirs]
    assert still_open not in _ids(client, me, status="closed")
    counts = client.get(f"/users/{me}/bills/counts", params={"status": "closed"}).json()
    assert counts == {"all": 2, "owned": 1, "joined": 1}
    searched = client.get(f"/users/{me}/bills/counts", params={"status": "closed", "q": "shash"}).json()
    assert searched == {"all": 1, "owned": 0, "joined": 1}


def test_a_bill_says_when_it_was_made_in_utc_so_the_archive_dates_it_by_the_phone_s_clock(client: TestClient):
    alice = _user(client, 960, "alice6")
    bill_id = _bill(client, alice, "Ужин")

    listed = datetime.fromisoformat(_listed(client, alice, bill_id)["created_at"])
    opened = datetime.fromisoformat(client.get(f"/bills/{bill_id}?user_id={alice}").json()["created_at"])

    assert listed.utcoffset() == opened.utcoffset() == timedelta(0)
    assert abs(datetime.now(timezone.utc) - listed) < timedelta(minutes=1)


def test_the_archive_pages_from_what_is_already_shown(client: TestClient):
    me = _user(client, 970, "leo7")
    made = [_bill(client, me, f"Ужин {index}") for index in range(5)]
    for bill_id in made:
        client.post(f"/bills/{bill_id}/close", json={"user_id": me})
    newest_first = _ids(client, me, status="closed")
    shown = newest_first[:2]
    client.delete(f"/bills/{shown[0]}", params={"user_id": me})

    # One of the two shown is gone: the next page starts after the one left.
    assert _ids(client, me, status="closed", offset=1, limit=2) == newest_first[2:4]
    assert client.get(f"/users/{me}/bills", params={"limit": 0}).status_code == 422
