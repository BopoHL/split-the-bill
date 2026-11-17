"""Bot onboarding over the webhook.

/start walks a newcomer through the language, stores the app defaults and
leaves the welcome picture; an onboarded user lands on the menu; the webhook
secret is still enforced.
"""
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import User
from app.repositories.bot_dialog_repo import BotDialogRepository
from app.utils.currency import DEFAULT_CURRENCY, VALID_CURRENCIES
from tests.bot_chat_world import CHAT_ID
from tests.telegram_world import next_update_id


def _settings(session: Session) -> dict:
    user = session.exec(select(User).where(User.telegram_id == CHAT_ID)).first()
    session.refresh(user)
    return dict(user.settings or {})


def test_start_asks_a_newcomer_for_a_language_in_every_language(bot_chat):
    typed = bot_chat.say("/start", language_code="en")

    prompt = bot_chat.last()
    assert prompt.text == "🌐 Выберите язык\nTilni tanlang\nChoose your language"
    assert prompt.labels() == ["Русский", "O‘zbekcha", "English"]
    assert bot_chat.deleted_input == [typed]


def test_language_finishes_onboarding_with_default_currency(bot_chat, session: Session):
    bot_chat.say("/start")
    bot_chat.tap("lang:uz")

    stored = _settings(session)
    assert stored["language"] == "uz"
    assert stored["currency"] == DEFAULT_CURRENCY
    assert stored["onboarding_completed"] is True


def test_onboarding_is_counted_once_in_the_language_chosen(bot_chat, product_events):
    bot_chat.say("/start")
    question = bot_chat.last()
    bot_chat.tap("lang:uz", on=question)
    # The same question answered again, from where it once was.
    bot_chat.tap("lang:en", on=question)

    finished = [properties for event, _, properties in product_events if event == "onboarding_completed"]
    assert finished == [{"surface": "bot", "language": "uz"}]


def test_language_keeps_a_currency_chosen_in_the_app_before_start(bot_chat, session: Session):
    session.add(User(telegram_id=CHAT_ID, settings={"currency": "usd"}))
    session.commit()

    bot_chat.say("/start")
    bot_chat.tap("lang:ru")

    stored = _settings(session)
    assert stored["currency"] == "usd"
    assert stored["onboarding_completed"] is True


def test_the_language_question_gives_way_to_the_welcome_picture(bot_chat):
    bot_chat.say("/start")
    bot_chat.tap("lang:uz")

    [welcome] = bot_chat.visible()
    assert welcome.kind == "photo"
    assert welcome.photo.startswith("https://split-the-bill.uz/bot/welcome-uz.png?v=")
    assert "Split Bill" in welcome.text
    assert welcome.buttons()[0]["web_app"]["url"] == "https://split-the-bill.uz"
    assert welcome.callbacks() == ["menu:guide", "menu:main"]


def test_welcome_falls_back_to_text_when_the_picture_fails(bot_chat):
    bot_chat.refuse_photo = True

    bot_chat.say("/start")
    bot_chat.tap("lang:ru")

    [welcome] = bot_chat.visible()
    assert welcome.kind == "text"
    assert "Split Bill" in welcome.text


def test_the_welcome_opens_the_menu_under_itself(bot_chat):
    bot_chat.say("/start")
    bot_chat.tap("lang:ru")
    welcome = bot_chat.last()

    bot_chat.tap("menu:main", on=welcome)

    assert [m.kind for m in bot_chat.visible()] == ["photo", "text"]
    assert "/new" in bot_chat.last().text


def test_start_after_onboarding_goes_straight_to_the_menu(bot_chat):
    bot_chat.say("/start")
    bot_chat.tap("lang:ru")

    bot_chat.say("/start")
    bot_chat.say("/start")

    welcome, menu = bot_chat.visible()
    assert welcome.kind == "photo"
    assert "/bills" in menu.text
    assert "pro:offer" in menu.callbacks()


