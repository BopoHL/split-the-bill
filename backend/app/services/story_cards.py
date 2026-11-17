"""A person's year as Telegram stories: how many bills they split, their dish
of the year, and the person they shared the most tables with.

Each is a full-screen 9:16 picture in the app's colours — ink, terracotta and
paper, one each, so the three read as a set — drawn twice as large and scaled
down, so their big rounded shapes come out smooth.
"""
import io
from enum import Enum

from PIL import Image, ImageDraw

from app.schemas.analytics_schemas import AnalyticsResponse, Champion, Companion
from app.services.drawing import draw_text, load_font, printable, text_width, wrap
from app.utils.currency import currency_symbol, format_number
from app.utils.report_copy import ReportCopy

WIDTH, HEIGHT = 1080, 1920
SCALE = 2
SIDE = 66
INNER = WIDTH - 2 * SIDE

INK = "#1b1813"
PAPER = "#efe7d8"
CARD = "#fbf7ee"
ACCENT = "#e1442f"
ACCENT_DEEP = "#bd3320"
CHART_ACCENT = "#d9442f"
LINE = "#cdc1a7"
WHITE = "#ffffff"

ONEST_BOLD = "Onest-ExtraBold.ttf"
ONEST_SEMI = "Onest-SemiBold.ttf"
ONEST = "Onest-Regular.ttf"
MONO_BOLD = "JetBrainsMono-Bold.ttf"
MONO = "JetBrainsMono-Medium.ttf"
# Telegram lays the poster's name over a story's top and the reply bar over
# its foot; the brand and the footer keep clear of both.
BRAND_BASELINE = 260
FOOTER_BASELINE = HEIGHT - 260
# Where each story's lead line sits; what it says follows under it.
LEAD = 560
# The dish of the year is named as large as fits, down to this.
DISH_SIZES = (156, 132, 112, 96)
MORE_PEOPLE = 2


class Story(str, Enum):
    BILLS = "bills"
    DISH = "dish"
    PERSON = "person"


def stories_for(data: AnalyticsResponse) -> list[Story]:
    """The stories a year has enough in it for, in the order they are told."""
    found = []
    if data.overview.bills:
        found.append(Story.BILLS)
    if data.food.top:
        found.append(Story.DISH)
    if data.people.companions:
        found.append(Story.PERSON)
    return found


class _Canvas:
    """A story drawn at twice its size; everything is placed in its own pixels."""

    def __init__(self, background: str):
        self.image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), background)
        self.draw = ImageDraw.Draw(self.image)

    @staticmethod
    def font(name: str, size: int):
        return load_font(name, size * SCALE)

    def width(self, text: str, name: str, size: int, tracking: int = 0) -> float:
        return text_width(text, self.font(name, size), tracking * SCALE) / SCALE

    def text(self, x: float, baseline: float, text: str, name: str, size: int, fill: str, tracking: int = 0) -> None:
        draw_text(self.draw, x * SCALE, baseline * SCALE, text, self.font(name, size), fill, tracking * SCALE)

    def box(self, box, radius: float, fill: str | None = None, outline: str | None = None, width: float = 0) -> None:
        self.draw.rounded_rectangle(
            [value * SCALE for value in box], radius=radius * SCALE, fill=fill, outline=outline, width=round(width * SCALE),
        )

    def dashes(self, left: float, right: float, y: float, fill: str) -> None:
        x = left
        while x < right:
            self.draw.line((x * SCALE, y * SCALE, min(x + 12, right) * SCALE, y * SCALE), fill=fill, width=3 * SCALE)
            x += 20

    def dots(self, left: float, right: float, y: float, fill: str) -> None:
        x = left + 10
        while x < right - 10:
            self.draw.ellipse(((x - 2.5) * SCALE, (y - 2.5) * SCALE, (x + 2.5) * SCALE, (y + 2.5) * SCALE), fill=fill)
            x += 13

    def stamp(self, x: float, y: float, text: str, colour: str, tilt: float) -> None:
        """A rubber stamp pressed at a slant, its top-left corner at (x, y)."""
        font = self.font(MONO_BOLD, 54)
        tracking = 6 * SCALE
        width = text_width(text, font, tracking) + 2 * 40 * SCALE
        height = 100 * SCALE
        tile = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tile)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=18 * SCALE, outline=colour, width=9 * SCALE)
        draw_text(draw, 40 * SCALE, 70 * SCALE, text, font, colour, tracking)
        tilted = tile.rotate(tilt, resample=Image.BICUBIC, expand=True)
        self.image.paste(tilted, (round(x * SCALE), round(y * SCALE)), tilted)

    def jpeg(self) -> bytes:
        picture = self.image.resize((WIDTH, HEIGHT), Image.LANCZOS)
        output = io.BytesIO()
        picture.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue()


