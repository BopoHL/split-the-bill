"""Seating someone the owner already knows, and telling them in the bot.

The Telegram calls are stubbed; what matters here is who the picker offers, who
it hides, and that a seat is never taken unless the message actually went out.
"""
import json
import time
from urllib.parse import quote, urlencode

import pytest
from fastapi.testclient import TestClient

import app.services.shared_bill_service as shared_mod
from app.models import User
from app.services.invite_service import InviteService
from sqlmodel import select


def _auth_headers(telegram_id: int) -> dict[str, str]:
    user = quote(json.dumps({"id": telegram_id}))
    return {"X-Telegram-Init-Data": f"user={user}&auth_date={int(time.time())}&hash=dev-test"}


def _deliver_to(sent: list[dict]):
    def fake_message(chat_id, text, reply_markup=None, parse_mode="HTML", link_preview_options=None):
        sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup, "preview": link_preview_options})
        return {"ok": True}

    return fake_message


@pytest.fixture
def outbox(monkeypatch) -> list[dict]:
    """Capture what the bot would send."""
    sent: list[dict] = []
    monkeypatch.setattr(shared_mod, "send_message", _deliver_to(sent))
    return sent


def _user(client: TestClient, telegram_id: int, username: str) -> dict:
    return client.post(
        "/users/", json={"telegram_id": telegram_id, "username": username, "name": username}
    ).json()


def _bill_with_guest_seat(client: TestClient, owner: dict, title: str = "Ужин") -> tuple[dict, dict]:
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner["id"],
            "total_sum": 0,
            "title": title,
            "payment_details": "8600 0000 0000 1234",
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    item = client.post(
        f"/bills/{bill['id']}/items", json={"name": "Lagman", "price": 40, "count": 1}
    ).json()
    seat = next(
        p
        for p in client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()["participants"]
        if p["is_guest"]
    )
    client.post(
        f"/bills/{bill['id']}/items/assign-batch?requester_id={owner['id']}",
        json={"ops": [{"item_id": item["id"], "participant_id": seat["id"], "is_assigned": True}]},
    )
    return bill, seat


