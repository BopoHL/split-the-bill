"""Prepared-message share endpoint (Bot API 8.0 savePreparedInlineMessage) and
the bot's join-welcome DM.

The actual Telegram calls are stubbed — we only verify access control, the
prepared id / DM plumbing, and that captions are escaped and buttons are plain.
What the group share says, and how it is kept current, is in test_shared_bill.
"""
import json
import time
import hashlib
import hmac
from urllib.parse import quote, urlencode

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import BillUser, Invite, SharedBillMessage, User
import app.services.shared_bill_service as shared_mod
from app.services.invite_service import invite_start_param
from app.utils.telegram import mini_app_link
import app.services.bill_participant_service as participant_mod


def _auth_headers(telegram_id: int) -> dict[str, str]:
    user = quote(json.dumps({"id": telegram_id}))
    init_data = f"user={user}&auth_date={int(time.time())}&hash=dev-test"
    return {"X-Telegram-Init-Data": init_data}


def _signed_auth_headers(telegram_id: int, token: str) -> dict[str, str]:
    values = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": telegram_id}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"X-Telegram-Init-Data": urlencode(values)}


def test_prepare_share_forbidden_for_outsider(client: TestClient, monkeypatch):
    monkeypatch.setattr(shared_mod, "save_prepared_text_message", lambda *a, **k: "X")
    owner = client.post("/users/", json={"telegram_id": 557, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 1, "include_owner": True}
    ).json()
    outsider = client.post("/users/", json={"telegram_id": 558, "username": "x"}).json()

    resp = client.post(
        f"/bills/{bill['id']}/prepare-share",
        # Spoofing the owner's body id must not override the authenticated user.
        json={"user_id": owner["id"], "text": "hi", "cta_label": "go"},
        headers=_auth_headers(558),
    )
    assert resp.status_code == 403


def test_prepare_share_requires_telegram_auth(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 561, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 1, "include_owner": True}
    ).json()
    resp = client.post(
        f"/bills/{bill['id']}/prepare-share",
        json={"user_id": owner["id"], "text": "no auth"},
        headers={"X-Telegram-Init-Data": ""},
    )
    assert resp.status_code == 401


def _bill_with_guest_seat(client: TestClient, telegram_id: int) -> tuple[dict, dict, dict]:
    """An open bill whose one guest seat has a dish on it."""
    owner = client.post(
        "/users/", json={"telegram_id": telegram_id, "username": "o", "name": "Leonid"}
    ).json()
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner["id"],
            "total_sum": 0,
            "title": "Ужин",
            "payment_details": "8600 0000 0000 1234",
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    item = client.post(
        f"/bills/{bill['id']}/items", json={"name": "Lagman", "price": 40, "count": 1}
    ).json()
    guest = next(
        p
        for p in client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()["participants"]
        if p["is_guest"]
    )
    client.post(
        f"/bills/{bill['id']}/items/assign-batch?requester_id={owner['id']}",
        json={"ops": [{"item_id": item["id"], "participant_id": guest["id"], "is_assigned": True}]},
    )
    return owner, bill, guest


def _capture_prepared(monkeypatch) -> list[tuple[int, dict]]:
    prepared: list[tuple[int, dict]] = []
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz")
    monkeypatch.setattr(
        shared_mod,
        "save_prepared_text_message",
        lambda uid, **message: prepared.append((uid, message)) or "PERSONAL123",
    )
    return prepared


