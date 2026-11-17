import pytest

from app.utils.telegram_html import (
    RICH_MEDIA_LIMIT,
    TelegramHtmlError,
    rich_visible_length,
    visible_length,
)

PICTURE = '<img src="https://split-the-bill.uz/api/broadcasts/media/abc.jpg"/>'


def test_an_ordinary_message_counts_utf16_units_without_markup():
    assert visible_length("<b>Привет</b> 🚀") == len("Привет ") + 2


def test_an_ordinary_message_has_no_pictures_or_paragraphs():
    with pytest.raises(TelegramHtmlError, match="<img>"):
        visible_length(PICTURE)
    with pytest.raises(TelegramHtmlError, match="<p>"):
        visible_length("<p>Абзац</p>")


def test_a_rich_message_puts_a_picture_between_paragraphs():
    body = f"<h2>Split·Bill 1.0</h2><p>Что нового</p>{PICTURE}<p>Промокод: <code>PRO</code></p>"

    assert rich_visible_length(body) == len("Split·Bill 1.0Что новогоПромокод: PRO")


def test_a_rich_message_counts_characters_not_utf16_units():
    assert rich_visible_length("<p>🚀</p>") == 1


def test_a_rich_message_reads_tables_lists_and_self_closing_tags():
    body = (
        "<table bordered striped><tr><th>Free</th><th>Pro</th></tr>"
        '<tr><td>3</td><td align="right">∞</td></tr></table>'
        "<ul><li>Один</li><li>Два<br/>строки</li></ul><hr/>"
    )
    assert rich_visible_length(body) == len("FreePro3∞ОдинДвастроки")


def test_a_picture_needs_an_address_telegram_can_download():
    with pytest.raises(TelegramHtmlError, match="src"):
        rich_visible_length("<img/>")
    with pytest.raises(TelegramHtmlError, match="src"):
        rich_visible_length('<img src="/api/broadcasts/media/abc.jpg"/>')
    assert rich_visible_length('<img src="tg://emoji?id=5368324170671202286"/>') == 0


def test_a_rich_message_refuses_what_telegram_does_not_know():
    with pytest.raises(TelegramHtmlError, match="<div>"):
        rich_visible_length("<div>x</div>")
    with pytest.raises(TelegramHtmlError, match="не закрыт"):
        rich_visible_length("<p>x")
    with pytest.raises(TelegramHtmlError, match="&amp;"):
        rich_visible_length("<p>Tom & Jerry</p>")


def test_only_a_rich_message_may_mark_an_anchor():
    assert rich_visible_length('<a name="pro"></a><p><a href="#pro">Pro</a></p>') == len("Pro")
    with pytest.raises(TelegramHtmlError, match="href"):
        visible_length('<a name="pro">x</a>')


def test_a_rich_message_holds_a_limited_number_of_pictures():
    assert rich_visible_length(PICTURE * RICH_MEDIA_LIMIT) == 0
    with pytest.raises(TelegramHtmlError, match=str(RICH_MEDIA_LIMIT)):
        rich_visible_length(PICTURE * (RICH_MEDIA_LIMIT + 1))
