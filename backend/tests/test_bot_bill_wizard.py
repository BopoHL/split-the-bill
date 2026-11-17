"""Creating a bill without leaving the chat.

Each answer advances the dialog and redraws the one panel: the questions do
not pile up, and what the person typed — a card number among it — goes once
the bot has it. The bill carries the answers, and the receipt photo ends up
queued against that bill.
"""
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, select

import app.services.bot_flow_service as flow
from app.models import Bill, ReceiptTask, User
from app.repositories.bot_dialog_repo import BotDialogRepository
from app.repositories.payment_method_repo import PaymentMethodRepository
from app.repositories.user_repo import UserRepository
from app.schemas.payment_method_schemas import PaymentMethodCreate
from app.services.payment_method_service import PaymentMethodService
from app.services.scan_allowance import ScanLimitReached
from tests.bot_chat_world import CHAT_ID


@pytest.fixture
def onboarded(session: Session) -> User:
    user = User(
        telegram_id=CHAT_ID,
        name="Lea",
        settings={"language": "ru", "currency": "uzs", "onboarding_completed": True},
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def queued(monkeypatch) -> list[int]:
    submitted: list[int] = []
    monkeypatch.setattr(flow.queue_manager, "submit", submitted.append)
    return submitted


def _reach_receipt_step(bot_chat, headcount="3", payment="8600123412341234"):
    bot_chat.say("/new")
    bot_chat.say(headcount)
    bot_chat.tap("pay:new")
    bot_chat.say(payment)


def test_new_asks_how_many_people(bot_chat, onboarded):
    bot_chat.say("/new")

    assert "На сколько человек" in bot_chat.last().text
    assert bot_chat.last().callbacks() == ["bill:cancel"]


def test_the_menu_button_asks_in_the_same_panel(bot_chat, onboarded):
    bot_chat.say("/menu")
    menu = bot_chat.last().id

    bot_chat.tap("bill:new")

    assert bot_chat.last().id == menu
    assert "На сколько человек" in bot_chat.last().text


def test_a_headcount_that_is_not_a_number_is_rejected(bot_chat, session: Session, onboarded):
    bot_chat.say("/new")
    bot_chat.say("человек пять")

    assert "Нужно число" in bot_chat.last().text
    assert BotDialogRepository(session).get_by_chat(CHAT_ID).step == "bill_headcount"


def test_saved_cards_are_offered_before_typing_new_ones(bot_chat, session: Session, onboarded):
    PaymentMethodService(
        PaymentMethodRepository(session), UserRepository(session)
    ).create(onboarded.id, PaymentMethodCreate(value="8600123412341234", label="Uzcard"))

    bot_chat.say("/new")
    bot_chat.say("4")

    question = bot_chat.last()
    assert question.labels()[0] == "Uzcard"
    assert question.callbacks()[1:] == ["pay:new", "bill:cancel"]


def test_a_saved_card_goes_straight_to_the_receipt(bot_chat, session: Session, onboarded):
    method = PaymentMethodService(
        PaymentMethodRepository(session), UserRepository(session)
    ).create(onboarded.id, PaymentMethodCreate(value="8600123412341234", label="Uzcard"))

    bot_chat.say("/new")
    bot_chat.say("4")
    bot_chat.tap(f"pay:{method.id}")

    assert "фото чека" in bot_chat.last().text
    assert session.exec(select(Bill)).first().expected_people == 4


def test_the_whole_flow_stays_in_one_message_and_typed_answers_go(bot_chat, onboarded):
    typed = [bot_chat.say("/new"), bot_chat.say("3")]
    bot_chat.tap("pay:new")
    typed.append(bot_chat.say("8600123412341234"))

    assert len(bot_chat.visible()) == 1
    assert bot_chat.deleted_input == typed


def test_answers_land_on_the_bill_and_the_receipt_is_asked_for(bot_chat, session: Session, onboarded):
    _reach_receipt_step(bot_chat)

    bill = session.exec(select(Bill)).first()
    assert bill.expected_people == 3
    assert bill.payment_method_id is not None

    prompt = bot_chat.last()
    assert "фото чека" in prompt.text
    # UZS, so the fiscal-receipt shortcut is on offer and points at the scanner;
    # without a photo to hand, the bill opens in the app.
    scan, open_bill, menu = prompt.buttons()
    assert scan["url"].endswith(f"scan_{bill.public_token}")
    assert open_bill["url"].endswith(f"bill_{bill.public_token}")
    assert menu["callback_data"] == "menu:main"


def test_no_qr_shortcut_outside_uzbek_receipts(bot_chat, session: Session, onboarded):
    onboarded.settings = {**onboarded.settings, "currency": "usd"}
    session.add(onboarded)
    session.commit()

    _reach_receipt_step(bot_chat)

    assert [button.get("url", "").split("startapp=")[-1][:5] for button in bot_chat.last().buttons()] == ["bill_", ""]


def test_cancel_goes_back_to_the_menu_and_forgets_the_answers(bot_chat, session: Session, onboarded):
    bot_chat.say("/new")
    bot_chat.say("3")

    bot_chat.tap("bill:cancel")

    assert "/new" in bot_chat.last().text
    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None
    assert session.exec(select(Bill)).first() is None


def test_the_photo_is_queued_against_that_bill_and_the_flow_ends(
    bot_chat, session: Session, onboarded, queued, product_events
):
    _reach_receipt_step(bot_chat)
    photo = bot_chat.say(photo=[{"file_id": "small"}, {"file_id": "biggest"}])

    bill = session.exec(select(Bill)).first()
    task = session.exec(select(ReceiptTask)).first()
    assert task.bill_id == bill.id
    assert queued == [task.id]
    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None
    assert photo in bot_chat.deleted_input

    [final] = bot_chat.visible()
    assert "Счёт создан" in final.text
    assert final.labels() == ["👥 Пригласить участников", "📱 Открыть счёт в приложении", "← Меню"]
    assert bill.public_token in final.buttons()[1]["url"]
    assert [(event, properties) for event, _, properties in product_events] == [
        ("bot_command", {"surface": "bot", "command": "new"}),
        ("bill_create_opened", {"surface": "bot"}),
        ("bill_create_step", {"surface": "bot", "step": "payment"}),
        ("bill_created", {"surface": "bot", "source": "bot", "bill_id": bill.id}),
        ("receipt_scan_started", {"surface": "bot", "mode": "photo", "target": "new_bill"}),
    ]
    assert {distinct_id for _, distinct_id, _ in product_events} == {str(onboarded.id)}


def test_the_wizard_opened_from_the_menu_is_counted_like_new(bot_chat, onboarded, product_events):
    bot_chat.say("/menu")
    bot_chat.tap("bill:new")

    assert [event for event, _, _ in product_events if event.startswith("bill_create")] == ["bill_create_opened"]


def test_only_an_accepted_headcount_moves_the_wizard_on(bot_chat, onboarded, product_events):
    bot_chat.say("/new")
    bot_chat.say("много")
    bot_chat.say("3")

    steps = [properties for event, _, properties in product_events if event == "bill_create_step"]
    assert steps == [{"surface": "bot", "step": "payment"}]


def test_past_the_free_scans_the_bill_is_made_for_filling_in_by_hand(
    bot_chat, session: Session, onboarded, queued, monkeypatch
):
    def spent(user_id, now):
        raise ScanLimitReached(3)

    monkeypatch.setattr(flow.ScanAllowance, "ensure", lambda self, user_id, now: spent(user_id, now))
    _reach_receipt_step(bot_chat)
    bot_chat.say(photo=[{"file_id": "biggest"}])

    final = bot_chat.last()
    assert "3 в день" in final.text
    assert "добавить в приложении" in final.text
    assert final.labels()[0] == "⭐ Оформить Pro"
    assert queued == []


def test_text_where_a_photo_is_expected_is_answered_not_swallowed(bot_chat, onboarded):
    _reach_receipt_step(bot_chat)
    bot_chat.say("сейчас пришлю")

    assert "Жду фото" in bot_chat.last().text
    assert len(bot_chat.visible()) == 1


def test_another_command_ends_the_flow(bot_chat, session: Session, onboarded):
    bot_chat.say("/new")
    bot_chat.say("/bills")
    bot_chat.say("3")

    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None
    assert "Счетов пока нет" in bot_chat.last().text


def _saved_card(session: Session, user: User):
    return PaymentMethodService(
        PaymentMethodRepository(session), UserRepository(session)
    ).create(user.id, PaymentMethodCreate(value="8600123412341234", label="Uzcard"))


def test_a_second_tap_on_the_card_makes_no_second_bill(bot_chat, session: Session, onboarded):
    method = _saved_card(session, onboarded)
    bot_chat.say("/new")
    bot_chat.say("4")

    bot_chat.tap(f"pay:{method.id}")
    bot_chat.tap(f"pay:{method.id}")

    assert len(session.exec(select(Bill)).all()) == 1


def test_a_payment_button_from_another_step_does_nothing(bot_chat, session: Session, onboarded):
    method = _saved_card(session, onboarded)
    bot_chat.say("/new")

    bot_chat.tap(f"pay:{method.id}", on=1)
    bot_chat.tap("pay:new", on=1)

    assert session.exec(select(Bill)).first() is None
    assert BotDialogRepository(session).get_by_chat(CHAT_ID).step == "bill_headcount"


def test_an_answer_lands_under_news_that_came_in_since_the_question(bot_chat, onboarded):
    bot_chat.say("/new")
    news = bot_chat.send_message(CHAT_ID, "Чек распознан")["message_id"]

    bot_chat.say("3")
    panel = bot_chat.last().id
    bot_chat.tap("pay:new")
    bot_chat.say("8600123412341234")

    assert [m.id for m in bot_chat.visible()] == [news, panel]
    assert "фото чека" in bot_chat.last().text


def test_a_question_left_too_long_is_no_longer_asked(bot_chat, session: Session, onboarded):
    bot_chat.say("/new")
    dialog = BotDialogRepository(session).get_by_chat(CHAT_ID)
    dialog.updated_at = datetime.utcnow() - flow.DIALOG_TTL - timedelta(minutes=1)
    session.add(dialog)
    session.commit()

    typed = bot_chat.say("3")

    assert typed not in bot_chat.deleted_input
    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None
    # Nor shown: the panel no longer asks a question nobody is waiting on.
    assert "делит счёт" in bot_chat.last().text


def test_a_receipt_sent_long_after_the_question_is_still_read(
    bot_chat, session: Session, onboarded, queued
):
    """Its bill is made already; the photo is what the panel keeps asking for."""
    _reach_receipt_step(bot_chat)
    dialog = BotDialogRepository(session).get_by_chat(CHAT_ID)
    dialog.updated_at = datetime.utcnow() - flow.DIALOG_TTL - timedelta(minutes=1)
    session.add(dialog)
    session.commit()

    bot_chat.say(photo=[{"file_id": "biggest"}])

    assert len(queued) == 1


def test_a_photo_the_bot_could_not_take_stays_in_the_chat(
    bot_chat, onboarded, queued, monkeypatch
):
    """Past the free scans nothing is saved: the photo is their only copy."""
    def spent(self, user_id, now):
        raise ScanLimitReached(3)

    monkeypatch.setattr(flow.ScanAllowance, "ensure", spent)
    _reach_receipt_step(bot_chat)

    photo = bot_chat.say(photo=[{"file_id": "biggest"}])

    assert photo not in bot_chat.deleted_input


def test_a_tap_again_after_a_failed_draw_makes_no_second_bill(
    bot_chat, session: Session, onboarded, monkeypatch
):
    import app.services.bot_panel as panel

    PaymentMethodService(
        PaymentMethodRepository(session), UserRepository(session)
    ).create(onboarded.id, PaymentMethodCreate(value="8600123412341234", label="Uzcard"))
    bot_chat.say("/new")
    bot_chat.say("3")
    card = bot_chat.last().callbacks()[0]

    def telegram_down(*args, **kwargs):
        raise RuntimeError("Telegram request failed: read timeout")

    monkeypatch.setattr(panel, "edit_chat_message_text", telegram_down)
    monkeypatch.setattr(panel, "send_message", telegram_down)
    with pytest.raises(AssertionError):  # the worker records the failed update
        bot_chat.tap(card)
    monkeypatch.setattr(panel, "edit_chat_message_text", bot_chat.edit_chat_message_text)
    monkeypatch.setattr(panel, "send_message", bot_chat.send_message)
    bot_chat.tap(card)

    bills = session.exec(select(Bill).where(Bill.owner_id == onboarded.id)).all()
    assert len(bills) == 1
    assert "фото чека" in bot_chat.last().text


def test_the_receipt_step_leads_back_to_the_menu(bot_chat, session: Session, onboarded):
    _reach_receipt_step(bot_chat)

    bot_chat.tap("menu:main")

    assert "/new" in bot_chat.last().text
    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None
    # The bill stays: it is there to fill in from the app.
    assert session.exec(select(Bill)).first() is not None