def _shared_history(client: TestClient, owner: dict, friend: dict) -> None:
    """An earlier bill the two of them were on together."""
    past = client.post(
        "/bills/",
        json={
            "owner_id": owner["id"],
            "total_sum": 100,
            "title": "Прошлый раз",
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    seat = next(
        p
        for p in client.get(f"/bills/{past['id']}?user_id={owner['id']}").json()["participants"]
        if p["is_guest"]
    )
    client.post(
        f"/bills/{past['id']}/seats/{seat['id']}/claim", json={"user_id": friend["id"]}
    )


def test_the_picker_offers_people_you_have_shared_a_bill_with(client: TestClient):
    owner = _user(client, 900, "owner")
    friend = _user(client, 901, "friend")
    _user(client, 902, "stranger")
    _shared_history(client, owner, friend)
    bill, _ = _bill_with_guest_seat(client, owner)

    listed = client.get(
        f"/bills/{bill['id']}/assignable-users", headers=_auth_headers(900)
    ).json()

    assert [u["user_id"] for u in listed] == [friend["id"]]
    assert listed[0]["username"] == "friend"


def test_the_picker_hides_whoever_is_already_on_the_bill(client: TestClient):
    owner = _user(client, 910, "owner")
    friend = _user(client, 911, "friend")
    _shared_history(client, owner, friend)
    bill, seat = _bill_with_guest_seat(client, owner)
    client.post(f"/bills/{bill['id']}/seats/{seat['id']}/claim", json={"user_id": friend["id"]})

    listed = client.get(
        f"/bills/{bill['id']}/assignable-users", headers=_auth_headers(910)
    ).json()

    assert listed == []


def test_the_picker_keeps_previously_blocked_users_retryable(client: TestClient, session):
    owner = _user(client, 920, "owner")
    friend = _user(client, 921, "friend")
    _shared_history(client, owner, friend)
    bill, _ = _bill_with_guest_seat(client, owner)

    blocked = session.exec(select(User).where(User.id == friend["id"])).one()
    blocked.settings = {**(blocked.settings or {}), "bot_blocked": True}
    session.add(blocked)
    session.commit()

    listed = client.get(
        f"/bills/{bill['id']}/assignable-users", headers=_auth_headers(920)
    ).json()

    assert [u["user_id"] for u in listed] == [friend["id"]]


def test_a_username_lookup_finds_a_stranger_but_not_on_two_letters(client: TestClient):
    owner = _user(client, 930, "owner")
    stranger = _user(client, 931, "kolyan")
    bill, _ = _bill_with_guest_seat(client, owner)

    found = client.get(
        f"/bills/{bill['id']}/assignable-users?q=@kol", headers=_auth_headers(930)
    ).json()
    assert [u["user_id"] for u in found] == [stranger["id"]]

    # Too short to be a lookup, and a substring is not a lookup at all.
    assert client.get(
        f"/bills/{bill['id']}/assignable-users?q=ko", headers=_auth_headers(930)
    ).json() == []
    assert client.get(
        f"/bills/{bill['id']}/assignable-users?q=olya", headers=_auth_headers(930)
    ).json() == []


def test_a_username_lookup_takes_wildcards_literally(client: TestClient):
    owner = _user(client, 934, "owner")
    _user(client, 935, "kolyan")
    _user(client, 936, "pet_ya")
    bill, _ = _bill_with_guest_seat(client, owner)

    def lookup(term: str) -> list[str]:
        found = client.get(
            f"/bills/{bill['id']}/assignable-users",
            params={"q": term},
            headers=_auth_headers(934),
        ).json()
        return [u["username"] for u in found]

    # LIKE wildcards typed into the box used to list every account there is.
    assert lookup("%%%") == []
    assert lookup("___") == []
    assert lookup("pet_") == ["pet_ya"]


def test_only_the_owner_may_look_at_the_picker(client: TestClient):
    owner = _user(client, 940, "owner")
    outsider = _user(client, 941, "outsider")
    bill, _ = _bill_with_guest_seat(client, owner)

    resp = client.get(f"/bills/{bill['id']}/assignable-users", headers=_auth_headers(941))

    assert resp.status_code == 403
    assert outsider["id"]


def test_assigning_seats_the_person_and_messages_them(client: TestClient, outbox, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz")
    owner = _user(client, 950, "owner")
    friend = _user(client, 951, "friend")
    bill, seat = _bill_with_guest_seat(client, owner)

    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"], "lang": "ru"},
        headers=_auth_headers(950),
    )

    assert resp.status_code == 200
    taken = next(p for p in resp.json()["participants"] if p["id"] == seat["id"])
    assert taken["user_id"] == friend["id"]

    assert len(outbox) == 1
    message = outbox[0]
    assert message["chat_id"] == 951
    # The bill's post, as anyone sharing it sends it — under a line saying
    # why it came, with them already on their seat, and the picture above.
    assert message["text"].startswith("👋 <b>Вас добавили в счёт «Ужин»</b>\n\n👥 <b>Участники</b>")
    assert "<b>friend</b> — <code>40</code> сум" in message["text"]
    assert "8600000000001234" in message["text"]
    assert message["preview"]["url"].startswith(
        f"https://split-the-bill.uz/api/bills/public/{bill['public_token']}/card.png"
    )
    # Sent to them alone, so «I've paid» is theirs to press right here.
    [copy_card, paid], [open_button] = message["markup"]["inline_keyboard"]
    assert copy_card == {"text": "💳 Карта", "copy_text": {"text": "8600000000001234"}}
    assert open_button["text"] == "🧾 Открыть"
    assert "startapp=inv_" in open_button["url"]
    assert paid == {"text": "✅ Я оплатил(а)", "callback_data": "share_paid:" + open_button["url"].rsplit("inv_", 1)[1]}


def test_the_invite_is_written_in_the_language_the_person_reads_and_drawn_in_the_owners_theme(
    client: TestClient, outbox, monkeypatch
):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz")
    owner = _user(client, 952, "owner")
    friend = _user(client, 953, "friend")
    client.patch(f"/users/{owner['id']}/settings", json={"theme": "dark"}, headers=_auth_headers(952))
    client.patch(
        f"/users/{friend['id']}/settings", json={"language": "en", "theme": "light"}, headers=_auth_headers(953)
    )
    bill, seat = _bill_with_guest_seat(client, owner)

    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"], "lang": "ru"},
        headers=_auth_headers(952),
    )

    assert resp.status_code == 200
    # The owner's screen is in Russian; the friend reads English.
    assert "👥 <b>Participants</b>" in outbox[0]["text"]
    assert "<b>friend</b> — <code>40</code> uzs" in outbox[0]["text"]
    # The picture comes from the owner, as a post they shared would.
    assert "&theme=dark&" in outbox[0]["preview"]["url"]


def test_assigning_loses_to_a_claim_that_landed_first(
    client: TestClient, outbox, monkeypatch, session
):
    """The seat is checked, the invite minted, then the seat written — and a
    tap on an invite link can land in that gap. Whoever sat down first keeps
    the seat; the assign must not write over them."""
    owner = _user(client, 954, "owner")
    friend = _user(client, 955, "friend")
    early_bird = _user(client, 956, "early")
    bill, seat = _bill_with_guest_seat(client, owner)

    mint = InviteService.create

    def claim_meanwhile(self, *args, **kwargs):
        invite = mint(self, *args, **kwargs)
        client.post(
            f"/bills/{bill['id']}/seats/{seat['id']}/claim",
            json={"user_id": early_bird["id"]},
        )
        return invite

    monkeypatch.setattr(InviteService, "create", claim_meanwhile)

    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"], "lang": "ru"},
        headers=_auth_headers(954),
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "SEAT_TAKEN"
    assert outbox == []
    taken = next(
        p
        for p in client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()["participants"]
        if p["id"] == seat["id"]
    )
    assert taken["user_id"] == early_bird["id"]


def test_a_seat_stays_free_when_the_bot_cannot_write_to_the_person(
    client: TestClient, outbox, monkeypatch, session
):
    """The whole point of assigning is that the person finds out."""
    def blocked(*args, **kwargs):
        raise RuntimeError("Telegram error: Forbidden: bot was blocked by the user")

    monkeypatch.setattr(shared_mod, "send_message", blocked)

    owner = _user(client, 960, "owner")
    friend = _user(client, 961, "friend")
    bill, seat = _bill_with_guest_seat(client, owner)

    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"], "lang": "ru"},
        headers=_auth_headers(960),
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "BOT_BLOCKED"

    detail = client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()
    still_free = next(p for p in detail["participants"] if p["id"] == seat["id"])
    assert still_free["user_id"] is None
    assert still_free["is_guest"] is True
    # We still remember this for admin/broadcast hygiene, but the picker may
    # offer them again because Telegram gives us no "unblocked" webhook.
    session.expire_all()
    assert session.exec(select(User).where(User.id == friend["id"])).one().settings["bot_blocked"]


def test_assigning_retries_a_previously_blocked_user_and_clears_the_flag(
    client: TestClient, monkeypatch, session
):
    def blocked(*args, **kwargs):
        raise RuntimeError("Telegram error: Forbidden: bot was blocked by the user")

    monkeypatch.setattr(shared_mod, "send_message", blocked)

    owner = _user(client, 965, "owner")
    friend = _user(client, 966, "friend")
    bill, seat = _bill_with_guest_seat(client, owner)

    first = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"], "lang": "ru"},
        headers=_auth_headers(965),
    )

    assert first.status_code == 409
    assert first.json()["detail"] == "BOT_BLOCKED"
    session.expire_all()
    assert session.exec(select(User).where(User.id == friend["id"])).one().settings["bot_blocked"]

    listed = client.get(
        f"/bills/{bill['id']}/assignable-users?q=@friend", headers=_auth_headers(965)
    ).json()
    assert [u["user_id"] for u in listed] == [friend["id"]]

    sent: list[dict] = []
    monkeypatch.setattr(shared_mod, "send_message", _deliver_to(sent))

    second = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"], "lang": "ru"},
        headers=_auth_headers(965),
    )

    assert second.status_code == 200
    taken = next(p for p in second.json()["participants"] if p["id"] == seat["id"])
    assert taken["user_id"] == friend["id"]
    assert sent and sent[0]["chat_id"] == 966
    session.expire_all()
    retried = session.exec(select(User).where(User.id == friend["id"])).one()
    assert retried.settings["bot_blocked"] is False


