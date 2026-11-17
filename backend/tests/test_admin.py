"""Admin panel: the auth contour, the read-only views and broadcasts."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.jobs import broadcast_sender
from app.models import Bill, Broadcast, BroadcastDelivery, BroadcastStatus, DeliveryStatus, Feedback, User


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    # The limiter is process-wide; start every test from a clean slate.
    from app.routers import admin

    admin._LOGIN_ATTEMPTS.clear()


def _login(client: TestClient) -> None:
    resp = client.post(
        "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
    )
    assert resp.status_code == 200


def test_admin_endpoints_are_closed_without_a_session(client: TestClient):
    assert client.get("/admin/stats").status_code == 401
    assert client.get("/admin/bills").status_code == 401
    assert client.get("/admin/users").status_code == 401


def test_login_rejects_a_wrong_password(client: TestClient):
    resp = client.post(
        "/admin/auth/login", json={"email": "boss@example.com", "password": "nope"}
    )
    assert resp.status_code == 401
    assert client.get("/admin/stats").status_code == 401


def test_repeated_guessing_is_rate_limited(client: TestClient):
    for _ in range(5):
        client.post("/admin/auth/login", json={"email": "boss@example.com", "password": "x"})
    resp = client.post(
        "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
    )
    assert resp.status_code == 429


def test_guessing_from_one_address_does_not_lock_out_another(client: TestClient):
    for _ in range(5):
        client.post(
            "/admin/auth/login",
            json={"email": "boss@example.com", "password": "x"},
            headers={"X-Real-IP": "203.0.113.9"},
        )
    resp = client.post(
        "/admin/auth/login",
        json={"email": "boss@example.com", "password": "s3cret"},
        headers={"X-Real-IP": "198.51.100.7"},
    )
    assert resp.status_code == 200


def test_rotating_addresses_inside_one_ipv6_block_does_not_reset_the_count(client: TestClient):
    for host in range(5):
        client.post(
            "/admin/auth/login",
            json={"email": "boss@example.com", "password": "x"},
            headers={"X-Real-IP": f"2001:db8:1:2::{host + 1}"},
        )
    resp = client.post(
        "/admin/auth/login",
        json={"email": "boss@example.com", "password": "s3cret"},
        headers={"X-Real-IP": "2001:db8:1:2::ffff"},
    )
    assert resp.status_code == 429


def test_guesses_from_many_addresses_hit_a_ceiling_together(client: TestClient):
    for host in range(50):
        client.post(
            "/admin/auth/login",
            json={"email": "boss@example.com", "password": "x"},
            headers={"X-Real-IP": f"198.51.100.{host}"},
        )
    resp = client.post(
        "/admin/auth/login",
        json={"email": "boss@example.com", "password": "s3cret"},
        headers={"X-Real-IP": "203.0.113.200"},
    )
    assert resp.status_code == 429


def test_signing_in_uses_up_no_attempts(client: TestClient):
    for _ in range(6):
        resp = client.post(
            "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
        )
        assert resp.status_code == 200


def test_login_opens_the_read_only_views(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o"}).json()["id"]
    client.post(
        "/bills/", json={"owner_id": owner, "total_sum": 100, "include_owner": True}
    )
    _login(client)

    stats = client.get("/admin/stats").json()
    assert stats["users_total"] == 1
    assert stats["bills_total"] == 1

    bills = client.get("/admin/bills").json()["items"]
    assert len(bills) == 1 and bills[0]["owner"] == "o"
    assert client.get("/admin/users").json()["items"][0]["username"] == "o"


def test_feedback_reads_newest_first_with_whoever_sent_it(client: TestClient, session):
    lea = User(telegram_id=77, username="lea", name="Lea")
    session.add(lea)
    session.commit()
    session.add(Feedback(user_id=lea.id, name="Лея", message="Кнопок слишком много", created_at=datetime(2026, 9, 1)))
    session.add(Feedback(message="Не понял, куда жать", created_at=datetime(2026, 9, 2)))
    session.commit()
    assert client.get("/admin/feedback").status_code == 401
    _login(client)

    page = client.get("/admin/feedback").json()

    assert page["total"] == 2
    anonymous, signed = page["items"]
    assert (anonymous["message"], anonymous["user"], anonymous["telegram_id"]) == ("Не понял, куда жать", None, None)
    assert (signed["message"], signed["name"], signed["user"], signed["user_id"], signed["telegram_id"]) == (
        "Кнопок слишком много", "Лея", "lea", lea.id, 77,
    )


def test_admin_lists_are_paginated(client: TestClient):
    for tg in range(100, 105):
        user_id = client.post(
            "/users/", json={"telegram_id": tg, "username": f"u{tg}"}
        ).json()["id"]
        client.post("/bills/", json={"owner_id": user_id, "total_sum": tg})
    _login(client)

    users = client.get("/admin/users?limit=2&offset=2").json()
    assert users["total"] == 5
    assert users["limit"] == 2
    assert users["offset"] == 2
    assert len(users["items"]) == 2

    bills = client.get("/admin/bills?limit=3&offset=1").json()
    assert bills["total"] == 5
    assert len(bills["items"]) == 3


def test_deleted_bills_are_hidden_unless_asked_for_and_can_be_restored(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 2, "username": "o2"}).json()["id"]
    bill = client.post(
        "/bills/", json={"owner_id": owner, "total_sum": 100, "include_owner": True}
    ).json()
    client.delete(f"/bills/{bill['id']}?user_id={owner}")
    _login(client)

    assert client.get("/admin/bills").json()["items"] == []
    with_deleted = client.get("/admin/bills?include_deleted=true").json()["items"]
    assert len(with_deleted) == 1 and with_deleted[0]["is_deleted"] is True

    assert client.post(f"/admin/bills/{bill['id']}/restore").status_code == 200
    assert client.get(f"/bills/{bill['id']}?user_id={owner}").status_code == 200


def test_the_tours_demo_bills_stay_out_of_every_admin_view(client: TestClient, session):
    owner = client.post("/users/", json={"telegram_id": 3, "username": "o3"}).json()["id"]
    real = client.post("/bills/", json={"owner_id": owner, "total_sum": 100}).json()
    demo = client.post("/bills/", json={"owner_id": owner, "total_sum": 900}).json()
    stored = session.get(Bill, demo["id"])
    stored.is_demo = True
    session.add(stored)
    session.commit()
    _login(client)

    stats = client.get("/admin/stats").json()
    assert (stats["bills_total"], stats["bills_open"], stats["average_bill"]) == (1, 1, 100)
    listed = client.get("/admin/bills?include_deleted=true").json()
    assert [bill["id"] for bill in listed["items"]] == [real["id"]] and listed["total"] == 1
    detail = client.get(f"/admin/users/{owner}").json()
    assert [bill["id"] for bill in detail["owned_bills"]] == [real["id"]]
    assert detail["bills_count"] == 1


def test_payment_details_never_leave_the_admin_api(client: TestClient):
    """They are encrypted at rest precisely so a session can't hand them out."""
    owner = client.post("/users/", json={"telegram_id": 3, "username": "o3"}).json()["id"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner, "total_sum": 100, "include_owner": True,
            "payment_details": "8600 1234 5678 9012",
        },
    ).json()
    _login(client)

    for path in (
        "/admin/stats",
        "/admin/bills",
        f"/admin/bills/{bill['id']}",
        "/admin/users",
    ):
        assert "8600" not in client.get(path).text


