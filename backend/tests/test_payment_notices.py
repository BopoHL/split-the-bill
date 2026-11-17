"""The bot tells an owner who has paid them."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.jobs.payment_notices as payment_notices
import app.services.owner_messages as owner_messages
from app.models import Bill, BillUser, User

OWNER = 800


@pytest.fixture
def sent(monkeypatch):
    outbox = []

    def fake_send(chat_id, text, reply_markup=None, **kwargs):
        outbox.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return {"message_id": 1}

    monkeypatch.setattr(owner_messages, "send_message", fake_send)
    monkeypatch.setenv("TG_BOT_USERNAME", "SplitTheBillsBot")
    return outbox


def _table(client: TestClient, session: Session) -> tuple[int, dict[str, int], dict[str, int]]:
    """Owner, Ann and Bob each on a seat with a dish; one more guest seat nobody
    took, with a dish too. Returns the bill, the seats by name and the people."""
    owner = client.post("/users/", json={"telegram_id": OWNER, "username": "owner"}).json()["id"]
    bill = client.post("/bills/", json={
        "owner_id": owner, "total_sum": 0, "title": "Ужин", "include_owner": True, "expected_people": 4,
    }).json()["id"]
    user = session.get(User, owner)
    user.settings = {"language": "ru", "bot_blocked": False}
    session.add(user)
    session.commit()

    free = session.exec(
        select(BillUser).where(BillUser.bill_id == bill, BillUser.user_id.is_(None)).order_by(BillUser.seat_index)
    ).all()
    people = {}
    for name, seat in zip(("Ann", "Bob"), free):
        people[name] = client.post("/users/", json={"telegram_id": 801 + len(people), "name": name}).json()["id"]
        client.post(f"/bills/{bill}/seats/{seat.id}/claim", json={"user_id": people[name]})
    seats = {"Ann": free[0].id, "Bob": free[1].id, "guest": free[2].id}
    for seat_id in seats.values():
        item = client.post(f"/bills/{bill}/items", json={"name": "Плов", "price": 30000, "count": 1}).json()
        client.post(f"/bills/{bill}/items/{item['id']}/assign", json={"participant_id": seat_id, "is_assigned": True})
    return bill, seats, {"owner": owner, **people}


def _pay(client: TestClient, bill: int, seat: int, by: int) -> None:
    response = client.post(f"/bills/{bill}/participants/{seat}/payment", json={"is_paid": True, "user_id": by})
    assert response.status_code == 200, response.text


def test_the_owner_hears_who_paid_and_how_many_have_once(client: TestClient, session: Session, sent, product_events):
    bill, seats, people = _table(client, session)
    _pay(client, bill, seats["Ann"], people["Ann"])
    _pay(client, bill, seats["Bob"], people["Bob"])

    assert payment_notices.run(session, datetime.utcnow()) == 1
    assert payment_notices.run(session, datetime.utcnow()) == 0

    [message] = sent
    assert message["chat_id"] == OWNER
    assert message["text"] == "✅ Оплата по счёту «Ужин»: Ann, Bob.\nОплатили 2 из 3."
    assert message["markup"]["inline_keyboard"][0][0]["url"].endswith("startapp=bill_" + _token(session, bill))
    assert [(event, properties) for event, _, properties in product_events if event == "payment_notice_result"] == [
        ("payment_notice_result", {"surface": "server", "bill_id": bill, "ok": True}),
    ]


def test_a_seat_the_owner_marked_paid_is_no_news_to_them(client: TestClient, session: Session, sent):
    bill, seats, people = _table(client, session)
    _pay(client, bill, seats["guest"], people["owner"])

    assert payment_notices.run(session, datetime.utcnow()) == 0
    assert sent == []


def test_the_last_payment_says_everyone_has_paid(client: TestClient, session: Session, sent):
    bill, seats, people = _table(client, session)
    _pay(client, bill, seats["guest"], people["owner"])
    _pay(client, bill, seats["Ann"], people["Ann"])
    payment_notices.run(session, datetime.utcnow())

    _pay(client, bill, seats["Bob"], people["Bob"])
    payment_notices.run(session, datetime.utcnow())

    assert sent[-1]["text"] == "✅ Оплата по счёту «Ужин»: Bob.\n🎉 Оплатили все."


def _token(session: Session, bill: int) -> str:
    return session.get(Bill, bill).public_token
