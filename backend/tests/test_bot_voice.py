"""A voice message to the bot, whenever it comes: a new bill from what was said,
or — with a bill of theirs open from the last hours — that one if they pick it.
Sent while the wizard waits for its receipt, it fills that bill. Pro only."""
from datetime import datetime, timedelta

from sqlalchemy import update

import pytest
from sqlmodel import Session, select

from app.models import Bill, BillItem, BillUser, ProSource, User
from app.repositories.bot_dialog_repo import BotDialogRepository
from tests.bot_chat_world import CHAT_ID
from tests.pro_world import grant

VOICE = {"file_id": "voice-1", "duration": 7, "mime_type": "audio/ogg"}


@pytest.fixture
def lea(session: Session) -> User:
    user = User(telegram_id=CHAT_ID, name="Lea", settings={"language": "ru", "currency": "uzs", "onboarding_completed": True})
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def pro(session: Session, lea: User) -> User:
    grant(session, lea, ProSource.PROMO, datetime.utcnow() - timedelta(days=1), 30)
    return lea


def _events(product_events, prefix="voice_input"):
    return [(event, properties) for event, _, properties in product_events if event.startswith(prefix)]


def test_without_pro_a_voice_message_opens_pro_and_is_not_listened_to(bot_chat, session: Session, lea, model, product_events):
    sent = bot_chat.say(voice=VOICE)

    panel = bot_chat.last()
    assert "Счёт голосом — в Pro" in panel.text
    assert panel.labels()[0] == "⭐ Оформить Pro"
    assert model["transcription"] is None
    assert sent not in bot_chat.deleted_input
    assert ("paywall_opened", {"surface": "bot", "reason": "voice"}) in [(e, p) for e, _, p in product_events]


def test_in_the_wizard_the_voice_fills_the_bill_it_just_made(bot_chat, session: Session, pro, model, product_events):
    bot_chat.say("/new")
    bot_chat.say("3")
    bot_chat.tap("pay:new")
    bot_chat.say("8600123412341234")
    bill = session.exec(select(Bill)).one()
    me = session.exec(select(BillUser).where(BillUser.bill_id == bill.id, BillUser.user_id == pro.id)).one()
    model["heard"] = "плов 80 мой, чай 10 Ане"
    model["answer"] = {
        "items": [{"ref": "n1", "name": "Плов", "amount": 80000}, {"ref": "n2", "name": "Чай", "amount": 10000}],
        "assign": [{"item": "n1", "people": [me.id]}, {"item": "n2", "people": ["Аня"]}],
    }

    bot_chat.say(voice=VOICE)

    session.expire_all()
    assert sorted(item.name for item in session.exec(select(BillItem)).all()) == ["Плов", "Чай"]
    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None
    panel = bot_chat.last()
    assert "добавлено позиций — 2, распределено — 2" in panel.text
    assert panel.labels() == ["👥 Пригласить участников", "📱 Открыть счёт в приложении", "← Меню"]
    # The bill's dishes and names help the transcription spell them.
    assert model["transcription"]["file"] == ("voice.ogg", b"receipt-bytes")
    assert _events(product_events) == [
        ("voice_input_sent", {"surface": "bot", "input": "voice", "bill_id": bill.id}),
        ("voice_input_result", {"surface": "bot", "bill_id": bill.id, "input": "voice", "ok": True, "added": 2, "assigned": 2}),
    ]


def test_with_no_open_bill_the_voice_makes_one_and_seats_who_it_names(bot_chat, session: Session, pro, model, product_events):
    model["heard"] = "ужин в Рыбе: рыба 120 — Дима"
    model["answer"] = {
        "title": "Ужин в Рыбе",
        "items": [{"ref": "n1", "name": "Рыба", "amount": 120000}],
        "assign": [{"item": "n1", "people": ["Дима"]}],
    }

    bot_chat.say(voice=VOICE)

    bill = session.exec(select(Bill)).one()
    assert (bill.title, bill.expected_people, bill.total_sum) == ("Ужин в Рыбе", 2, 12000000)
    dima = session.exec(select(BillUser).where(BillUser.guest_name == "Дима")).one()
    assert dima.allocated_amount == 12000000
    assert "«Ужин в Рыбе»: добавлено позиций — 1" in bot_chat.last().text
    assert ("bill_created", {"surface": "bot", "source": "voice", "bill_id": bill.id}) in [(e, p) for e, _, p in product_events]


