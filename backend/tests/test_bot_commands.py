"""The bot's commands and the panel they open.

A typed command goes away once the bot has read it, and whatever it opens
takes the place of the previous panel — the chat keeps one menu, not a trail.
"""
import pytest
from sqlmodel import Session, select

import app.services.bot_commands as commands
from app.models import Bill, BotDialog, BotDialogStep, User
from app.repositories.bill_repo import BillRepository
from app.repositories.bot_dialog_repo import BotDialogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.bill_schemas import BillCreate
from app.services.bill_core_service import BillCoreService
from app.services.bot_flow_service import COMMANDS
from app.utils.bot_copy import LANGUAGES, t
from app.utils.telegram_html import rich_visible_length
from tests.bot_chat_world import CHAT_ID, GROUP_ID
from tests.telegram_world import next_update_id


@pytest.fixture
def onboarded(session: Session) -> User:
    user = User(
        telegram_id=CHAT_ID,
        settings={"language": "ru", "currency": "uzs", "onboarding_completed": True},
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_bills(session: Session, owner: User, count: int) -> None:
    service = BillCoreService(BillRepository(session), UserRepository(session))
    for i in range(count):
        service.create_bill(BillCreate(owner_id=owner.id, total_sum=1000 * (i + 1), title=f"Ужин {i}"))


def test_the_menu_lists_the_commands(bot_chat, onboarded):
    bot_chat.say("/menu")

    menu = bot_chat.last()
    for command in ("/new", "/bills", "/settings", "/help", "/pro"):
        assert command in menu.text
    assert menu.buttons()[0]["web_app"]["url"] == "https://split-the-bill.uz"
    assert menu.callbacks() == ["bill:new", "bills:0", "menu:settings", "menu:guide", "pro:offer"]


def test_typed_commands_leave_one_panel_and_no_trace(bot_chat, session: Session, onboarded):
    _make_bills(session, onboarded, 2)

    typed = [bot_chat.say(command) for command in ("/menu", "/bills", "/settings", "/menu")]

    assert len(bot_chat.visible()) == 1
    assert "/new" in bot_chat.last().text
    assert bot_chat.deleted_input == typed


def test_taps_redraw_the_panel_in_place(bot_chat, session: Session, onboarded):
    _make_bills(session, onboarded, 1)
    bot_chat.say("/menu")
    panel = bot_chat.last().id

    bot_chat.tap("bills:0")
    token = bot_chat.last().callbacks()[0]
    bot_chat.tap(token)
    bot_chat.tap("bills:0")
    bot_chat.tap("menu:main")

    assert [m.id for m in bot_chat.visible()] == [panel]
    assert "/new" in bot_chat.last().text


def test_menu_is_the_way_out_of_a_half_finished_flow(bot_chat, session: Session, onboarded):
    BotDialogRepository(session).save(
        BotDialog(chat_id=CHAT_ID, user_id=onboarded.id, step=BotDialogStep.BILL_HEADCOUNT)
    )

    bot_chat.say("/menu")

    assert BotDialogRepository(session).get_by_chat(CHAT_ID) is None


def test_a_command_addressed_to_the_bot_by_name_still_works(bot_chat, onboarded):
    bot_chat.say("/menu@SplitTheBillsBot")
    assert "/new" in bot_chat.last().text


def test_an_unknown_command_is_left_alone(bot_chat, onboarded):
    bot_chat.say("/whatever")

    assert bot_chat.visible() == []
    assert bot_chat.deleted_input == []


def test_the_store_verification_command_answers_with_its_token(bot_chat):
    # No onboarded user: the store checks a bot it has never talked to.
    bot_chat.say("/appss_verify")
    assert bot_chat.last().text == "appss_fc0ee6"


def test_the_store_verification_command_is_never_advertised():
    assert "appss_verify" not in commands.COMMANDS
    assert all("appss_verify" not in t(language, "menu") for language in LANGUAGES)


def test_help_opens_the_illustrated_guide(bot_chat, onboarded):
    bot_chat.say("/help")

    guide = bot_chat.last()
    assert guide.kind == "rich"
    assert "<h2>Как пользоваться Split Bill</h2>" in guide.text
    assert 'src="https://split-the-bill.uz/bot/guide-ru-1.png?v=' in guide.text
    assert guide.callbacks() == ["menu:main"]


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_guide_is_rich_html_telegram_accepts(bot_chat, session: Session, onboarded, language):
    onboarded.settings = {**onboarded.settings, "language": language}
    session.add(onboarded)
    session.commit()

    bot_chat.say("/help")

    assert rich_visible_length(bot_chat.last().text) > 0


def test_the_guide_goes_plain_when_telegram_refuses_rich_messages(bot_chat, onboarded):
    bot_chat.refuse_rich = True

    bot_chat.say("/help")

    guide = bot_chat.last()
    assert guide.kind == "text"
    assert "<b>1. Создайте счёт</b>" in guide.text


def test_from_the_guide_back_to_the_menu(bot_chat, onboarded):
    bot_chat.say("/help")

    bot_chat.tap("menu:main")

    [menu] = bot_chat.visible()
    assert menu.kind == "text"
    assert "/new" in menu.text


def test_bills_says_so_when_there_are_none(bot_chat, onboarded):
    bot_chat.say("/bills")

    assert "Счетов пока нет" in bot_chat.last().text
    assert bot_chat.last().callbacks() == ["bill:new", "menu:main"]


def test_bills_lists_them_with_a_button_each(bot_chat, session: Session, onboarded):
    _make_bills(session, onboarded, 3)

    bot_chat.say("/bills")

    listing = bot_chat.last()
    assert listing.text.count("•") == 3
    assert "открыт" in listing.text
    # Tapping one opens it in the chat, not straight in the app.
    assert [data.split(":")[0] for data in listing.callbacks()] == ["card", "card", "card", "menu"]


def test_a_short_page_offers_no_more_button(bot_chat, session: Session, onboarded):
    _make_bills(session, onboarded, 4)
    bot_chat.say("/bills")

    assert "⬇️ Ещё" not in bot_chat.last().labels()


def test_a_full_page_paginates_both_ways(bot_chat, session: Session, onboarded):
    _make_bills(session, onboarded, 12)
    bot_chat.say("/bills")
    assert "bills:10" in bot_chat.last().callbacks()

    bot_chat.tap("bills:10")

    second = bot_chat.last()
    assert second.text.count("•") == 2
    assert "bills:0" in second.callbacks()
    assert "bills:20" not in second.callbacks()


def test_commands_are_published_per_language_and_for_everyone_else(monkeypatch):
    monkeypatch.setenv("TG_TOKEN", "token")
    published = {}
    monkeypatch.setattr(
        commands, "set_my_commands",
        lambda cmds, language_code=None: published.__setitem__(language_code, cmds),
    )

    commands.register_bot_commands()

    assert set(published) == {None, "ru", "uz", "en"}
    assert [c["command"] for c in published["ru"]] == ["menu", "new", "bills", "settings", "help", "pro", "start"]
    assert published["uz"][2]["description"] == "Mening hisoblarim"
    assert published[None] == published["ru"]


def test_every_published_command_is_one_the_bot_answers():
    assert set(commands.COMMANDS) <= set(COMMANDS)


def test_registration_is_skipped_without_a_token(monkeypatch):
    monkeypatch.delenv("TG_TOKEN", raising=False)
    monkeypatch.setattr(
        commands, "set_my_commands",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call Telegram")),
    )
    commands.register_bot_commands()


def test_a_failed_registration_does_not_stop_startup(monkeypatch):
    monkeypatch.setenv("TG_TOKEN", "token")
    monkeypatch.setattr(
        commands, "set_my_commands",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Telegram error: flood wait")),
    )
    commands.register_bot_commands()


def test_a_listed_bill_opens_as_a_card_in_the_panel(bot_chat, session: Session, onboarded):
    _make_bills(session, onboarded, 1)
    bot_chat.say("/bills")
    token = bot_chat.last().callbacks()[0]

    bot_chat.tap(token)

    card = bot_chat.last()
    assert "Ужин 0" in card.text
    assert "Итого" in card.text
    open_bill = card.buttons()[0]
    assert open_bill["text"] == "📱 Открыть счёт в приложении"
    assert "startapp=bill_" in open_bill["url"]
    assert card.callbacks() == ["bills:0"]


def test_an_unknown_token_says_so_instead_of_failing(bot_chat, onboarded):
    bot_chat.tap("card:nope", on=1)
    assert bot_chat.last().text == "Счёт не найден."


def test_creating_a_bill_is_still_reachable_without_a_web_app_url(bot_chat, onboarded, monkeypatch):
    """The app button is the one thing that needs a public URL."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    bot_chat.say("/menu")

    menu = bot_chat.last()
    assert all("web_app" not in button for button in menu.buttons())
    assert "bill:new" in menu.callbacks()


def test_settings_change_the_language_and_say_so_in_it(bot_chat, session: Session, onboarded):
    bot_chat.say("/settings")
    assert bot_chat.last().callbacks() == ["settings:lang", "settings:cur", "menu:main"]

    bot_chat.tap("settings:lang")
    assert bot_chat.last().callbacks() == ["setlang:ru", "setlang:uz", "setlang:en", "menu:settings"]

    bot_chat.tap("setlang:en")

    session.expire_all()
    assert session.get(User, onboarded.id).settings["language"] == "en"
    # Already in the language just chosen, and settings stay open — whoever
    # came to fix one setting usually means to fix both.
    assert "Done" in bot_chat.last().text
    assert bot_chat.last().callbacks()[1] == "settings:cur"
    assert len(bot_chat.visible()) == 1


def test_settings_change_the_currency_without_restarting_onboarding(bot_chat, session: Session, onboarded):
    bot_chat.tap("settings:cur", on=1)
    assert bot_chat.last().callbacks()[:2] == ["setcur:uzs", "setcur:rub"]

    bot_chat.tap("setcur:eur")

    session.expire_all()
    stored = session.get(User, onboarded.id).settings
    assert stored["currency"] == "eur"
    # Still onboarded: this is not the onboarding question wearing a hat.
    assert stored["onboarding_completed"] is True


def _screens(product_events) -> list[dict]:
    return [
        {key: value for key, value in properties.items() if key != "surface"}
        for event, _, properties in product_events
        if event == "bot_screen_viewed"
    ]


def test_every_place_in_the_panel_is_counted_however_it_is_reached(
    bot_chat, session: Session, onboarded, product_events
):
    _make_bills(session, onboarded, 1)
    bill = session.exec(select(Bill)).one()

    bot_chat.say("/bills")
    bot_chat.tap(f"card:{bill.public_token}")
    bot_chat.tap("menu:main")
    bot_chat.tap("menu:guide")
    bot_chat.tap("menu:settings")
    bot_chat.say("/start")

    assert _screens(product_events) == [
        {"screen": "bills"},
        {"screen": "bill_card", "bill_id": bill.id},
        {"screen": "menu"},
        {"screen": "guide"},
        {"screen": "settings"},
        {"screen": "menu"},
    ]
    assert {properties["surface"] for _, _, properties in product_events} == {"bot"}


def test_every_command_counts_the_place_it_opens(bot_chat, onboarded, product_events):
    for command in ("/menu", "/bills", "/settings", "/help", "/pro"):
        bot_chat.say(command)

    assert [screen["screen"] for screen in _screens(product_events)] == ["menu", "bills", "settings", "guide", "pro"]


def test_a_setting_saved_is_no_new_visit_to_settings(bot_chat, onboarded, product_events):
    bot_chat.tap("menu:settings", on=1)
    bot_chat.tap("setlang:en")

    assert _screens(product_events) == [{"screen": "settings"}]


def test_a_card_that_could_not_be_opened_is_not_counted(bot_chat, onboarded, product_events):
    bot_chat.tap("card:nope", on=1)

    assert _screens(product_events) == []


def test_a_changed_setting_is_counted_with_what_it_became(bot_chat, onboarded, product_events):
    bot_chat.tap("setlang:en", on=1)
    bot_chat.tap("setcur:eur")

    assert [(event, properties) for event, _, properties in product_events if event.endswith("_changed")] == [
        ("language_changed", {"surface": "bot", "language": "en"}),
        ("currency_changed", {"surface": "bot", "currency": "eur"}),
    ]


def test_a_command_typed_in_a_group_is_counted_as_one_from_a_group(bot_chat, onboarded, product_events):
    bot_chat.say("/new@SplitTheBillsBot", chat_id=GROUP_ID)

    assert product_events == [
        ("bot_command", str(onboarded.id), {"surface": "bot", "command": "new", "chat": "group"}),
    ]


def _member(client, status: str, chat_type: str = "private"):
    return client.post("/telegram/webhook", json={"update_id": next_update_id(), "my_chat_member": {
        "chat": {"id": CHAT_ID, "type": chat_type},
        "from": {"id": CHAT_ID, "first_name": "Leo"},
        "date": 0,
        "old_chat_member": {"status": "member", "user": {"id": 1, "is_bot": True, "first_name": "Bot"}},
        "new_chat_member": {"status": status, "user": {"id": 1, "is_bot": True, "first_name": "Bot"}},
    }})


def test_the_bot_knows_when_it_is_blocked_and_let_back_in(client, session, onboarded):
    _member(client, "kicked")
    session.refresh(onboarded)
    assert onboarded.settings["bot_blocked"] is True

    _member(client, "member")
    session.refresh(onboarded)
    assert onboarded.settings["bot_blocked"] is False

    # In a group it is about the group, not about writing to this person.
    _member(client, "kicked", chat_type="group")
    session.refresh(onboarded)
    assert onboarded.settings["bot_blocked"] is False


def test_blocking_the_bot_and_letting_it_back_in_are_counted(client, onboarded, product_events):
    _member(client, "kicked")
    _member(client, "member")
    _member(client, "kicked", chat_type="group")

    assert [(event, properties) for event, _, properties in product_events] == [
        ("bot_access_changed", {"surface": "bot", "allowed": False}),
        ("bot_access_changed", {"surface": "bot", "allowed": True}),
    ]


def test_start_in_private_lets_the_bot_write(bot_chat, session, onboarded):
    onboarded.settings = {**onboarded.settings, "bot_blocked": True}
    session.add(onboarded)
    session.commit()

    bot_chat.say("/start")

    session.refresh(onboarded)
    assert onboarded.settings["bot_blocked"] is False


def test_in_a_group_a_command_points_to_the_private_chat(bot_chat, session: Session, onboarded):
    bot_chat.say("/new@SplitTheBillsBot", chat_id=GROUP_ID)
    bot_chat.say("3", chat_id=GROUP_ID)

    [pointer] = bot_chat.visible(GROUP_ID)
    assert pointer.buttons()[0]["url"] == "https://t.me/SplitTheBillsBot"
    assert BotDialogRepository(session).get_by_chat(GROUP_ID) is None
    assert bot_chat.deleted_input == []


def test_in_a_group_a_menu_button_opens_nothing(bot_chat, session: Session, onboarded):
    bot_chat.tap("bill:new", on=1, chat_id=GROUP_ID)

    assert bot_chat.visible(GROUP_ID) == []
    assert BotDialogRepository(session).get_by_chat(GROUP_ID) is None


def test_a_card_of_a_bill_no_longer_theirs_says_so(bot_chat, session: Session, onboarded):
    stranger = User(telegram_id=777, settings={"language": "ru"})
    session.add(stranger)
    session.commit()
    session.refresh(stranger)
    _make_bills(session, stranger, 1)
    bill = session.exec(select(Bill).where(Bill.owner_id == stranger.id)).one()

    bot_chat.tap(f"card:{bill.public_token}", on=1)

    assert bot_chat.last().text == "Счёт не найден."
