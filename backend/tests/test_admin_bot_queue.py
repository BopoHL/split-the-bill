"""The bot's queue in the admin panel: where it stands, what is in it, and
running a failed update again or settling a payment the worker gave up on."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.bot_worker import update_worker
from app.models import TelegramUpdate
from app.services.telegram_updates import TelegramUpdateQueue
from app.services.telegram_updates_admin import describe
from tests.telegram_world import next_update_id


@pytest.fixture
def admin(client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    from app.routers import admin as admin_router

    admin_router._LOGIN_ATTEMPTS.clear()
    assert client.post("/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}).status_code == 200
    return client


@pytest.fixture
def woken(monkeypatch) -> list[bool]:
    calls: list[bool] = []
    monkeypatch.setattr(update_worker, "wake", lambda: calls.append(True))
    return calls


def _message(chat_id: int, text: str) -> dict:
    return {"update_id": next_update_id(), "message": {
        "message_id": 1, "text": text, "chat": {"id": chat_id}, "from": {"id": chat_id, "username": f"u{chat_id}"},
    }}


def _payment(user_id: int) -> dict:
    return {"update_id": next_update_id(), "message": {
        "chat": {"id": user_id}, "from": {"id": user_id, "first_name": "Ann"},
        "successful_payment": {"currency": "XTR", "total_amount": 100, "invoice_payload": "pro:month:7"},
    }}


def _kept(session: Session, update: dict, **state) -> int:
    TelegramUpdateQueue(session).accept(update, datetime.utcnow() - timedelta(minutes=5))
    kept = session.get(TelegramUpdate, update["update_id"])
    for field, value in state.items():
        setattr(kept, field, value)
    session.add(kept)
    session.commit()
    return kept.update_id


@pytest.fixture
def queue(session: Session) -> dict[str, int]:
    now = datetime.utcnow()
    return {
        "waiting": _kept(session, _message(1, "/start")),
        "in_hand": _kept(session, _message(2, "/bills"), claimed_until=now + timedelta(seconds=20), claimed_by="w", attempts=1),
        "retrying": _kept(session, _payment(3), not_before=now + timedelta(minutes=1), attempts=2, error="RuntimeError('db')"),
        "handled": _kept(session, _message(4, "/menu"), done_at=now - timedelta(minutes=1), attempts=1),
        "failed": _kept(session, _message(5, "/pro"), done_at=now, error="RuntimeError('bug')", attempts=1),
        "unpaid": _kept(session, _payment(6), done_at=now, error="RuntimeError('db')", attempts=10),
    }


def test_the_panel_says_what_waits_what_is_in_hand_and_what_failed(admin: TestClient, queue):
    summary = admin.get("/admin/bot-queue").json()
    assert {key: summary[key] for key in (
        "waiting", "in_hand", "retrying", "handled_last_hour", "failed_last_day", "unsettled_payments",
    )} == {"waiting": 1, "in_hand": 1, "retrying": 1, "handled_last_hour": 1, "failed_last_day": 2, "unsettled_payments": 1}
    assert summary["slots"] == 4 and summary["oldest_waiting_at"]

    waiting = admin.get("/admin/bot-queue/updates").json()
    assert [(row["update_id"], row["state"]) for row in waiting["items"]] == [
        (queue["waiting"], "waiting"), (queue["in_hand"], "in_hand"), (queue["retrying"], "retry_later"),
    ]
    first = waiting["items"][0]
    assert (first["kind"], first["who"], first["what"], first["lane"]) == ("command", "@u1", "/start", "chat:1")

    failed = admin.get("/admin/bot-queue/updates", params={"view": "failed"}).json()["items"]
    assert [(row["update_id"], row["actions"]) for row in failed] == [
        (queue["unpaid"], ["retry", "settle"]), (queue["failed"], ["retry"]),
    ]
    payments = admin.get("/admin/bot-queue/updates", params={"view": "payments"}).json()["items"]
    assert [(row["update_id"], row["kind"], row["who"]) for row in payments] == [(queue["unpaid"], "payment", "Ann (6)")]

    found = admin.get("/admin/bot-queue/updates", params={"view": "all", "q": "5"}).json()
    assert [row["update_id"] for row in found["items"]] == [queue["failed"]] and found["total"] == 1


def test_a_failed_update_goes_back_into_the_queue(admin: TestClient, session: Session, queue, woken):
    row = admin.post(f"/admin/bot-queue/updates/{queue['failed']}/retry").json()

    assert (row["state"], row["attempts"], row["error"], row["actions"]) == ("waiting", 0, "RuntimeError('bug')", [])
    assert woken == [True]
    assert admin.post(f"/admin/bot-queue/updates/{queue['failed']}/retry").status_code == 409
    assert admin.post(f"/admin/bot-queue/updates/{queue['handled']}/retry").status_code == 409


def test_a_payment_given_up_on_is_settled_by_hand_and_leaves_the_list(admin: TestClient, queue):
    row = admin.post(f"/admin/bot-queue/updates/{queue['unpaid']}/settle").json()

    assert (row["state"], row["actions"]) == ("settled", [])
    assert admin.get("/admin/bot-queue/updates", params={"view": "payments"}).json()["items"] == []
    assert admin.get("/admin/bot-queue").json()["unsettled_payments"] == 0
    assert admin.post(f"/admin/bot-queue/updates/{queue['unpaid']}/settle").status_code == 409
    assert admin.post(f"/admin/bot-queue/updates/{queue['failed']}/settle").status_code == 409
    assert admin.post("/admin/bot-queue/updates/1/settle").status_code == 404


def test_the_queue_is_for_the_admin_only(client: TestClient):
    assert client.get("/admin/bot-queue").status_code == 401


def test_each_kind_of_update_reads_for_a_person():
    tap = {"callback_query": {"data": "share_paid:abc", "from": {"id": 9, "first_name": "Lea"}}}
    assert describe(tap) == ("post_button", "Lea (9)", "share_paid:abc")
    assert describe({"callback_query": {"data": "menu:settings", "from": {"id": 9, "username": "lea"}}})[0] == "button"
    assert describe({"message": {"photo": [{}], "caption": "чек", "from": {"id": 9}}}) == ("photo", "(9)", "чек")
    assert describe({"my_chat_member": {"new_chat_member": {"status": "kicked"}, "from": {"id": 9}}})[2] == "kicked"
    assert describe({"chosen_inline_result": {"result_id": "share:abc", "from": {"id": 9}}})[0] == "shared_post"
    assert describe({"update_id": 1, "edited_message": {}}) == ("other", None, "edited_message")
