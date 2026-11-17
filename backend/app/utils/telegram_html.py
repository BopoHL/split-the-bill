"""Telegram's flavours of HTML.

Neither is HTML: only a listed set of tags is understood, every other `<` is a
parse error, and a broadcast that trips one is rejected for every single
recipient. Checking it once, when the operator writes it, turns a failed
send into a form error.

The ordinary dialect formats a message or a caption. The rich one is what
sendRichMessage reads: paragraphs, headings, lists, tables and pictures that
sit between paragraphs instead of above the text.
"""
import re
from dataclasses import dataclass
from html.parser import HTMLParser

# A photo drops the limit from 4096 to 1024: the caption travels with the
# picture, not as a message of its own.
# https://core.telegram.org/bots/api#sendphoto
CAPTION_LIMIT = 1024
# https://core.telegram.org/bots/api#sendmessage
TEXT_LIMIT = 4096

# https://core.telegram.org/bots/api#html-style
ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "span", "tg-spoiler", "blockquote", "br",
}
VOID_TAGS = {"br"}

# https://core.telegram.org/bots/api#sendrichmessage
RICH_TEXT_LIMIT = 32768
RICH_MEDIA_LIMIT = 50
RICH_MEDIA_TAGS = {"img", "video", "audio"}
RICH_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "mark", "sub", "sup",
    "tg-spoiler", "a", "br", "tg-emoji", "tg-time", "tg-reference", "tg-math",
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "footer", "hr",
    "blockquote", "aside", "cite", "tg-math-block", "details", "summary", "ul", "ol", "li",
    "figure", "figcaption", "table", "caption", "tr", "th", "td",
    "tg-collage", "tg-slideshow", "tg-map",
} | RICH_MEDIA_TAGS
RICH_VOID_TAGS = {"br", "hr", "img", "tg-map"}
# Telegram downloads a picture by its address. A custom emoji may be drawn as
# an image too, by its id.
MEDIA_SOURCE = re.compile(r"^(https?://\S+|tg://emoji\?id=\d+)$")

# Telegram asks for `<` and `&` to be escaped even when they read as plain text.
# Python's parser shrugs at them, so they are caught before it runs — a stray
# ampersand that only Telegram objects to would fail the whole send.
STRAY_ANGLE = re.compile(r"<(?![a-zA-Z/])")
STRAY_AMPERSAND = re.compile(r"&(?!(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z]+);)")


class TelegramHtmlError(ValueError):
    pass


@dataclass(frozen=True)
class _Dialect:
    tags: set[str]
    void_tags: set[str]
    # A rich message can link within itself: `<a name>` marks the spot.
    named_anchors: bool


_MESSAGE = _Dialect(ALLOWED_TAGS, VOID_TAGS, named_anchors=False)
_RICH = _Dialect(RICH_TAGS, RICH_VOID_TAGS, named_anchors=True)


class _Reader(HTMLParser):
    """Collects the visible text and complains about anything Telegram won't
    accept, so one pass answers both questions."""

    def __init__(self, dialect: _Dialect) -> None:
        super().__init__(convert_charrefs=True)
        self.dialect = dialect
        self.text: list[str] = []
        self.open_tags: list[str] = []
        self.media_count = 0

    def handle_starttag(self, tag, attrs):
        if tag not in self.dialect.tags:
            raise TelegramHtmlError(f"Telegram не понимает тег <{tag}>")
        attributes = dict(attrs)
        if tag == "a" and not attributes.get("href"):
            if not (self.dialect.named_anchors and attributes.get("name")):
                raise TelegramHtmlError("У ссылки нет href")
        if tag in RICH_MEDIA_TAGS:
            if not MEDIA_SOURCE.match(attributes.get("src") or ""):
                raise TelegramHtmlError(f"У <{tag}> в src должна быть ссылка https://…")
            self.media_count += 1
        if tag not in self.dialect.void_tags:
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if tag in self.dialect.void_tags:
            return
        if not self.open_tags or self.open_tags[-1] != tag:
            raise TelegramHtmlError(f"Тег </{tag}> закрыт не там, где открыт")
        self.open_tags.pop()

    def handle_data(self, data):
        self.text.append(data)


def _read(body: str, dialect: _Dialect) -> _Reader:
    if STRAY_ANGLE.search(body):
        raise TelegramHtmlError("Символ < нужно писать как &lt;")
    if STRAY_AMPERSAND.search(body):
        raise TelegramHtmlError("Символ & нужно писать как &amp;")

    reader = _Reader(dialect)
    reader.feed(body)
    reader.close()
    if reader.open_tags:
        raise TelegramHtmlError(f"Тег <{reader.open_tags[-1]}> не закрыт")
    return reader


def visible_length(body: str) -> int:
    """How long Telegram considers the message: markup doesn't count, and the
    unit is UTF-16 code units, so an emoji costs two."""
    plain = "".join(_read(body, _MESSAGE).text)
    return len(plain.encode("utf-16-le")) // 2


def rich_visible_length(body: str) -> int:
    """How long Telegram considers a rich message. Its limit is counted in
    characters rather than UTF-16 units, and the pictures have a cap of their own."""
    reader = _read(body, _RICH)
    if reader.media_count > RICH_MEDIA_LIMIT:
        raise TelegramHtmlError(f"Картинок и видео больше {RICH_MEDIA_LIMIT}")
    return len("".join(reader.text))