def test_admin_bill_detail_shows_items_split_and_payment_statuses(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 301, "username": "owner"}).json()["id"]
    guest = client.post("/users/", json={"telegram_id": 302, "username": "guest"}).json()["id"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner,
            "total_sum": 120,
            "title": "Dinner",
            "currency": "usd",
            "include_owner": True,
        },
    ).json()
    seats = client.post(f"/bills/{bill['id']}/participants", json={"user_id": guest}).json()
    guest_seat = next(seat for seat in seats if seat["user_id"] == guest)
    item = client.post(
        f"/bills/{bill['id']}/items",
        json={"name": "Plov", "price": 120, "count": 1},
    ).json()
    client.post(
        f"/bills/{bill['id']}/items/{item['id']}/assign?requester_id={owner}",
        json={"participant_id": guest_seat["id"], "is_assigned": True},
    )
    client.post(
        f"/bills/{bill['id']}/participants/{guest_seat['id']}/payment",
        json={"is_paid": True, "user_id": guest},
    )
    _login(client)

    detail = client.get(f"/admin/bills/{bill['id']}").json()
    assert detail["title"] == "Dinner"
    assert detail["owner_id"] == owner
    assert "payment_details" not in detail
    assert detail["items"][0]["name"] == "Plov"
    assert detail["items"][0]["portions"] == [[guest_seat["id"]]]
    paid_guest = next(p for p in detail["participants"] if p["user_id"] == guest)
    assert paid_guest["allocated_amount"] == 120
    assert paid_guest["is_paid"] is True


def test_admin_user_detail_lists_owned_and_participating_bills(client: TestClient):
    user = client.post(
        "/users/",
        json={"telegram_id": 401, "username": "alice", "name": "Alice"},
    ).json()
    owner = client.post("/users/", json={"telegram_id": 402, "username": "owner2"}).json()
    client.patch(
        f"/users/{user['id']}/settings",
        json={"language": "ru", "currency": "uzs", "onboarding_completed": True},
    )
    own = client.post(
        "/bills/", json={"owner_id": user["id"], "total_sum": 10, "title": "Mine"}
    ).json()
    other = client.post(
        "/bills/",
        json={"owner_id": owner["id"], "total_sum": 20, "title": "Joined"},
    ).json()
    client.post(f"/bills/{other['id']}/participants", json={"user_id": user["id"]})
    _login(client)

    detail = client.get(f"/admin/users/{user['id']}").json()
    assert detail["language"] == "ru"
    assert detail["currency"] == "uzs"
    assert detail["onboarding_completed"] is True
    assert [bill["id"] for bill in detail["owned_bills"]] == [own["id"]]
    assert [bill["id"] for bill in detail["participant_bills"]] == [other["id"]]


def test_a_broadcast_is_only_sent_once_even_if_the_job_reruns(client: TestClient, session, monkeypatch):
    for tg in (10, 11, 12):
        client.post("/users/", json={"telegram_id": tg, "username": f"u{tg}"})
    _login(client)

    created = client.post(
        "/admin/broadcasts",
        json={"title": "Release 0.4", "body": {"ru": "Привет", "en": "Hello"}},
    ).json()
    assert client.post(f"/admin/broadcasts/{created['id']}/send").status_code == 200

    outbox = []
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda chat_id, text, reply_markup=None, parse_mode="HTML": outbox.append(chat_id),
    )

    assert broadcast_sender.run(session, sleep=lambda _: None) == 3
    # A second pass has nothing left to do — the delivery rows say so.
    assert broadcast_sender.run(session, sleep=lambda _: None) == 0
    assert sorted(outbox) == [10, 11, 12]

    session.expire_all()
    broadcast = session.get(Broadcast, created["id"])
    assert broadcast.status == BroadcastStatus.DONE
    assert broadcast.sent_count == 3