def test_start_with_a_deep_link_payload_still_starts(bot_chat):
    bot_chat.say("/start join_abc123")
    assert bot_chat.visible()


def test_where_a_start_link_came_from_is_counted_and_the_first_source_kept(bot_chat, product_events):
    bot_chat.say("/start src_TikTok-Autumn")
    bot_chat.say("/start promo42")
    bot_chat.say("/start")

    starts = [properties for event, _, properties in product_events if event == "bot_command"]
    assert starts == [
        {"surface": "bot", "command": "start", "start": "source", "source": "tiktok-autumn"},
        {"surface": "bot", "command": "start", "start_ref": "promo42"},
        {"surface": "bot", "command": "start"},
    ]
    assert [properties for event, _, properties in product_events if event == "$set_once"] == [
        {"first_start": "source", "first_source": "tiktok-autumn"},
    ]


def test_someone_new_to_the_bot_is_kept_as_come_from_it(bot_chat, product_events):
    bot_chat.say("/start promo42")

    assert [properties for event, _, properties in product_events if event == "$set_once"] == [
        {"first_start": "bot"},
    ]


def test_non_start_message_is_ignored(bot_chat):
    bot_chat.say("hello there")

    assert bot_chat.visible() == []
    assert bot_chat.deleted_input == []


def test_webhook_rejects_bad_secret(client: TestClient, monkeypatch):
    monkeypatch.setenv("TG_WEBHOOK_SECRET", "s3cr3t")
    update = {
        "update_id": next_update_id(),
        "message": {
            "message_id": 1, "text": "/start",
            "chat": {"id": CHAT_ID, "type": "private"},
            "from": {"id": CHAT_ID, "language_code": "ru", "first_name": "Lea"},
        },
    }

    assert client.post("/telegram/webhook", json=update).status_code == 403
    assert client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    ).status_code == 403
    assert client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
    ).status_code == 200


def test_the_command_list_button_of_an_old_menu_opens_the_menu(bot_chat):
    bot_chat.say("/start")
    bot_chat.tap("lang:ru")
    old_menu = bot_chat.send_message(CHAT_ID, "старое меню")["message_id"]

    bot_chat.tap("menu:commands", on=old_menu)

    assert "/bills" in bot_chat.last().text


def test_a_currency_the_bot_does_not_offer_falls_back_instead_of_sticking(bot_chat, session: Session):
    """The keyboard is the only way in, but a callback is just a string."""
    bot_chat.say("/start")
    bot_chat.tap("cur:xxx")

    assert _settings(session)["currency"] == "uzs"


def test_every_settings_currency_is_one_the_app_accepts(bot_chat, session: Session):
    session.add(User(telegram_id=CHAT_ID, settings={"language": "ru", "onboarding_completed": True}))
    session.commit()

    bot_chat.tap("settings:cur", on=1)

    offered = {data.removeprefix("setcur:") for data in bot_chat.last().callbacks() if data.startswith("setcur:")}
    assert offered == VALID_CURRENCIES


def test_a_language_question_from_before_the_panel_goes_once_answered(bot_chat, session: Session):
    session.add(User(telegram_id=CHAT_ID, settings={"language": "ru", "onboarding_completed": True}))
    session.commit()
    old_question = bot_chat.send_message(CHAT_ID, "🌐 Выберите язык интерфейса.")["message_id"]
    bot_chat.say("/new")
    question = bot_chat.last()

    bot_chat.tap("lang:en", on=old_question)

    assert old_question not in [m.id for m in bot_chat.visible()]
    assert question in bot_chat.visible()
    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None


def test_without_its_secret_the_webhook_takes_nothing_in_production(client: TestClient, monkeypatch):
    """Anyone could post an update as any user, and the bot would act for them."""
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)

    answer = client.post("/telegram/webhook", json={"update_id": next_update_id(), "message": {"chat": {"id": 1}, "text": "/start"}})

    assert answer.status_code == 503