def test_a_personal_invite_is_the_bills_post_with_a_link_to_the_seat(
    client: TestClient, monkeypatch, session: Session
):
    prepared = _capture_prepared(monkeypatch)
    owner, bill, guest = _bill_with_guest_seat(client, 570)

    resp = client.post(
        f"/bills/{bill['id']}/seats/{guest['id']}/prepare-invite",
        json={"lang": "ru"},
        headers=_auth_headers(570),
    )
    shared = client.post(f"/bills/{bill['id']}/prepare-share", json={"lang": "ru"}, headers=_auth_headers(570))

    assert resp.status_code == 200 and shared.status_code == 200
    assert resp.json()["prepared_message_id"] == "PERSONAL123"
    (uid, personal), (_, group) = prepared
    assert uid == 570
    # Word for word the post anyone shares, picture included.
    assert personal["text_html"] == group["text_html"]
    assert personal["text_html"].startswith("👥 <b>Участники</b>")
    assert personal["link_preview_options"]["url"].startswith(
        f"https://split-the-bill.uz/api/bills/public/{bill['public_token']}/card.png"
    )
    # Its link sits whoever follows it on this seat, so it is for one person.
    assert personal["private_chats_only"] is True
    assert group["private_chats_only"] is False
    invite = session.exec(select(Invite).where(Invite.seat_participant_id == guest["id"])).one()
    buttons = [button for row in personal["reply_markup"]["inline_keyboard"] for button in row]
    [open_button] = [button for button in buttons if "url" in button]
    assert open_button["url"] == mini_app_link(invite_start_param(invite.code))
    # Whose seat it is is known already: no seat to take, «I've paid» takes it.
    assert not any(button.get("callback_data", "").startswith("share_seat:") for button in buttons)
    assert personal["result_id"] == f"share:{invite.code}"
    # Kept current like any shared post.
    assert session.exec(select(SharedBillMessage).where(SharedBillMessage.invite_code == invite.code)).one()

    session.expire_all()
    assert session.get(BillUser, guest["id"]).user_id is None


def test_a_personal_invite_is_written_in_the_requested_language(client: TestClient, monkeypatch):
    prepared = _capture_prepared(monkeypatch)
    _, bill, guest = _bill_with_guest_seat(client, 581)

    client.post(
        f"/bills/{bill['id']}/seats/{guest['id']}/prepare-invite",
        json={"lang": "en"},
        headers=_auth_headers(581),
    )

    [(_, message)] = prepared
    assert "👥 <b>Participants</b>" in message["text_html"]
    assert "🧾 Open" in [button["text"] for row in message["reply_markup"]["inline_keyboard"] for button in row]