def _queued_broadcast(client: TestClient, telegram_ids) -> None:
    for tg in telegram_ids:
        client.post("/users/", json={"telegram_id": tg, "username": f"u{tg}"})
    _login(client)
    created = client.post("/admin/broadcasts", json={"title": "News", "body": {"ru": "a"}}).json()
    client.post(f"/admin/broadcasts/{created['id']}/send")


def test_a_restart_mid_batch_sends_nobody_the_message_twice(client: TestClient, session, monkeypatch):
    _queued_broadcast(client, (30, 31))
    outbox = []

    def killed_after_the_first(chat_id, text, reply_markup=None, parse_mode="HTML"):
        if outbox:
            raise SystemExit  # the deploy stops the container mid-batch
        outbox.append(chat_id)

    monkeypatch.setattr(broadcast_sender, "send_message", killed_after_the_first)
    with pytest.raises(SystemExit):
        broadcast_sender.run(session, sleep=lambda _: None)
    session.rollback()  # whatever was not written down is gone with the process

    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda chat_id, text, reply_markup=None, parse_mode="HTML": outbox.append(chat_id),
    )
    broadcast_sender.run(session, sleep=lambda _: None)
    assert sorted(outbox) == [30, 31]


def test_a_network_blip_is_tried_again_rather_than_failed(client: TestClient, session, monkeypatch):
    _queued_broadcast(client, (40,))
    attempts = []

    def flaky(chat_id, text, reply_markup=None, parse_mode="HTML"):
        attempts.append(chat_id)
        if len(attempts) == 1:
            raise RuntimeError("Telegram request failed: read timeout")

    monkeypatch.setattr(broadcast_sender, "send_message", flaky)
    with pytest.raises(RuntimeError):
        broadcast_sender.run(session, sleep=lambda _: None)
    broadcast_sender.run(session, sleep=lambda _: None)

    session.expire_all()
    delivery = session.exec(select(BroadcastDelivery)).one()
    assert attempts == [40, 40]
    assert delivery.status == DeliveryStatus.SENT


def test_an_empty_body_is_rejected(client: TestClient):
    _login(client)
    resp = client.post("/admin/broadcasts", json={"title": "x", "body": {"ru": "   "}})
    assert resp.status_code == 400


def test_how_a_broadcast_ended_is_counted_for_each_recipient(client: TestClient, session, monkeypatch, product_events):
    blocker = client.post("/users/", json={"telegram_id": 20, "username": "blocker"}).json()
    reader = client.post("/users/", json={"telegram_id": 21, "username": "reader"}).json()
    _login(client)
    broadcast = client.post("/admin/broadcasts", json={"title": "One", "body": {"ru": "a"}}).json()
    client.post(f"/admin/broadcasts/{broadcast['id']}/send")

    def selective(chat_id, text, reply_markup=None, parse_mode="HTML"):
        if chat_id == 20:
            raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(broadcast_sender, "send_message", selective)
    broadcast_sender.run(session, sleep=lambda _: None)

    results = sorted(
        (distinct_id, properties) for event, distinct_id, properties in product_events if event == "broadcast_result"
    )
    common = {"surface": "server", "broadcast_id": broadcast["id"]}
    assert results == sorted([
        (str(blocker["id"]), {**common, "ok": False, "status": "blocked"}),
        (str(reader["id"]), {**common, "ok": True, "status": "sent"}),
    ])


def test_a_blocked_user_is_remembered_and_skipped_next_time(
    client: TestClient, session, monkeypatch
):
    client.post("/users/", json={"telegram_id": 20, "username": "blocker"})
    client.post("/users/", json={"telegram_id": 21, "username": "reader"})
    _login(client)

    first = client.post(
        "/admin/broadcasts", json={"title": "One", "body": {"ru": "a"}}
    ).json()
    client.post(f"/admin/broadcasts/{first['id']}/send")

    def selective(chat_id, text, reply_markup=None, parse_mode="HTML"):
        if chat_id == 20:
            raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(broadcast_sender, "send_message", selective)
    broadcast_sender.run(session, sleep=lambda _: None)

    session.expire_all()
    blocked = session.exec(select(User).where(User.telegram_id == 20)).one()
    assert blocked.settings.get("bot_blocked") is True

    # The next broadcast doesn't even create a delivery row for them.
    second = client.post(
        "/admin/broadcasts", json={"title": "Two", "body": {"ru": "b"}}
    ).json()
    client.post(f"/admin/broadcasts/{second['id']}/send")
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda chat_id, text, reply_markup=None, parse_mode="HTML": None,
    )
    broadcast_sender.run(session, sleep=lambda _: None)

    recipients = session.exec(
        select(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == second["id"])
    ).all()
    assert [d.user_id for d in recipients] != []
    assert all(session.get(User, d.user_id).telegram_id != 20 for d in recipients)