def _brand(canvas: _Canvas, year: int, ink: str, dot: str) -> None:
    """«SPLIT·BILL · 2026» at the top, its dot in the accent."""
    x = SIDE
    for part, fill in (("SPLIT", ink), ("·", dot), (f"BILL · {year}", ink)):
        canvas.text(x, BRAND_BASELINE, part, ONEST_BOLD, 39, fill, tracking=6)
        x += canvas.width(part, ONEST_BOLD, 39, tracking=6) + 6


def _footer(canvas: _Canvas, copy: ReportCopy, fill: str) -> None:
    canvas.text(SIDE, FOOTER_BASELINE, copy("story_footer"), ONEST_SEMI, 39, fill)


def _bills(data: AnalyticsResponse, copy: ReportCopy, year: int) -> bytes:
    canvas = _Canvas(INK)
    _brand(canvas, year, PAPER, ACCENT)
    overview = data.overview
    canvas.text(SIDE, LEAD, copy("story_bills_lead"), ONEST_SEMI, 66, PAPER)
    canvas.text(SIDE - 12, LEAD + 290, str(overview.bills), MONO_BOLD, 288, ACCENT)
    canvas.text(SIDE, LEAD + 410, copy.noun(overview.bills, "bills"), ONEST_BOLD, 84, PAPER)

    canvas.dashes(SIDE, WIDTH - SIDE, LEAD + 510, "#5d564b")
    half = INNER / 2
    columns = (
        (copy.compact(overview.spent), copy("story_spent", currency=currency_symbol(data.currency, copy.language))),
        (str(data.people.distinct), copy("story_people", people=copy.noun(data.people.distinct, "people"))),
    )
    for index, (figure, caption) in enumerate(columns):
        x = SIDE + index * (half + 20)
        canvas.text(x, LEAD + 620, figure, MONO_BOLD, 66, PAPER)
        for line_index, line in enumerate(wrap(caption, canvas.font(ONEST, 39), int((half - 20) * SCALE), 2)):
            canvas.text(x, LEAD + 680 + line_index * 50, line, ONEST, 39, LINE)

    _footer(canvas, copy, "#9b917d")
    return canvas.jpeg()


def _dish_lines(canvas: _Canvas, name: str) -> tuple[list[str], int]:
    """The dish's name in the largest size it fits two lines at."""
    for size in DISH_SIZES:
        lines = wrap(name, canvas.font(ONEST_BOLD, size), INNER * SCALE, 2)
        if all(not line.endswith("…") for line in lines):
            return lines, size
    return wrap(name, canvas.font(ONEST_BOLD, DISH_SIZES[-1]), INNER * SCALE, 2), DISH_SIZES[-1]


def _champion_of(data: AnalyticsResponse, kind: str | None) -> Champion | None:
    return next((champion for champion in data.food.champions if champion.kind == kind), None)


def _dish(data: AnalyticsResponse, copy: ReportCopy, year: int) -> bytes:
    canvas = _Canvas(ACCENT_DEEP)
    _brand(canvas, year, WHITE, WHITE)
    dish = data.food.top[0]
    canvas.text(SIDE, LEAD, copy("story_dish_lead"), ONEST_SEMI, 66, WHITE)

    lines, size = _dish_lines(canvas, printable(dish.name) or "—")
    y = LEAD + 60
    for line in lines:
        y += size * 1.05
        canvas.text(SIDE, y, line, ONEST_BOLD, size, WHITE)

    y += 230
    count = str(dish.count)
    canvas.text(SIDE, y, count, MONO_BOLD, 192, WHITE)
    canvas.text(SIDE + canvas.width(count, MONO_BOLD, 192) + 30, y, copy.noun(dish.count, "times"), ONEST_SEMI, 54, WHITE)

    champion = _champion_of(data, dish.kind)
    if champion:
        price = f"{format_number(round(champion.priciest_price * 100))} {currency_symbol(data.currency, copy.language)}"
        sentence = copy("story_dish_priciest", dish=printable(champion.priciest), price=price)
        for index, line in enumerate(wrap(sentence, canvas.font(ONEST, 45), INNER * SCALE, 2)):
            canvas.text(SIDE, y + 100 + index * 62, line, ONEST, 45, WHITE)
        y += 100 + 62 * 2

    if data.badges:
        canvas.stamp(SIDE, y + 30, copy(f"badge_{data.badges[0].key}").upper(), WHITE, 5)

    _footer(canvas, copy, "#f3c9bf")
    return canvas.jpeg()


