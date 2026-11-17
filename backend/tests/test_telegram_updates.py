"""Telegram's updates kept by the webhook and handled by the bot's worker:
each kept once, a lane in order and one at a time, a dead worker's update taken
again, a failure given up at once — but a payment tried again."""
import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.services.telegram_updates as telegram_updates
from app.jobs import telegram_updates as purge
from app.bot_worker import UpdateWorker, update_worker
from app.models import TelegramUpdate
from app.services.pro_payments import ProPayments
from app.services.telegram_updates import (
    INTERRUPTIONS, LEASE, PAYMENT_ATTEMPTS, TelegramUpdateQueue, lane_of,
)
from tests.telegram_world import WORKER, next_update_id

NOW = datetime(2026, 10, 5, 9, 0)


def _message(chat_id: int, text: str = "hi") -> dict:
    return {"update_id": next_update_id(), "message": {
        "message_id": 1, "text": text, "chat": {"id": chat_id}, "from": {"id": chat_id},
    }}


def _payment(user_id: int) -> dict:
    return {"update_id": next_update_id(), "message": {
        "chat": {"id": user_id}, "from": {"id": user_id}, "successful_payment": {"currency": "XTR"},
    }}


class _Bot:
    """What the bot was given to handle; it fails on the ids it is told to."""

    def __init__(self):
        self.seen: list[int] = []
        self.failing: set[int] = set()

    def handle(self, payload: dict) -> None:
        self.seen.append(payload["update_id"])
        if payload["update_id"] in self.failing:
            raise RuntimeError("Telegram error: Bad Gateway")


@pytest.fixture
def bot(monkeypatch) -> _Bot:
    stub = _Bot()
    monkeypatch.setattr(telegram_updates.BotUpdates, "handle", lambda self, payload: stub.handle(payload))
    return stub


def _keep(session: Session, *updates: dict) -> list[int]:
    queue = TelegramUpdateQueue(session)
    for update in updates:
        assert queue.accept(update, NOW)
    return [update["update_id"] for update in updates]


def test_the_webhook_keeps_an_update_once_and_wakes_the_worker(client: TestClient, session: Session, monkeypatch):
    woken = []
    monkeypatch.setattr(update_worker, "wake", lambda: woken.append(True))
    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)
    update = _message(42)

    assert client.post("/telegram/webhook", json=update).status_code == 200
    assert client.post("/telegram/webhook", json=update).status_code == 200

    kept = session.exec(select(TelegramUpdate)).all()
    assert [(row.update_id, row.lane, row.done_at) for row in kept] == [(update["update_id"], "chat:42", None)]
    assert woken == [True]