def test_the_message_follows_the_readers_language(client: TestClient, session, monkeypatch):
    user = client.post("/users/", json={"telegram_id": 30, "username": "uz"}).json()
    client.patch(f"/users/{user['id']}/settings", json={"language": "en"})
    _login(client)

    created = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "Привет", "en": "Hello"}}
    ).json()
    client.post(f"/admin/broadcasts/{created['id']}/send")

    sent = []
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda chat_id, text, reply_markup=None, parse_mode="HTML": sent.append(text),
    )
    broadcast_sender.run(session, sleep=lambda _: None)

    assert sent == ["Hello"]


def test_a_broadcast_can_target_one_person_by_username_or_id(
    client: TestClient, session, monkeypatch
):
    client.post("/users/", json={"telegram_id": 50, "username": "alice"})
    client.post("/users/", json={"telegram_id": 51, "username": "bob"})
    client.post("/users/", json={"telegram_id": 52, "username": "carol"})
    _login(client)

    created = client.post(
        "/admin/broadcasts",
        json={
            "title": "Personal",
            "body": {"ru": "Только тебе"},
            "audience": "selected",
            # One by handle (with the @ the operator naturally types), one by id.
            "targets": ["@alice", "52"],
        },
    ).json()
    assert sorted(created["target_user_ids"]) == sorted(created["target_user_ids"])
    client.post(f"/admin/broadcasts/{created['id']}/send")

    outbox = []
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda chat_id, text, reply_markup=None, parse_mode="HTML": outbox.append(chat_id),
    )
    broadcast_sender.run(session, sleep=lambda _: None)

    assert sorted(outbox) == [50, 52]  # bob is left out


def test_an_unknown_recipient_is_reported_rather_than_silently_skipped(client: TestClient):
    client.post("/users/", json={"telegram_id": 60, "username": "known"})
    _login(client)

    resp = client.post(
        "/admin/broadcasts",
        json={
            "title": "T", "body": {"ru": "x"},
            "audience": "selected", "targets": ["known", "@ghost"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["targets"] == ["@ghost"]


def test_the_button_defaults_to_opening_the_mini_app(client: TestClient, monkeypatch):
    monkeypatch.setenv("TG_BOT_USERNAME", "SplitTestBot")
    _login(client)

    created = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "x"}}
    ).json()
    assert created["button_text"] == "Открыть"
    # `t.me/<bot>` alone lands in the conversation with the bot; opening the app
    # needs its short name on the end.
    assert created["button_url"] == "https://t.me/SplitTestBot/app"

    custom = client.post(
        "/admin/broadcasts",
        json={
            "title": "T", "body": {"ru": "x"},
            "button_text": "Открыть счёт", "button_url": "https://example.com",
        },
    ).json()
    assert custom["button_text"] == "Открыть счёт"
    assert custom["button_url"] == "https://example.com"

    without = client.post(
        "/admin/broadcasts",
        json={"title": "T", "body": {"ru": "x"}, "with_button": False},
    ).json()
    assert without["button_text"] is None
    assert without["button_url"] is None


def test_the_body_always_goes_out_as_html(client: TestClient, session, monkeypatch):
    """The panel no longer offers a choice: Markdown makes Telegram reject a
    message over a stray asterisk, and plain text would silently print tags."""
    client.post("/users/", json={"telegram_id": 70, "username": "u"})
    _login(client)

    created = client.post(
        "/admin/broadcasts",
        json={"title": "T", "body": {"ru": "<b>bold</b>"}, "parse_mode": "Markdown"},
    ).json()
    assert created["parse_mode"] == "HTML"
    client.post(f"/admin/broadcasts/{created['id']}/send")

    modes = []
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda chat_id, text, reply_markup=None, parse_mode="HTML": modes.append(parse_mode),
    )
    broadcast_sender.run(session, sleep=lambda _: None)
    assert modes == ["HTML"]


def test_a_scheduled_broadcast_waits_for_its_hour_without_holding_up_the_queue(
    client: TestClient, session, monkeypatch
):
    client.post("/users/", json={"telegram_id": 70, "username": "reader"})
    _login(client)

    # Created first, so it would be picked first if the schedule were ignored.
    later = client.post(
        "/admin/broadcasts",
        json={
            "title": "Tomorrow",
            "body": {"ru": "Потом"},
            "scheduled_at": "2026-08-20T09:00:00+05:00",
        },
    ).json()
    now = client.post(
        "/admin/broadcasts", json={"title": "Now", "body": {"ru": "Сейчас"}}
    ).json()
    for broadcast_id in (later["id"], now["id"]):
        assert client.post(f"/admin/broadcasts/{broadcast_id}/send").status_code == 200

    outbox = []
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda chat_id, text, reply_markup=None, parse_mode="HTML": outbox.append(text),
    )

    assert broadcast_sender.run(
        session, sleep=lambda _: None, now=datetime(2026, 8, 14, 12, 0)
    ) == 1
    assert outbox == ["Сейчас"]

    session.expire_all()
    assert session.get(Broadcast, later["id"]).status == BroadcastStatus.QUEUED

    assert broadcast_sender.run(
        session, sleep=lambda _: None, now=datetime(2026, 8, 20, 4, 30)
    ) == 1
    assert outbox == ["Сейчас", "Потом"]