def test_the_menu_says_a_voice_message_works_any_time(bot_chat, lea):
    bot_chat.say("/menu")

    assert "Пришлите голосовое в любой момент" in bot_chat.last().text


def test_right_after_the_menu_a_voice_message_makes_the_bill(bot_chat, session: Session, pro, model):
    bot_chat.say("/start")
    model["heard"] = "кола 15"
    model["answer"] = {"items": [{"ref": "n1", "name": "Кола", "amount": 15000}]}

    bot_chat.say(voice=VOICE)

    assert [item.name for item in session.exec(select(BillItem)).all()] == ["Кола"]
    assert "добавлено позиций — 1" in bot_chat.last().text


def test_a_bill_left_open_since_yesterday_is_not_offered(bot_chat, session: Session, pro, model, client):
    old = client.post("/bills/", json={"owner_id": pro.id, "total_sum": 0, "title": "Вчера", "include_owner": True}).json()
    session.execute(update(Bill).where(Bill.id == old["id"]).values(created_at=datetime.utcnow() - timedelta(days=1)))
    session.commit()
    model["heard"] = "кола 15"
    model["answer"] = {"items": [{"ref": "n1", "name": "Кола", "amount": 15000}]}

    bot_chat.say(voice=VOICE)

    item = session.exec(select(BillItem)).one()
    assert item.bill_id != old["id"]
    assert "Куда записать?" not in bot_chat.last().text


def test_with_open_bills_it_asks_which_one_and_fills_the_one_tapped(bot_chat, session: Session, pro, model, client):
    older = client.post("/bills/", json={"owner_id": pro.id, "total_sum": 0, "title": "Обед", "include_owner": True}).json()
    newer = client.post("/bills/", json={"owner_id": pro.id, "total_sum": 0, "title": "Ужин", "include_owner": True}).json()
    model["heard"] = "кола 15"
    model["answer"] = {"items": [{"ref": "n1", "name": "Кола", "amount": 15000}]}

    bot_chat.say(voice=VOICE)

    question = bot_chat.last()
    assert "«кола 15»" in question.text and "Куда записать?" in question.text
    # A new bill first: a voice message out of the blue is most often a new meal.
    assert question.callbacks()[:3] == ["voice:new", f"voice:{newer['public_token']}", f"voice:{older['public_token']}"]
    assert model["chat"] is None

    bot_chat.tap(f"voice:{older['public_token']}", on=question)

    items = session.exec(select(BillItem)).all()
    assert [(item.bill_id, item.name) for item in items] == [(older["id"], "Кола")]
    assert "«Обед»: добавлено позиций — 1" in bot_chat.last().text
    # The question is answered: tapping it again does nothing more.
    bot_chat.tap(f"voice:{older['public_token']}", on=question)
    assert len(session.exec(select(BillItem)).all()) == 1


def test_a_new_bill_that_gets_nothing_from_the_voice_goes_again(bot_chat, session: Session, pro, model, client):
    client.post("/bills/", json={"owner_id": pro.id, "total_sum": 0, "title": "Обед", "include_owner": True})
    model["heard"] = "э-э-э"
    bot_chat.say(voice=VOICE)

    bot_chat.tap("voice:new")

    assert [bill.title for bill in session.exec(select(Bill)).all()] == ["Обед"]
    assert "Не понял, что поменять. Услышал: «э-э-э»" in bot_chat.last().text


def test_a_voice_message_too_long_is_not_listened_to(bot_chat, pro, model):
    bot_chat.say(voice={**VOICE, "duration": 600})

    assert "Слишком длинное голосовое" in bot_chat.last().text
    assert model["transcription"] is None