def test_the_webhook_answers_a_checkout_itself_and_keeps_nothing(client: TestClient, session: Session, monkeypatch):
    answered = []
    monkeypatch.setattr(update_worker, "wake", lambda: answered.append("woken"))
    monkeypatch.setattr(ProPayments, "answer_checkout", lambda self, query, now: answered.append(query["id"]))
    monkeypatch.setenv("TG_WEBHOOK_SECRET", "s3")

    assert client.post(
        "/telegram/webhook",
        json={"update_id": next_update_id(), "pre_checkout_query": {"id": "q1"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3"},
    ).status_code == 200

    assert answered == ["q1"]
    assert session.exec(select(TelegramUpdate)).all() == []

def test_lanes_keep_in_order_what_must_be_and_nothing_more():
    def tap(data: str, **where) -> dict:
        return {"update_id": 1, "callback_query": {"id": "cb", "data": data, **where}}

    assert lane_of(_message(42)) == "chat:42"
    assert lane_of(tap("menu:settings", message={"chat": {"id": 42}})) == "chat:42"
    # Every copy of a post carries its code: taps on any of them keep their order.
    assert lane_of(tap("share_paid:abc", inline_message_id="AAA")) == "post:abc"
    assert lane_of(tap("share_seat:abc:7", message={"chat": {"id": 42}})) == "post:abc"
    assert lane_of({"update_id": 1, "chosen_inline_result": {"result_id": "share:abc"}}) == "post:abc"
    # A payment being tried again holds up no conversation.
    assert lane_of(_payment(42)) == "payment:42"


def test_a_lane_is_handled_in_order_one_update_at_a_time(session: Session, bot):
    first, second, other = _keep(session, _message(1), _message(1), _message(2))
    queue = TelegramUpdateQueue(session)

    assert list(queue.claim(NOW, limit=10, holder=WORKER)) == [first, other]
    assert not queue.claim(NOW, limit=10, holder=WORKER)

    queue.handle(first, holder=WORKER)

    assert list(queue.claim(NOW, limit=10, holder=WORKER)) == [second]
    assert bot.seen == [first]




def test_an_earlier_update_delivered_late_waits_for_the_later_one_in_hand(session: Session, bot):
    earlier, later = _message(1), _message(1)
    queue = TelegramUpdateQueue(session)
    _keep(session, later)
    assert list(queue.claim(NOW, limit=10, holder=WORKER)) == [later["update_id"]]

    _keep(session, earlier)

    assert not queue.claim(NOW, limit=10, holder=WORKER)
    queue.handle(later["update_id"], holder=WORKER)
    assert list(queue.claim(NOW, limit=10, holder=WORKER)) == [earlier["update_id"]]


def test_a_worker_takes_nothing_more_of_a_lane_it_is_still_on(session: Session, bot):
    first, _ = _keep(session, _message(1), _message(1))
    queue = TelegramUpdateQueue(session)
    assert list(queue.claim(NOW, limit=10, holder=WORKER)) == [first]

    # Its lease ran out while it was still on the update.
    assert not queue.claim(NOW + LEASE, limit=10, holder=WORKER, busy_lanes=frozenset({"chat:1"}))


def test_a_worker_keeps_hold_of_a_slow_update(session: Session, bot):
    (update_id,) = _keep(session, _message(1))
    queue = TelegramUpdateQueue(session)
    queue.claim(NOW, limit=10, holder=WORKER)

    queue.hold([update_id], NOW + LEASE - timedelta(seconds=5), holder=WORKER)

    assert not queue.claim(NOW + LEASE, limit=10, holder="another")


def test_only_the_worker_holding_an_update_says_how_it_went(session: Session, bot, monkeypatch):
    (update_id,) = _keep(session, _message(1))
    queue = TelegramUpdateQueue(session)
    queue.claim(NOW, limit=10, holder=WORKER)
    # This worker was too slow to renew: another takes the update over while
    # the bot is still on it, and this worker's failure must not undo that.
    bot.failing.add(update_id)
    stall = bot.handle

    def taken_over(payload):
        assert list(TelegramUpdateQueue(session).claim(NOW + LEASE, limit=10, holder="another")) == [update_id]
        stall(payload)

    monkeypatch.setattr(bot, "handle", taken_over)
    queue.handle(update_id, holder=WORKER)

    kept = session.get(TelegramUpdate, update_id)
    assert (kept.claimed_by, kept.done_at, kept.attempts) == ("another", None, 2)
    queue.handle(update_id, holder=WORKER)
    assert bot.seen == [update_id]

def test_a_failed_update_is_given_up_at_once_and_its_lane_moves_on(session: Session, bot):
    failing, behind = _keep(session, _message(1), _message(1))
    bot.failing.add(failing)
    queue = TelegramUpdateQueue(session)

    queue.claim(NOW, limit=10, holder=WORKER)
    queue.handle(failing, holder=WORKER)

    kept = session.get(TelegramUpdate, failing)
    assert kept.done_at is not None and "Bad Gateway" in kept.error
    assert list(queue.claim(NOW, limit=10, holder=WORKER)) == [behind]


def test_a_failed_payment_is_tried_again_waiting_longer_each_time_until_given_up(session: Session, bot):
    payment, chat = _keep(session, _payment(1), _message(1))
    bot.failing.add(payment)
    queue = TelegramUpdateQueue(session)
    assert list(queue.claim(NOW, limit=10, holder=WORKER)) == [payment, chat]
    queue.handle(chat, holder=WORKER)

    waits = []
    for _ in range(PAYMENT_ATTEMPTS):
        queue.handle(payment, holder=WORKER)
        kept = session.get(TelegramUpdate, payment)
        if kept.done_at:
            break
        retry_at = kept.not_before
        waits.append(round((retry_at - datetime.utcnow()).total_seconds()))
        assert not queue.claim(retry_at - timedelta(seconds=1), limit=10, holder=WORKER)
        assert list(queue.claim(retry_at, limit=10, holder=WORKER)) == [payment]

    assert waits[:4] == [5, 10, 20, 40] and len(waits) == PAYMENT_ATTEMPTS - 1
    assert session.get(TelegramUpdate, payment).done_at is not None
    assert len(bot.seen) == PAYMENT_ATTEMPTS + 1


@pytest.mark.asyncio
async def test_the_worker_handles_what_the_webhook_keeps_lane_by_lane(session: Session, bot):
    engine = session.get_bind()
    worker = UpdateWorker(slots=1, sessions=lambda: Session(engine))
    first, second, other = _keep(session, _message(1), _message(1), _message(2))

    running = asyncio.create_task(worker.run())
    worker.wake()
    for _ in range(100):
        if len(bot.seen) == 3:
            break
        await asyncio.sleep(0.02)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    order = bot.seen
    assert sorted(order) == [first, second, other]
    assert order.index(first) < order.index(second)
    session.expire_all()
    assert all(row.done_at for row in session.exec(select(TelegramUpdate)).all())


def test_a_handled_update_is_forgotten_a_week_later_and_a_waiting_one_never(session: Session, bot):
    handled, waiting = _keep(session, _message(1), _message(2))
    queue = TelegramUpdateQueue(session)
    queue.claim(NOW, limit=1, holder=WORKER)
    queue.handle(handled, holder=WORKER)
    done_at = session.get(TelegramUpdate, handled).done_at

    assert purge.run(session, done_at + purge.KEPT_FOR - timedelta(minutes=1)) == 0
    assert purge.run(session, done_at + purge.KEPT_FOR + timedelta(minutes=1)) == 1
    assert [row.update_id for row in session.exec(select(TelegramUpdate)).all()] == [waiting]


def test_a_payment_given_up_on_is_kept_until_settled_by_hand(session: Session, bot):
    payment, other = _keep(session, _payment(1), _message(2))
    bot.failing.update({payment, other})
    queue = TelegramUpdateQueue(session)
    queue.claim(NOW, limit=10, holder=WORKER)
    queue.handle(other, holder=WORKER)
    for _ in range(PAYMENT_ATTEMPTS):
        queue.handle(payment, holder=WORKER)
        if session.get(TelegramUpdate, payment).done_at:
            break
        queue.claim(session.get(TelegramUpdate, payment).not_before, limit=10, holder=WORKER)

    later = datetime.utcnow() + purge.KEPT_FOR + timedelta(days=1)
    assert purge.run(session, later) == 1
    assert [row.update_id for row in session.exec(select(TelegramUpdate)).all()] == [payment]

    kept = session.get(TelegramUpdate, payment)
    kept.settled_at = datetime.utcnow()
    session.add(kept)
    session.commit()
    assert purge.run(session, later) == 1