def test_the_hour_is_stored_in_utc_whatever_offset_it_arrives_in(client: TestClient, session):
    _login(client)

    created = client.post(
        "/admin/broadcasts",
        json={
            "title": "Evening",
            "body": {"ru": "Текст"},
            "scheduled_at": "2026-08-20T21:30:00+05:00",
        },
    ).json()

    # 21:30 in Tashkent is 16:30 UTC — and it is UTC that the job compares against,
    # so the server's own timezone never enters into it.
    assert session.get(Broadcast, created["id"]).scheduled_at == datetime(2026, 8, 20, 16, 30)
    assert created["scheduled_at"].startswith("2026-08-20T16:30")


def _png_bytes() -> bytes:
    """A one-pixel PNG — the endpoint only cares that it is an image."""
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def _attach_photo(client: TestClient, broadcast_id: int):
    return client.post(
        f"/admin/broadcasts/{broadcast_id}/photo",
        files={"file": ("cover.png", _png_bytes(), "image/png")},
    )


def test_a_broadcast_with_a_photo_uploads_it_once_and_reuses_the_handle(
    client: TestClient, session, monkeypatch
):
    """Telegram hands back a file_id for the picture it stored. Sending the
    bytes again for every recipient would multiply the upload by the size of
    the audience, so the first send is the only one that carries them."""
    for tg in (81, 82, 83):
        client.post("/users/", json={"telegram_id": tg, "username": f"u{tg}"})
    _login(client)

    created = client.post(
        "/admin/broadcasts", json={"title": "Cover", "body": {"ru": "Привет"}}
    ).json()
    assert _attach_photo(client, created["id"]).json()["has_photo"] is True
    assert client.post(f"/admin/broadcasts/{created['id']}/send").status_code == 200

    calls = []

    def fake_send_photo(chat_id, photo=None, caption=None, reply_markup=None,
                        parse_mode="HTML", photo_path=None):
        calls.append({"photo": photo, "photo_path": photo_path})
        return {"photo": [{"file_id": "small"}, {"file_id": "FILE-ID"}]}

    monkeypatch.setattr(broadcast_sender, "send_photo", fake_send_photo)
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda *a, **k: pytest.fail("a broadcast with a photo must not fall back to text"),
    )

    assert broadcast_sender.run(session, sleep=lambda _: None) == 3
    assert calls[0]["photo_path"] is not None and calls[0]["photo"] is None
    assert [c["photo"] for c in calls[1:]] == ["FILE-ID", "FILE-ID"]
    assert all(c["photo_path"] is None for c in calls[1:])


def test_a_text_too_long_for_a_caption_is_refused_with_the_photo(client: TestClient):
    """Telegram allows 4096 characters in a message but only 1024 under a
    picture, so attaching one can invalidate a text that was fine on its own."""
    _login(client)
    created = client.post(
        "/admin/broadcasts", json={"title": "Long", "body": {"ru": "x" * 1100}}
    ).json()

    resp = _attach_photo(client, created["id"])
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CAPTION_TOO_LONG"
    assert resp.json()["detail"]["limit"] == 1024


def test_replacing_the_photo_drops_the_cached_handle(client: TestClient, session):
    _login(client)
    created = client.post(
        "/admin/broadcasts", json={"title": "Cover", "body": {"ru": "Привет"}}
    ).json()
    _attach_photo(client, created["id"])

    broadcast = session.get(Broadcast, created["id"])
    broadcast.photo_file_id = "OLD-FILE-ID"
    session.add(broadcast)
    session.commit()

    _attach_photo(client, created["id"])
    session.expire_all()
    # Keeping it would send the previous picture to everyone.
    assert session.get(Broadcast, created["id"]).photo_file_id is None


def test_broadcast_details_show_the_message_and_how_it_landed(
    client: TestClient, session, monkeypatch
):
    """The header only. Who exactly it reached is its own paged endpoint."""
    for tg in (91, 92):
        client.post("/users/", json={"telegram_id": tg, "username": f"u{tg}"})
    _login(client)

    created = client.post(
        "/admin/broadcasts", json={"title": "News", "body": {"ru": "Привет"}}
    ).json()
    client.post(f"/admin/broadcasts/{created['id']}/send")

    def selective(chat_id, text, reply_markup=None, parse_mode="HTML"):
        if chat_id == 92:
            raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(broadcast_sender, "send_message", selective)
    broadcast_sender.run(session, sleep=lambda _: None)

    detail = client.get(f"/admin/broadcasts/{created['id']}").json()
    assert detail["body"]["ru"] == "Привет"
    assert detail["sent_count"] == 1 and detail["failed_count"] == 1
    assert detail["total_count"] == 2


def test_a_body_telegram_cannot_parse_is_refused_at_the_form(client: TestClient):
    """Telegram rejects the whole message over one stray tag — and it would do
    so once per recipient, turning a typo into a wholly failed broadcast."""
    _login(client)

    for body, reason in (
        ({"ru": "<ul><li>пункт</li></ul>"}, "тег"),
        ({"ru": "<b>не закрыт"}, "закрыт"),
        ({"ru": "5 < 6"}, "&lt;"),
    ):
        resp = client.post("/admin/broadcasts", json={"title": "T", "body": body})
        assert resp.status_code == 400, body
        assert resp.json()["detail"]["code"] == "BAD_HTML"
        assert reason in resp.json()["detail"]["message"]

    assert client.post(
        "/admin/broadcasts",
        json={"title": "T", "body": {"ru": "<b>Привет</b> &amp; пока"}},
    ).status_code == 201


