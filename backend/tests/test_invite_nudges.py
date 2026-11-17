"""The bot hands the invite to an owner whose bill nobody has joined."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.jobs.invite_nudges as invite_nudges
import app.services.owner_messages as owner_messages
from app.models import Bill, BillUser, User

# 14:00 in Tashkent, well clear of the quiet hours.
NOON = datetime(2026, 8, 11, 9, 0)


@pytest.fixture
def sent(monkeypatch):
    outbox = []

    def fake_send(chat_id, text, reply_markup=None, **kwargs):
        outbox.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return {"message_id": 1}

    monkeypatch.setattr(owner_messages, "send_message", fake_send)
    monkeypatch.setenv("TG_BOT_USERNAME", "SplitTheBillsBot")
    return outbox


def _bill(
    client: TestClient, session: Session, *, created_at: datetime, writes: bool | None = False, people: int = 3,
) -> Bill:
    """A bill laid for `people`, made at `created_at`, by an owner the bot may write to unless told otherwise."""
    owner = client.post("/users/", json={"telegram_id": 700, "username": "owner"}).json()["id"]
    bill_id = client.post("/bills/", json={
        "owner_id": owner, "total_sum": 0, "title": "Ужин", "include_owner": True, "expected_people": people,
    }).json()["id"]
    user = session.get(User, owner)
    user.settings = {"language": "ru", **({} if writes is None else {"bot_blocked": writes})}
    bill = session.get(Bill, bill_id)
    bill.created_at = created_at
    session.add(user)
    session.add(bill)
    session.commit()
    return bill


def _results(product_events) -> list[dict]:
    return [properties for event, _, properties in product_events if event == "invite_nudge_result"]


def test_two_hours_on_the_owner_of_a_bill_nobody_joined_gets_the_invite_once(
    client: TestClient, session: Session, sent, product_events
):
    bill = _bill(client, session, created_at=NOON)

    assert invite_nudges.run(session, NOON + timedelta(hours=1)) == 0
    assert invite_nudges.run(session, NOON + timedelta(hours=2)) == 1
    assert invite_nudges.run(session, NOON + timedelta(hours=3)) == 0

    [message] = sent
    assert message["chat_id"] == 700
    assert "«Ужин» пока никто не присоединился" in message["text"]
    buttons = [button for row in message["markup"]["inline_keyboard"] for button in row]
    assert buttons[0]["callback_data"] == f"invite:{bill.public_token}"
    assert buttons[1]["url"].endswith(f"startapp=bill_{bill.public_token}")
    assert _results(product_events) == [{"surface": "server", "bill_id": bill.id, "ok": True}]


def test_a_bill_someone_has_joined_is_left_alone(client: TestClient, session: Session, sent):
    bill = _bill(client, session, created_at=NOON)
    guest = client.post("/users/", json={"telegram_id": 701, "username": "guest"}).json()["id"]
    seat = session.exec(select(BillUser).where(BillUser.bill_id == bill.id, BillUser.user_id.is_(None))).first()
    client.post(f"/bills/{bill.id}/seats/{seat.id}/claim", json={"user_id": guest})

    assert invite_nudges.run(session, NOON + timedelta(hours=2)) == 0
    assert sent == []


def test_a_bill_laid_for_its_owner_alone_is_left_alone(client: TestClient, session: Session, sent):
    bill = _bill(client, session, created_at=NOON, people=1)

    assert invite_nudges.run(session, NOON + timedelta(hours=2)) == 0
    assert sent == []
    assert session.get(Bill, bill.id).invite_nudged_at is None


def test_the_night_waits_for_the_morning(client: TestClient, session: Session, sent):
    # 22:00 in Tashkent: two hours on is past midnight.
    evening = datetime(2026, 8, 11, 17, 0)
    _bill(client, session, created_at=evening)

    assert invite_nudges.run(session, evening + timedelta(hours=2)) == 0
    # 09:30 the next morning.
    assert invite_nudges.run(session, evening + timedelta(hours=11, minutes=30)) == 1


def test_an_owner_the_bot_cannot_write_to_is_counted_and_not_tried_again(
    client: TestClient, session: Session, sent, product_events
):
    bill = _bill(client, session, created_at=NOON, writes=None)

    assert invite_nudges.run(session, NOON + timedelta(hours=2)) == 0
    assert invite_nudges.run(session, NOON + timedelta(hours=3)) == 0

    assert sent == []
    assert _results(product_events) == [{"surface": "server", "bill_id": bill.id, "ok": False, "reason": "no_chat"}]


def test_a_blocked_bot_is_remembered(client: TestClient, session: Session, monkeypatch, product_events):
    bill = _bill(client, session, created_at=NOON)

    def blocked(*args, **kwargs):
        raise RuntimeError("Telegram error: Forbidden: bot was blocked by the user")

    monkeypatch.setattr(owner_messages, "send_message", blocked)
    invite_nudges.run(session, NOON + timedelta(hours=2))

    session.expire_all()
    assert session.get(User, bill.owner_id).settings["bot_blocked"] is True
    assert _results(product_events) == [{"surface": "server", "bill_id": bill.id, "ok": False, "reason": "unreachable"}]


def test_a_message_that_failed_is_counted_and_the_chat_kept_open(
    client: TestClient, session: Session, monkeypatch, product_events
):
    bill = _bill(client, session, created_at=NOON)

    def flaky(*args, **kwargs):
        raise RuntimeError("Telegram error: Too Many Requests: retry after 5")

    monkeypatch.setattr(owner_messages, "send_message", flaky)
    assert invite_nudges.run(session, NOON + timedelta(hours=2)) == 0

    session.expire_all()
    assert session.get(User, bill.owner_id).settings["bot_blocked"] is False
    assert _results(product_events) == [{"surface": "server", "bill_id": bill.id, "ok": False, "reason": "error"}]