def test_prepare_personal_seat_invite_rejects_taken_seat(
    client: TestClient, monkeypatch
):
    monkeypatch.setattr(shared_mod, "save_prepared_text_message", lambda *a, **k: "X")
    owner = client.post("/users/", json={"telegram_id": 571, "username": "o"}).json()
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner["id"],
            "total_sum": 0,
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    guest = next(
        p for p in client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()["participants"]
        if p["is_guest"]
    )
    joiner = client.post("/users/", json={"telegram_id": 572, "username": "j"}).json()
    client.post(
        f"/bills/{bill['id']}/seats/{guest['id']}/claim",
        json={"user_id": joiner["id"]},
    )

    resp = client.post(
        f"/bills/{bill['id']}/seats/{guest['id']}/prepare-invite",
        json={"lang": "ru"},
        headers=_auth_headers(571),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SEAT_TAKEN"


def test_prepare_personal_seat_invite_owner_only(client: TestClient, monkeypatch):
    monkeypatch.setattr(shared_mod, "save_prepared_text_message", lambda *a, **k: "X")
    owner = client.post("/users/", json={"telegram_id": 573, "username": "o"}).json()
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner["id"],
            "total_sum": 0,
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    guest = next(
        p for p in client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()["participants"]
        if p["is_guest"]
    )
    outsider = client.post("/users/", json={"telegram_id": 574, "username": "x"}).json()

    resp = client.post(
        f"/bills/{bill['id']}/seats/{guest['id']}/prepare-invite",
        json={"lang": "ru"},
        headers=_auth_headers(outsider["telegram_id"]),
    )
    assert resp.status_code == 403


def test_prepare_share_verifies_telegram_signature_in_production(
    client: TestClient, monkeypatch
):
    owner = client.post("/users/", json={"telegram_id": 562, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 1, "include_owner": True}
    ).json()
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.setenv("TG_TOKEN", "test-token")
    monkeypatch.setattr(shared_mod, "save_prepared_text_message", lambda *args, **kwargs: "SIGNED")

    invalid = client.post(
        f"/bills/{bill['id']}/prepare-share",
        json={"text": "invalid"},
        headers=_auth_headers(562),
    )
    assert invalid.status_code == 401

    valid = client.post(
        f"/bills/{bill['id']}/prepare-share",
        json={"text": "valid"},
        headers=_signed_auth_headers(562, "test-token"),
    )
    assert valid.status_code == 200
    assert valid.json()["prepared_message_id"] == "SIGNED"


def test_join_welcome_sends_onboarding_once(client: TestClient, monkeypatch):
    calls = []

    def fake_send(chat_id, text, reply_markup=None, parse_mode="HTML"):
        calls.append((chat_id, text))
        return {}

    monkeypatch.setattr(participant_mod, "send_message", fake_send)

    owner = client.post("/users/", json={"telegram_id": 600, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "title": "Ужин", "include_owner": True}
    ).json()
    joiner = client.post("/users/", json={"telegram_id": 601, "username": "j"}).json()
    client.post(
        "/bills/join-by-token",
        json={"token": bill["public_token"], "user_id": joiner["id"]},
    )

    # First trigger: the bot DMs the joiner its one-time onboarding message.
    r1 = client.post(
        f"/bills/{bill['id']}/join-welcome",
        # The body id is deliberately wrong; the signed header is authoritative.
        json={"user_id": owner["id"], "lang": "ru"},
        headers=_auth_headers(601),
    )
    assert r1.status_code == 204
    assert len(calls) == 1
    assert calls[0][0] == 601
    assert "Split Bill" in calls[0][1]

    # Second trigger: already onboarded → no further DM.
    r2 = client.post(
        f"/bills/{bill['id']}/join-welcome",
        json={"lang": "ru"},
        headers=_auth_headers(601),
    )
    assert r2.status_code == 204
    assert len(calls) == 1


def test_join_welcome_clears_blocked_flag_after_write_access(
    client: TestClient, session: Session, monkeypatch
):
    calls = []

    def fake_send(chat_id, text, reply_markup=None, parse_mode="HTML"):
        calls.append((chat_id, text))
        return {}

    monkeypatch.setattr(participant_mod, "send_message", fake_send)

    owner = client.post("/users/", json={"telegram_id": 604, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "title": "Ужин", "include_owner": True}
    ).json()
    joiner = client.post("/users/", json={"telegram_id": 605, "username": "j"}).json()
    client.post(
        "/bills/join-by-token",
        json={"token": bill["public_token"], "user_id": joiner["id"]},
    )

    stored = session.exec(select(User).where(User.id == joiner["id"])).one()
    stored.settings = {"bot_blocked": True}
    session.add(stored)
    session.commit()

    r1 = client.post(
        f"/bills/{bill['id']}/join-welcome",
        json={"lang": "ru"},
        headers=_auth_headers(605),
    )

    assert r1.status_code == 204
    assert len(calls) == 1
    session.expire_all()
    settings = session.exec(select(User).where(User.id == joiner["id"])).one().settings
    assert settings["welcome_sent"] is True
    assert settings["bot_blocked"] is False

    calls.clear()
    stored = session.exec(select(User).where(User.id == joiner["id"])).one()
    stored.settings = {**stored.settings, "bot_blocked": True}
    session.add(stored)
    session.commit()

    r2 = client.post(
        f"/bills/{bill['id']}/join-welcome",
        json={"lang": "ru"},
        headers=_auth_headers(605),
    )

    assert r2.status_code == 204
    assert calls == []
    session.expire_all()
    settings = session.exec(select(User).where(User.id == joiner["id"])).one().settings
    assert settings["welcome_sent"] is True
    assert settings["bot_blocked"] is False

def test_join_welcome_forbidden_for_non_participant(client: TestClient, monkeypatch):
    monkeypatch.setattr(participant_mod, "send_message", lambda *a, **k: {})
    owner = client.post("/users/", json={"telegram_id": 602, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 1, "include_owner": True}
    ).json()
    outsider = client.post("/users/", json={"telegram_id": 603, "username": "x"}).json()

    resp = client.post(
        f"/bills/{bill['id']}/join-welcome",
        json={"user_id": owner["id"], "lang": "en"},
        headers=_auth_headers(603),
    )
    assert resp.status_code == 403


def test_public_receipt_404_without_receipt(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 559, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 1, "include_owner": True}
    ).json()
    detail = client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()
    # No receipt attached → 404; unknown token → 404.
    assert client.get(f"/bills/public/{detail['public_token']}/receipt").status_code == 404
    assert client.get("/bills/public/nope-nope/receipt").status_code == 404