def test_the_caption_limit_counts_what_telegram_counts(client: TestClient):
    """Markup doesn't take up room, and an emoji takes two code units."""
    _login(client)

    # 1020 visible characters wrapped in tags — well over 1024 raw, fine as text.
    wrapped = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "<b>" + "x" * 1020 + "</b>"}}
    ).json()
    assert _attach_photo(client, wrapped["id"]).status_code == 200

    emoji = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "\U0001F9FE" * 513}}
    ).json()
    assert _attach_photo(client, emoji["id"]).status_code == 400


def test_a_file_that_is_not_an_image_is_refused(client: TestClient):
    _login(client)
    created = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "Привет"}}
    ).json()

    resp = client.post(
        f"/admin/broadcasts/{created['id']}/photo",
        # The content type is whatever the sender claims; the bytes are the proof.
        files={"file": ("cover.png", b"definitely not a picture", "image/png")},
    )
    assert resp.status_code == 400


def test_only_a_draft_can_be_deleted_and_its_photo_goes_with_it(
    client: TestClient, session
):
    import os

    _login(client)
    created = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "Привет"}}
    ).json()
    _attach_photo(client, created["id"])
    path = session.get(Broadcast, created["id"]).photo_path
    assert os.path.exists(path)

    assert client.delete(f"/admin/broadcasts/{created['id']}").status_code == 204
    assert session.get(Broadcast, created["id"]) is None
    assert not os.path.exists(path)

    started = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "Привет"}}
    ).json()
    client.post(f"/admin/broadcasts/{started['id']}/send")
    # Once queued, the delivery rows are the record of what people received.
    assert client.delete(f"/admin/broadcasts/{started['id']}").status_code == 409


def test_replacing_the_photo_removes_the_previous_file(client: TestClient, session):
    import os

    _login(client)
    created = client.post(
        "/admin/broadcasts", json={"title": "T", "body": {"ru": "Привет"}}
    ).json()
    _attach_photo(client, created["id"])
    first = session.get(Broadcast, created["id"]).photo_path

    _attach_photo(client, created["id"])
    session.expire_all()
    second = session.get(Broadcast, created["id"]).photo_path
    assert second != first
    # Nothing points at it any more, and the purge job only knows about receipts.
    assert not os.path.exists(first)
    assert os.path.exists(second)


def test_a_bug_in_the_sender_surfaces_instead_of_looking_like_bad_luck(
    client: TestClient, session, monkeypatch
):
    """Telegram refusing one chat is routine and gets recorded per recipient.
    A broken sender is not, and swallowing it the same way is how a feature
    quietly stops working while the log fills with per-user warnings."""
    for tg in (95, 96):
        client.post("/users/", json={"telegram_id": tg, "username": f"u{tg}"})
    _login(client)

    created = client.post(
        "/admin/broadcasts", json={"title": "News", "body": {"ru": "Привет"}}
    ).json()
    client.post(f"/admin/broadcasts/{created['id']}/send")

    seen = []

    def broken(chat_id, text, reply_markup=None, parse_mode="HTML"):
        seen.append(chat_id)
        if len(seen) > 1:
            raise NameError("mini_app_link is not defined")

    monkeypatch.setattr(broadcast_sender, "send_message", broken)

    with pytest.raises(NameError):
        broadcast_sender.run(session, sleep=lambda _: None)

    session.expire_all()
    delivered = session.exec(
        select(BroadcastDelivery).where(BroadcastDelivery.status == DeliveryStatus.SENT)
    ).all()
    # The one that did go out stays recorded, or the retry would send it twice.
    assert len(delivered) == 1


def test_deliveries_are_paged_and_filtered_by_outcome(
    client: TestClient, session, monkeypatch
):
    for tg in (30, 31, 32):
        client.post("/users/", json={"telegram_id": tg, "username": f"u{tg}"})
    _login(client)

    created = client.post(
        "/admin/broadcasts", json={"title": "News", "body": {"ru": "Привет"}}
    ).json()
    client.post(f"/admin/broadcasts/{created['id']}/send")

    def refusing(chat_id, text, reply_markup=None, parse_mode="HTML"):
        if chat_id == 31:
            raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(broadcast_sender, "send_message", refusing)
    broadcast_sender.run(session, sleep=lambda _: None)

    page = client.get(f"/admin/broadcasts/{created['id']}/deliveries").json()
    assert page["total"] == 3
    assert {row["telegram_id"] for row in page["items"]} == {30, 31, 32}

    first = client.get(f"/admin/broadcasts/{created['id']}/deliveries?limit=2").json()
    assert len(first["items"]) == 2 and first["total"] == 3

    blocked = client.get(
        f"/admin/broadcasts/{created['id']}/deliveries?status={DeliveryStatus.BLOCKED.value}"
    ).json()
    assert [row["telegram_id"] for row in blocked["items"]] == [31]
    assert blocked["items"][0]["error"]

    by_name = client.get(
        f"/admin/broadcasts/{created['id']}/deliveries?q=u32"
    ).json()
    assert [row["telegram_id"] for row in by_name["items"]] == [32]


def test_deliveries_of_an_unknown_broadcast_are_a_404(client: TestClient):
    _login(client)
    assert client.get("/admin/broadcasts/999/deliveries").status_code == 404