def _initial(companion: Companion) -> str:
    name = printable(companion.name or "").lstrip("@")
    return name[:1].upper() or "?"


def _person(data: AnalyticsResponse, copy: ReportCopy, year: int) -> bytes:
    canvas = _Canvas(PAPER)
    _brand(canvas, year, INK, CHART_ACCENT)
    first, *others = data.people.companions
    canvas.text(SIDE, LEAD, copy("story_person_lead"), ONEST_SEMI, 66, INK)

    top, inner = LEAD + 60, 54
    rows = [
        (copy("story_invited"), copy.counted(first.invited, "times")),
        (copy("story_invited_me"), copy.counted(first.invited_me, "times")),
    ]
    if first.paid_me > 0:
        rows.append((copy("story_paid_me"), f"{format_number(round(first.paid_me * 100))} {currency_symbol(data.currency, copy.language)}"))
    bottom = top + inner + 192 + 48 + 40 + len(rows) * 66 + inner
    left, right = SIDE, WIDTH - SIDE
    canvas.box((left + 15, top + 18, right + 15, bottom + 18), 30, fill=INK)
    canvas.box((left, top, right, bottom), 30, fill=CARD, outline=INK, width=4.5)

    tile = (left + inner, top + inner, left + inner + 192, top + inner + 192)
    canvas.box(tile, 42, fill=CHART_ACCENT, outline=INK, width=6)
    initial = _initial(first)
    canvas.text(
        tile[0] + (192 - canvas.width(initial, ONEST_BOLD, 90)) / 2, tile[1] + 128, initial, ONEST_BOLD, 90, WHITE,
    )
    text_x = tile[2] + 42
    name = printable(first.name or "") or "—"
    name_width = int((right - inner - text_x) * SCALE)
    canvas.text(text_x, tile[1] + 100, wrap(name, canvas.font(ONEST_BOLD, 90), name_width, 1)[0], ONEST_BOLD, 90, INK)
    canvas.text(text_x, tile[1] + 160, copy("story_together", bills=copy.counted(first.together, "bills")), MONO, 42, INK)

    y = tile[3] + 48
    canvas.dashes(left + inner, right - inner, y, LINE)
    for label, value in rows:
        y += 66
        canvas.text(left + inner, y, label, MONO, 39, INK)
        value_x = right - inner - canvas.width(value, MONO_BOLD, 39)
        canvas.dots(left + inner + canvas.width(label, MONO, 39), value_x, y - 6, LINE)
        canvas.text(value_x, y, value, MONO_BOLD, 39, INK)

    if others:
        listed = ", ".join(f"{printable(other.name or '') or '—'} — {other.together}" for other in others[:MORE_PEOPLE])
        sentence = copy("story_more_people", people=listed)
        for index, line in enumerate(wrap(sentence, canvas.font(ONEST, 45), INNER * SCALE, 3)):
            canvas.text(SIDE, bottom + 130 + index * 62, line, ONEST, 45, INK)

    _footer(canvas, copy, "#6c6354")
    return canvas.jpeg()


DRAWN = {Story.BILLS: _bills, Story.DISH: _dish, Story.PERSON: _person}


def render_story(story: Story, data: AnalyticsResponse, year: int, language: str) -> bytes:
    """One of the year's stories as a JPEG, 1080×1920. The story has to be
    one the year has enough for (see stories_for)."""
    return DRAWN[story](data, ReportCopy(language), year)