def test_assigning_refuses_a_taken_seat_and_a_stranger_to_the_owner(client: TestClient, outbox):
    owner = _user(client, 980, "owner")
    friend = _user(client, 981, "friend")
    other = _user(client, 982, "other")
    bill, seat = _bill_with_guest_seat(client, owner)

    outsider = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"]},
        headers=_auth_headers(982),
    )
    assert outsider.status_code == 403
    assert other["id"]

    client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"]},
        headers=_auth_headers(980),
    )
    again = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"]},
        headers=_auth_headers(980),
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "SEAT_TAKEN"


def test_the_bot_writes_only_to_someone_the_owner_could_have_found(client: TestClient, outbox):
    """No @name and never met: the picker could not show them, so an owner going
    down the ids must not get the bot to write to them."""
    owner = _user(client, 960, "owner2")
    stranger = client.post("/users/", json={"telegram_id": 961, "name": "Ghost"}).json()
    bill, seat = _bill_with_guest_seat(client, owner)

    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": stranger["id"], "lang": "ru"},
        headers=_auth_headers(960),
    )

    assert resp.status_code == 404
    assert outbox == []


def test_someone_without_an_at_name_the_owner_has_sat_with_can_be_seated(client: TestClient, outbox):
    """The picker shows them from a past bill; seating them must work too."""
    owner = _user(client, 970, "owner3")
    friend = client.post("/users/", json={"telegram_id": 971, "name": "Quiet"}).json()
    _shared_history(client, owner, friend)
    bill, seat = _bill_with_guest_seat(client, owner)

    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/assign",
        json={"target_user_id": friend["id"], "lang": "ru"},
        headers=_auth_headers(970),
    )

    assert resp.status_code == 200, resp.json()
    assert [message["chat_id"] for message in outbox] == [971]