def test_an_operator_changes_someones_settings_by_hand(client: TestClient):
    user = client.post("/users/", json={"telegram_id": 601, "username": "maya"}).json()
    client.patch(
        f"/users/{user['id']}/settings",
        json={"language": "ru", "theme": "dark", "currency": "uzs", "onboarding_completed": True},
    )
    _login(client)

    changed = client.put(
        f"/admin/users/{user['id']}/settings",
        json={"language": "uz", "onboarding_completed": False, "theme": None, "bot_blocked": True},
    )

    assert changed.status_code == 200
    detail = changed.json()
    assert detail["settings"] == {"language": "uz", "currency": "uzs", "onboarding_completed": False, "bot_blocked": True}
    assert (detail["language"], detail["onboarding_completed"], detail["bot_blocked"]) == ("uz", False, True)
    assert client.get(f"/users/{user['id']}", params={"user_id": user["id"]}).json()["settings"]["language"] == "uz"


def test_an_operator_marks_one_of_the_team_as_internal_for_posthog(client: TestClient, product_events):
    user = client.post("/users/", json={"telegram_id": 603, "username": "team"}).json()
    _login(client)

    client.put(f"/admin/users/{user['id']}/settings", json={"internal": True})
    client.put(f"/admin/users/{user['id']}/settings", json={"language": "ru"})
    client.put(f"/admin/users/{user['id']}/settings", json={"internal": None})

    assert [entry for entry in product_events if entry[0] == "$set"] == [
        ("$set", str(user["id"]), {"internal": True}),
        ("$set", str(user["id"]), {"internal": False}),
    ]


def test_settings_an_app_would_not_understand_are_refused(client: TestClient):
    user = client.post("/users/", json={"telegram_id": 602, "username": "lev"}).json()
    _login(client)

    assert client.put(f"/admin/users/{user['id']}/settings", json={"language": "fr"}).status_code == 422
    assert client.put(f"/admin/users/{user['id']}/settings", json={"currency": "doge"}).status_code == 400
    assert client.put("/admin/users/99999/settings", json={"language": "ru"}).status_code == 404


def test_user_settings_are_closed_without_a_session(client: TestClient):
    assert client.put("/admin/users/1/settings", json={"language": "ru"}).status_code == 401


RICH_BODY = (
    "<h2>Split·Bill 1.0</h2><p>Что нового</p>"
    '<img src="https://split-the-bill.uz/api/broadcasts/media/0123456789abcdef0123456789abcdef.jpg"/>'
    "<p>Промокод: <code>PRO</code></p>"
)


def test_a_rich_broadcast_goes_out_as_a_rich_message_with_its_button(
    client: TestClient, session, monkeypatch
):
    client.post("/users/", json={"telegram_id": 701, "username": "rich"})
    _login(client)

    created = client.post(
        "/admin/broadcasts",
        json={"title": "1.0", "format": "rich", "body": {"ru": RICH_BODY}, "button_text": "⭐ PRO"},
    ).json()
    assert created["format"] == "rich"
    client.post(f"/admin/broadcasts/{created['id']}/send")

    outbox = []
    monkeypatch.setattr(
        broadcast_sender, "send_rich_message",
        lambda chat_id, html, reply_markup=None: outbox.append((chat_id, html, reply_markup)) or {},
    )
    monkeypatch.setattr(
        broadcast_sender, "send_message",
        lambda *a, **k: pytest.fail("a rich broadcast must not go out as an ordinary message"),
    )
    assert broadcast_sender.run(session, sleep=lambda _: None) == 1

    [(chat_id, html, markup)] = outbox
    assert (chat_id, html) == (701, RICH_BODY)
    assert markup["inline_keyboard"][0][0]["text"] == "⭐ PRO"


def test_an_ordinary_broadcast_stays_ordinary_by_default(client: TestClient):
    _login(client)

    created = client.post("/admin/broadcasts", json={"title": "T", "body": {"ru": "x"}}).json()

    assert created["format"] == "message"


def test_each_format_is_checked_in_its_own_dialect(client: TestClient):
    _login(client)

    ordinary = client.post("/admin/broadcasts", json={"title": "T", "body": {"ru": RICH_BODY}})
    assert ordinary.status_code == 400
    assert ordinary.json()["detail"]["code"] == "BAD_HTML"

    rich = client.post(
        "/admin/broadcasts",
        json={"title": "T", "format": "rich", "body": {"ru": "<p>ok</p>", "uz": '<img src="/relative.jpg"/>'}},
    )
    assert rich.status_code == 400
    assert (rich.json()["detail"]["code"], rich.json()["detail"]["language"]) == ("BAD_HTML", "uz")


