"""The panel: one message per chat that the bot redraws instead of adding to."""
import pytest
from sqlmodel import Session

import app.services.bot_panel as panel_module
from app.models import BotPanel
from app.repositories.bot_panel_repo import BotPanelRepository
from app.services.bot_panel import BotPanels, View
from tests.bot_chat_world import CHAT_ID

MENU = View("Меню", [[{"text": "Счета", "callback_data": "bills:0"}]])
BILLS = View("Счета", [[{"text": "← Меню", "callback_data": "menu:main"}]])
GUIDE = View("<h2>Как пользоваться</h2>", [], rich=True, fallback="Как пользоваться")


@pytest.fixture
def panels(session: Session) -> BotPanels:
    return BotPanels(BotPanelRepository(session))


def _stored(session: Session) -> BotPanel | None:
    return BotPanelRepository(session).get_by_chat(CHAT_ID)


def test_a_fresh_panel_is_remembered(panels, session, bot_chat):
    panels.open(CHAT_ID, MENU)

    assert [m.text for m in bot_chat.visible()] == ["Меню"]
    assert _stored(session).message_id == bot_chat.last().id


def test_a_second_panel_takes_the_first_one_down(panels, bot_chat):
    panels.open(CHAT_ID, MENU)
    panels.open(CHAT_ID, BILLS)

    assert [m.text for m in bot_chat.visible()] == ["Счета"]


def test_a_redraw_edits_the_panel_where_it_stands(panels, bot_chat):
    panels.open(CHAT_ID, MENU)
    first = bot_chat.last().id

    panels.redraw(CHAT_ID, BILLS)
    panels.redraw(CHAT_ID, BILLS)

    assert [(m.id, m.text) for m in bot_chat.visible()] == [(first, "Счета")]


def test_a_tap_on_the_panel_redraws_it_and_on_anything_else_opens_a_fresh_one(panels, bot_chat):
    bot_chat.send_message(CHAT_ID, "Добро пожаловать")
    welcome = bot_chat.last().id
    panels.open(CHAT_ID, MENU)
    menu = bot_chat.last().id

    panels.tapped(CHAT_ID, menu, BILLS)
    assert bot_chat.last().id == menu

    panels.tapped(CHAT_ID, welcome, MENU)
    assert [m.text for m in bot_chat.visible()] == ["Добро пожаловать", "Меню"]
    assert bot_chat.last().id != menu


def test_a_panel_the_person_deleted_is_drawn_again(panels, bot_chat):
    panels.open(CHAT_ID, MENU)
    bot_chat.last().deleted = True

    panels.redraw(CHAT_ID, BILLS)

    assert [m.text for m in bot_chat.visible()] == ["Счета"]


def test_rich_and_text_replace_each_other_rather_than_edit(panels, bot_chat):
    panels.open(CHAT_ID, MENU)
    panels.redraw(CHAT_ID, GUIDE)
    assert [m.kind for m in bot_chat.visible()] == ["rich"]

    panels.redraw(CHAT_ID, MENU)
    assert [(m.kind, m.text) for m in bot_chat.visible()] == [("text", "Меню")]


def test_a_refused_rich_view_goes_out_plain(panels, bot_chat):
    bot_chat.refuse_rich = True

    panels.open(CHAT_ID, GUIDE)

    assert [(m.kind, m.text) for m in bot_chat.visible()] == [("text", "Как пользоваться")]


def test_a_panel_too_old_to_delete_loses_its_buttons(panels, bot_chat):
    panels.open(CHAT_ID, MENU)
    old = bot_chat.last()
    bot_chat.undeletable.add(old.id)

    panels.open(CHAT_ID, BILLS)

    assert old.markup is None
    assert bot_chat.last().text == "Счета"


def test_closing_takes_the_panel_down_and_forgets_it(panels, session, bot_chat):
    panels.open(CHAT_ID, MENU)

    panels.close(CHAT_ID)

    assert bot_chat.visible() == []
    assert _stored(session) is None


def test_what_the_person_typed_is_cleared(panels, bot_chat):
    panels.clear_input(CHAT_ID, 7)

    assert bot_chat.deleted_input == [7]


def test_an_answer_right_under_the_panel_changes_it_in_place(panels, bot_chat):
    panels.open(CHAT_ID, MENU)
    panel = bot_chat.last().id

    first, second = bot_chat.typed(), bot_chat.typed()
    panels.answer(CHAT_ID, first, BILLS)
    panels.answer(CHAT_ID, second, MENU)

    assert [(m.id, m.text) for m in bot_chat.visible()] == [(panel, "Меню")]
    assert bot_chat.deleted_input == [first, second]


def test_an_answer_with_news_above_it_gets_a_fresh_panel_under_it(panels, bot_chat):
    panels.open(CHAT_ID, MENU)
    bot_chat.send_message(CHAT_ID, "Чек распознан")

    panels.answer(CHAT_ID, bot_chat.typed(), BILLS)

    assert [m.text for m in bot_chat.visible()] == ["Чек распознан", "Счета"]


def test_a_rich_view_that_may_have_gone_out_is_not_sent_again_plain(panels, bot_chat, monkeypatch):
    def timed_out(chat_id, html, reply_markup=None):
        raise RuntimeError("Telegram request failed: read timeout")

    monkeypatch.setattr(panel_module, "send_rich_message", timed_out)

    with pytest.raises(RuntimeError):
        panels.open(CHAT_ID, GUIDE)
    assert bot_chat.visible() == []