def test_a_rich_broadcast_over_its_limit_is_refused(client: TestClient):
    from app.utils.telegram_html import RICH_TEXT_LIMIT

    _login(client)

    resp = client.post(
        "/admin/broadcasts",
        json={"title": "T", "format": "rich", "body": {"ru": f"<p>{'x' * (RICH_TEXT_LIMIT + 1)}</p>"}},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "TEXT_TOO_LONG"


def test_a_rich_broadcast_takes_no_attached_photo(client: TestClient):
    """Its pictures sit inside the text; an attached one would have nowhere to go."""
    _login(client)
    created = client.post(
        "/admin/broadcasts", json={"title": "T", "format": "rich", "body": {"ru": RICH_BODY}}
    ).json()

    resp = _attach_photo(client, created["id"])

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "RICH_PICTURES_INLINE"


def _upload_media(client: TestClient, content: bytes = None):
    return client.post(
        "/admin/broadcasts/media",
        files={"file": ("compare.png", content or _png_bytes(), "image/png")},
    )


def test_a_picture_for_a_rich_broadcast_gets_an_address_telegram_can_download(
    client: TestClient, monkeypatch
):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz/")
    _login(client)

    resp = _upload_media(client)

    assert resp.status_code == 201
    url = resp.json()["url"]
    assert url.startswith("https://split-the-bill.uz/api/broadcasts/media/") and url.endswith(".jpg")
    client.post("/admin/auth/logout")
    served = client.get(url.removeprefix("https://split-the-bill.uz/api"))
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert "immutable" in served.headers["cache-control"]
    assert served.content[:2] == b"\xff\xd8"


def test_a_picture_is_refused_when_telegram_could_not_reach_it_or_it_is_no_picture(
    client: TestClient, monkeypatch
):
    _login(client)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    unreachable = _upload_media(client)
    assert unreachable.status_code == 503
    assert unreachable.json()["detail"]["code"] == "NO_PUBLIC_BASE_URL"

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz")
    assert _upload_media(client, b"not an image").status_code == 400


def test_only_the_operator_uploads_pictures(client: TestClient):
    assert _upload_media(client).status_code == 401


def test_only_stored_pictures_are_served(client: TestClient):
    assert client.get("/broadcasts/media/0123456789abcdef0123456789abcdef.jpg").status_code == 404
    assert client.get("/broadcasts/media/..%2F..%2F.env").status_code == 404
    assert client.get("/broadcasts/media/settings.py").status_code == 404


def _test_send(client: TestClient, payload: dict, photo: bytes | None = None):
    import json

    files = {"photo": ("cover.png", photo, "image/png")} if photo else None
    return client.post("/admin/broadcasts/test", data={"payload": json.dumps(payload)}, files=files)


def test_a_test_send_delivers_every_language_to_one_person_and_saves_nothing(
    client: TestClient, session, monkeypatch
):
    client.post("/users/", json={"telegram_id": 801, "username": "boss"})
    client.post("/users/", json={"telegram_id": 802, "username": "someone"})
    _login(client)
    outbox = []
    monkeypatch.setattr(
        broadcast_sender, "send_rich_message",
        lambda chat_id, html, reply_markup=None: outbox.append((chat_id, html, reply_markup)) or {},
    )

    resp = _test_send(
        client,
        {"format": "rich", "body": {"ru": RICH_BODY, "en": "<p>Hello</p>", "uz": " "}, "target": "@boss"},
    )

    assert resp.status_code == 200
    assert resp.json()["sent"] == ["ru", "en"]
    assert [(chat_id, html) for chat_id, html, _ in outbox] == [(801, RICH_BODY), (801, "<p>Hello</p>")]
    assert outbox[0][2]["inline_keyboard"][0][0]["text"] == "Открыть"
    assert session.exec(select(Broadcast)).all() == []


def test_a_test_send_reports_what_telegram_refused_and_in_which_language(
    client: TestClient, monkeypatch
):
    client.post("/users/", json={"telegram_id": 803, "username": "boss"})
    _login(client)

    def refusing(chat_id, html, reply_markup=None):
        if "Hello" in html:
            raise RuntimeError("Telegram error: Bad Request: can't parse rich message")
        return {}

    monkeypatch.setattr(broadcast_sender, "send_rich_message", refusing)

    resp = _test_send(
        client, {"format": "rich", "body": {"ru": "<p>Привет</p>", "en": "<p>Hello</p>"}, "target": "803"}
    )

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert (detail["code"], detail["language"], detail["sent"]) == ("TELEGRAM_REFUSED", "en", ["ru"])
    assert "can't parse" in detail["message"]


def test_a_test_send_uploads_its_photo_once_and_throws_it_away(client: TestClient, monkeypatch):
    import os

    client.post("/users/", json={"telegram_id": 804, "username": "boss"})
    _login(client)
    calls = []

    def fake_send_photo(chat_id, photo=None, caption=None, reply_markup=None, parse_mode="HTML", photo_path=None):
        calls.append({"photo": photo, "photo_path": photo_path, "exists": bool(photo_path) and os.path.exists(photo_path)})
        return {"photo": [{"file_id": "FILE-ID"}]}

    monkeypatch.setattr(broadcast_sender, "send_photo", fake_send_photo)

    resp = _test_send(
        client, {"body": {"ru": "Привет", "uz": "Salom"}, "with_button": False, "target": "boss"}, photo=_png_bytes()
    )

    assert resp.json()["sent"] == ["ru", "uz"]
    assert calls[0]["exists"] and calls[0]["photo"] is None
    assert calls[1] == {"photo": "FILE-ID", "photo_path": None, "exists": False}
    assert not os.path.exists(calls[0]["photo_path"])


def test_a_test_send_needs_a_known_person_and_a_well_formed_draft(client: TestClient):
    client.post("/users/", json={"telegram_id": 805, "username": "boss"})
    _login(client)

    unknown = _test_send(client, {"body": {"ru": "x"}, "target": "@ghost"})
    assert unknown.json()["detail"]["code"] == "UNKNOWN_RECIPIENTS"
    broken = _test_send(client, {"format": "rich", "body": {"ru": "<div>x</div>"}, "target": "boss"})
    assert broken.json()["detail"]["code"] == "BAD_HTML"
    photo_in_rich = _test_send(client, {"format": "rich", "body": {"ru": "<p>x</p>"}, "target": "boss"}, photo=_png_bytes())
    assert photo_in_rich.status_code == 409
    assert client.post("/admin/broadcasts/test", data={"payload": "{}"}).status_code == 422
