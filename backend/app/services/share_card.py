"""The picture above a shared bill: the app's ticket, drawn for a chat.

Telegram shows it as the link preview of the shared message, fetching it by
URL, so it has to stand on its own: who owes what and for which dishes, what
nobody has taken, how much is already in, and the total. Dishes are named, not
priced — a person's amount is the figure that matters — and run on with commas
from right after the person's name into one more line, counting the rest. It
keeps the app's look — paper, ink outline, hard shadow, monospace figures — so
the chat and the app read as one thing, and puts each person's face next to
their name.
"""
import io
import math
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.services.bill_summary import BillSummary, SummaryLine, SummarySeat
from app.services.drawing import (
    DEFAULT_THEME, PALETTES, Palette, Row, dashes, draw_text, fit, gap, leader, load_font, printable, resolve_theme,
    text_width, wrap,
)
from app.utils.bot_copy import t
from app.utils.currency import currency_symbol, format_number


WIDTH = 1080
# Portrait 4:5 at most: a taller picture is shrunk to fit the phone screen and
# the writing on it stops being readable. What does not fit is in the message.
MAX_HEIGHT = 1350
# The ticket fills the picture: the page around it is only its shadow's room.
MARGIN = 16
SHADOW = (10, 12)
PAD = 44
CARD_WIDTH = WIDTH - 2 * MARGIN - SHADOW[0]
INNER = CARD_WIDTH - 2 * PAD
AVATAR = 72
# A paid person's mark after their name, the app's: a green square with a
# dollar sign.
PAID_MARK = 44
# Faces and marks wear the app's «Bold» dress, scaled up about twice as the
# picture is: an ink outline, rounded corners and a hard shadow down-right.
OUTLINE = 3
HARD_SHADOW = (4, 6)
AVATAR_RADIUS = 13
PAID_MARK_RADIUS = 9
# A person's name and dishes start past their avatar.
NAME_X = AVATAR + 20
# A name and the dishes under it are centred on the face beside them, from
# the name's capitals (Onest SemiBold 42 stands 30px over its baseline) to the
# last line: a lone name sits across the face's middle, and a name with a line
# of dishes under it fills the face from top to bottom.
SEAT_TOP = 7
NAME_CAP = 30
SEAT_HEIGHT = SEAT_TOP + AVATAR + SEAT_TOP
DISH_LEADING = 40
# How far a line of dishes reaches under its baseline.
DISH_DESCENT = 8
# Between one person and the next, while their dishes get lines of their own.
SEAT_GAP = 24
# How many lines a person's dishes may take, the one with their name included,
# before the rest are only counted.
DISH_LINES = 2
# Between a name and the dishes after it.
DISH_GAP = 18
# The least room left before a figure set on the right.
FIGURE_GAP = 36
# A dish cut shorter than this reads as nothing.
SHORTEST_CUT = 110
# Faces and icons are drawn this many times larger and scaled down, for smooth edges.
SUPERSAMPLE = 4
# The Pro mark after the date: how tall, how far from it, and how much of it
# stands above the date's baseline.
PRO_MARK_HEIGHT = 34
PRO_MARK_GAP = 14
PRO_MARK_RISE = 27





def _title():
    return load_font("Onest-ExtraBold.ttf", 52)


def _name():
    return load_font("Onest-SemiBold.ttf", 42)


def _dish():
    return load_font("Onest-Regular.ttf", 30)


def _label():
    return load_font("Onest-SemiBold.ttf", 24)


def _initial():
    return load_font("Onest-SemiBold.ttf", 32 * SUPERSAMPLE)


def _figure():
    return load_font("JetBrainsMono-Bold.ttf", 40)


def _small_figure():
    return load_font("JetBrainsMono-Medium.ttf", 26)


def _total_label():
    return load_font("Onest-ExtraBold.ttf", 38)


def _total_figure():
    return load_font("JetBrainsMono-Bold.ttf", 42)


def _flow(units: list[str], font: ImageFont.FreeTypeFont, width: int, first: int) -> list[str]:
    """Units laid out in lines, never broken inside one. The first line is
    `first` wide — the room left after a name — and stays empty when not even
    one unit fits there."""
    lines: list[str] = []
    line = ""
    for unit in units:
        room = first if not lines else width
        candidate = f"{line} {unit}" if line else unit
        if text_width(candidate, font) <= room:
            line = candidate
        elif line or room < width:
            lines.append(line)
            line = unit
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _whole(words: list[str], font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """An item as one unit to lay out, or its words when no line holds it."""
    item = " ".join(words)
    return [item] if text_width(item, font) <= width else words


def _listing(
    items: list[list[str]],
    more: Callable[[int], str],
    font: ImageFont.FreeTypeFont,
    width: int,
    max_lines: int,
    first: int | None = None,
) -> list[str]:
    """Items, each a list of words, one after another with commas, in at most
    `max_lines` lines, the first of them `first` wide. An item stays whole on
    its line — «Raspberry and / lemongrass» reads as two dishes — unless it is
    longer than a line itself. As many as fit are named and the rest counted at
    the end: «Plov, Tea, +3 more»."""
    first = width if first is None else first

    def fitted(lines: list[str]) -> list[str]:
        return [fit(line, font, first if index == 0 else width) for index, line in enumerate(lines)]

    for shown in range(len(items), 0, -1):
        hidden = len(items) - shown
        units: list[str] = []
        for index, words in enumerate(items[:shown]):
            comma = "," if index < shown - 1 or hidden else ""
            units += _whole([*words[:-1], words[-1] + comma], font, width)
        if hidden:
            units.append(more(hidden))
        lines = _flow(units, font, width, first)
        if len(lines) <= max_lines:
            return fitted(lines)
    if not items:
        return []
    # Not even the first item fits whole: it is cut short, the rest still
    # counted after it — or nothing is listed where a cut would show nothing.
    tail = f", {more(len(items) - 1)}" if len(items) > 1 else ""
    lines = _flow(items[0], font, width, first)
    kept = lines[:max_lines]
    room = (first if len(kept) == 1 else width) - text_width(tail, font)
    if room < SHORTEST_CUT:
        return []
    kept[-1] = fit(" ".join(lines[len(kept) - 1:]).strip(), font, room) + tail
    return fitted(kept)


class _Copy:
    def __init__(self, summary: BillSummary, language: str, palette: Palette):
        self.summary = summary
        self.language = language
        self.palette = palette

    def __call__(self, key: str, **values) -> str:
        return t(self.language, key).format(**values)

    def figure(self, tiins: int) -> str:
        return format_number(tiins)

    def currency(self) -> str:
        return currency_symbol(self.summary.currency, self.language)

    def seat_name(self, seat: SummarySeat) -> str:
        return printable(seat.name or "") or self("share_guest", n=seat.seat_index)

    def initial(self, seat: SummarySeat) -> str:
        name = printable(seat.name or "").lstrip("@")
        return name[:1].upper() if name else str(seat.seat_index)


def _title_rows(copy: _Copy, meta: str) -> list[Row]:
    """The bill's name with its date to the right, or the date under a name
    too long to share its line. A bill kept by someone with Pro wears the mark
    right after the date."""
    p = copy.palette
    title = printable(copy.summary.title or "") or t(copy.language, "bill_untitled")
    mark = _pro_mark(p) if copy.summary.pro else None
    mark_room = mark.width + PRO_MARK_GAP if mark else 0
    meta_width = text_width(meta, _small_figure())
    if text_width(title, _title()) + FIGURE_GAP + meta_width + mark_room <= INNER:
        def paint_both(draw, x, y):
            draw_text(draw, x, y + 50, title, _title(), p.ink)
            draw_text(draw, x + INNER - mark_room - meta_width, y + 50, meta, _small_figure(), p.muted)

        pictures = ((mark, INNER - mark.width, 50 - PRO_MARK_RISE),) if mark else ()
        return [Row(72, paint_both, pictures=pictures)]

    lines = wrap(title, _title(), INNER, 2)

    def paint_title(draw, x, y):
        for index, line in enumerate(lines):
            draw_text(draw, x, y + 50 + index * 60, line, _title(), p.ink)

    def paint_meta(draw, x, y):
        draw_text(draw, x, y + 28, meta, _small_figure(), p.muted)

    pictures = ((mark, meta_width + PRO_MARK_GAP, 28 - PRO_MARK_RISE),) if mark else ()
    return [Row(12 + 60 * len(lines), paint_title), Row(40, paint_meta, pictures=pictures)]


@lru_cache(maxsize=None)
def _pro_mark(palette: Palette) -> Image.Image:
    """«PRO» on a small accent tile in the «Bold» dress, as by a name in the app."""
    scale = SUPERSAMPLE
    font = load_font("Onest-ExtraBold.ttf", 20 * scale)
    label = "PRO"
    width = text_width(label, font, 2 * scale) + 2 * 12 * scale
    height = PRO_MARK_HEIGHT * scale
    tile = Image.new("RGBA", (width + 3 * scale, height + 4 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle((3 * scale, 4 * scale, width + 3 * scale - 1, height + 4 * scale - 1), radius=8 * scale, fill=palette.shadow)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=8 * scale, fill=palette.accent, outline=palette.outline, width=OUTLINE * scale)
    draw_text(draw, 12 * scale, height / 2 + 7 * scale, label, font, palette.on_accent, 2 * scale)
    return _scaled_down(tile)


def _rule(palette: Palette) -> Row:
    return Row(38, lambda draw, x, y: dashes(draw, palette, x, x + INNER, y + 19))


def _arc(cx: float, cy: float, r: float, start: float, end: float, steps: int = 12) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(math.radians(angle)), cy + r * math.sin(math.radians(angle)))
        for angle in (start + (end - start) * step / steps for step in range(steps + 1))
    ]


# The app's lucide icons as strokes on their 24-unit grid.
USER_ICON = (
    _arc(12, 7, 4, 0, 360, 24),
    [(19, 21), (19, 19), *_arc(15, 19, 4, 0, -90), (9, 15), *_arc(9, 19, 4, -90, -180), (5, 21)],
)
DOLLAR_ICON = (
    [(12, 2), (12, 22)],
    [(17, 5), *_arc(9.5, 8.5, 3.5, -90, -270), *_arc(14.5, 15.5, 3.5, -90, 90), (6, 19)],
)


def _icon(draw: ImageDraw.ImageDraw, strokes, left: float, top: float, size: float, stroke: float, fill: str) -> None:
    """Draw an icon `size` wide from its top-left corner, with the round caps
    and joins of the app's icons; all lengths already supersampled."""
    unit = size / 24
    for points in strokes:
        placed = [(left + x * unit, top + y * unit) for x, y in points]
        draw.line(placed, fill=fill, width=round(stroke * unit), joint="curve")
        for x, y in (placed[0], placed[-1]):
            radius = stroke * unit / 2
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _dashed_outline(draw: ImageDraw.ImageDraw, box, radius: float, width: float, dash: float, gap: float, fill: str) -> None:
    """A rounded box's outline in dashes that run round its corners too."""
    inset = width / 2
    left, top, right, bottom = box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset
    radius -= inset
    path = [
        *_arc(right - radius, top + radius, radius, -90, 0),
        *_arc(right - radius, bottom - radius, radius, 0, 90),
        *_arc(left + radius, bottom - radius, radius, 90, 180),
        *_arc(left + radius, top + radius, radius, 180, 270),
    ]
    path.append(path[0])
    drawing, left_in_phase, stroke = True, dash, [path[0]]
    for start, end in zip(path, path[1:]):
        length = math.dist(start, end)
        done = 0.0
        while length - done > 1e-6:
            step = min(left_in_phase, length - done)
            done += step
            left_in_phase -= step
            point = (start[0] + (end[0] - start[0]) * done / length, start[1] + (end[1] - start[1]) * done / length)
            if drawing:
                stroke.append(point)
            if left_in_phase <= 1e-6:
                if drawing:
                    draw.line(stroke, fill=fill, width=round(width), joint="curve")
                drawing = not drawing
                left_in_phase = dash if drawing else gap
                stroke = [point]
    if drawing and len(stroke) > 1:
        draw.line(stroke, fill=fill, width=round(width), joint="curve")


def _bold_tile(
    palette: Palette, size: int, radius: int, fill: str, shadow: bool = True
) -> tuple[Image.Image, ImageDraw.ImageDraw, tuple[int, int, int, int]]:
    """A supersampled canvas holding a rounded square `size` wide on its hard
    shadow, and the square's box to draw into."""
    scale = SUPERSAMPLE
    dx, dy = HARD_SHADOW if shadow else (0, 0)
    tile = Image.new("RGBA", ((size + dx) * scale, (size + dy) * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    side = size * scale
    face = (0, 0, side - 1, side - 1)
    if shadow:
        offset = (dx * scale, dy * scale)
        draw.rounded_rectangle((*offset, side - 1 + offset[0], side - 1 + offset[1]), radius=radius * scale, fill=palette.shadow)
    draw.rounded_rectangle(face, radius=radius * scale, fill=fill)
    return tile, draw, face


def _scaled_down(tile: Image.Image) -> Image.Image:
    return tile.resize((tile.width // SUPERSAMPLE, tile.height // SUPERSAMPLE), Image.LANCZOS)


@lru_cache(maxsize=None)
def _paid_mark(palette: Palette) -> Image.Image:
    tile, draw, face = _bold_tile(palette, PAID_MARK, PAID_MARK_RADIUS, palette.green)
    draw.rounded_rectangle(face, radius=PAID_MARK_RADIUS * SUPERSAMPLE, outline=palette.outline, width=OUTLINE * SUPERSAMPLE)
    icon = PAID_MARK * 0.6 * SUPERSAMPLE
    corner = (PAID_MARK * SUPERSAMPLE - icon) / 2
    _icon(draw, DOLLAR_ICON, corner, corner, icon, 2.5, palette.on_green)
    return _scaled_down(tile)


@lru_cache(maxsize=None)
def _free_seat(palette: Palette) -> Image.Image:
    """A seat nobody sits on yet, as the app draws it: a dashed outline round a
    person's silhouette, with no shadow — there is nobody there to cast one."""
    tile, draw, face = _bold_tile(palette, AVATAR, AVATAR_RADIUS, palette.track, shadow=False)
    scale = SUPERSAMPLE
    _dashed_outline(draw, face, AVATAR_RADIUS * scale, OUTLINE * scale, 9 * scale, 6 * scale, palette.faint)
    icon = AVATAR / 2 * scale
    corner = (AVATAR * scale - icon) / 2
    _icon(draw, USER_ICON, corner, corner, icon, 1.75, palette.muted)
    return _scaled_down(tile)


def _avatar(palette: Palette, seat: SummarySeat, photo: Image.Image | None, initial: str) -> Image.Image:
    """A person's face as the app's list of people shows it: a rounded square
    in an ink outline on a hard shadow — their photo, or their initial."""
    if seat.is_free:
        return _free_seat(palette)
    tile, draw, face = _bold_tile(palette, AVATAR, AVATAR_RADIUS, palette.card)
    side = AVATAR * SUPERSAMPLE
    if photo is None:
        draw.text((side / 2, side / 2), initial, font=_initial(), fill=palette.ink, anchor="mm")
    else:
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).rounded_rectangle(face, radius=AVATAR_RADIUS * SUPERSAMPLE, fill=255)
        tile.paste(ImageOps.fit(photo.convert("RGB"), (side, side), Image.LANCZOS), (0, 0), mask)
    draw.rounded_rectangle(face, radius=AVATAR_RADIUS * SUPERSAMPLE, outline=palette.outline, width=OUTLINE * SUPERSAMPLE)
    return _scaled_down(tile)


def _seat_row(copy: _Copy, seat: SummarySeat, photo: Image.Image | None, max_lines: int) -> Row:
    """A person: face, name, their dishes running on from right after the name
    into the line below, and what they owe on the right."""
    p = copy.palette
    amount = copy.figure(seat.amount)
    amount_width = text_width(amount, _figure())
    mark_space = PAID_MARK + HARD_SHADOW[0] + 12 if seat.is_paid else 0
    name = fit(copy.seat_name(seat), _name(), INNER - NAME_X - amount_width - mark_space - 40)
    name_end = NAME_X + text_width(name, _name())
    dishes_x = name_end + mark_space + DISH_GAP
    dishes = _dishes(copy, seat.lines, max_lines, NAME_X, INNER - dishes_x - amount_width - FIGURE_GAP)
    under = DISH_LEADING * max(0, len(dishes) - 1)
    name_baseline = SEAT_TOP + max(0, AVATAR - NAME_CAP - under) // 2 + NAME_CAP

    def paint(draw, x, y):
        baseline = y + name_baseline
        draw_text(draw, x + NAME_X, baseline, name, _name(), p.ink)
        end = x + name_end + mark_space
        if dishes and dishes[0]:
            draw_text(draw, x + dishes_x, baseline, dishes[0], _dish(), p.muted)
            end = x + dishes_x + text_width(dishes[0], _dish())
        right = x + INNER - amount_width
        leader(draw, p, end, right, baseline - 11)
        draw_text(draw, right, baseline, amount, _figure(), p.ink)
        for index, line in enumerate(dishes[1:], start=1):
            draw_text(draw, x + NAME_X, baseline + index * DISH_LEADING, line, _dish(), p.muted)

    pictures = [(_avatar(p, seat, photo, copy.initial(seat)), 0, SEAT_TOP)]
    if seat.is_paid:
        # Centred on the name's capitals.
        pictures.append((_paid_mark(p), name_end + 12, name_baseline - (NAME_CAP + PAID_MARK) // 2))
    height = max(SEAT_HEIGHT, name_baseline + under + DISH_DESCENT + SEAT_TOP)
    return Row(height, paint, pictures=tuple(pictures))


def _line_words(line: SummaryLine) -> list[str]:
    """A dish's name as words to lay out; how much of it stays with the last
    word, so a line never starts with one."""
    words = (printable(line.name) or "—").split()
    if line.count:
        words[-1] = f"{words[-1]} {line.count}"
    return words


def _dishes(copy: _Copy, lines: tuple[SummaryLine, ...], max_lines: int, indent: int, first: int) -> list[str]:
    """Dishes as the lines to draw: the first one after a heading, `first`
    wide, the rest from `indent`. With no room for any line, none are listed
    at all: a lone «+3 more» says nothing a name doesn't."""
    if max_lines == 0 or not lines:
        return []
    return _listing(
        [_line_words(line) for line in lines],
        lambda hidden: copy("share_more_inline", n=hidden),
        _dish(),
        INNER - indent,
        max_lines,
        first=max(0, first),
    )


def _note(palette: Palette, text: str) -> Row:
    lines = wrap(text, _dish(), INNER, 3)

    def paint(draw, x, y):
        for index, line in enumerate(lines):
            draw_text(draw, x, y + 32 + index * 38, line, _dish(), palette.faint)

    return Row(4 + 38 * len(lines), paint)


def _section(palette: Palette, label: str, amount: str | None) -> Row:
    def paint(draw, x, y):
        baseline = y + 38
        draw_text(draw, x, baseline, label.upper(), _label(), palette.muted, tracking=2)
        if amount:
            draw_text(draw, x + INNER - text_width(amount, _small_figure()), baseline, amount, _small_figure(), palette.muted)

    return Row(52, paint)


def _progress(copy: _Copy) -> list[Row]:
    summary, p = copy.summary, copy.palette
    share = 0 if summary.to_collect <= 0 else min(1, max(0, summary.collected / summary.to_collect))
    caption = copy("share_collected_of", collected=copy.figure(summary.collected), total=copy.figure(summary.to_collect))

    def paint_bar(draw, x, y):
        box = (x, y + 6, x + INNER, y + 30)
        draw.rounded_rectangle(box, radius=12, fill=p.track, outline=p.outline, width=3)
        if share > 0:
            filled = x + 3 + (INNER - 6) * share
            draw.rounded_rectangle((x + 3, y + 9, max(x + 24, filled), y + 27), radius=9, fill=p.green)

    return [_section(p, copy("share_collected"), caption), Row(40, paint_bar)]


def _total(copy: _Copy) -> Row:
    summary, p = copy.summary, copy.palette
    figure = copy.figure(summary.total)
    currency = copy.currency()
    label = copy("share_total").upper()

    def paint(draw, x, y):
        dashes(draw, p, x, x + INNER, y + 12)
        baseline = y + 72
        draw_text(draw, x, baseline, label, _total_label(), p.ink)
        currency_width = text_width(currency, _name()) + 12 if currency else 0
        right = x + INNER - currency_width
        draw_text(draw, right - text_width(figure, _total_figure()), baseline, figure, _total_figure(), p.ink)
        if currency:
            draw_text(draw, right + 12, baseline, currency, _name(), p.ink)

    return Row(88, paint)


def _unassigned(copy: _Copy, max_lines: int) -> Row:
    """«Not taken yet:» and the dishes right after it, their sum on the right."""
    summary, p = copy.summary, copy.palette
    amount = copy.figure(summary.unassigned_total)
    amount_width = text_width(amount, _small_figure())
    listed = max_lines > 0 and bool(summary.unassigned)
    label = copy("share_unassigned").upper() + (":" if listed else "")
    dishes_x = text_width(label, _label(), 2) + DISH_GAP // 2
    dishes = _dishes(copy, summary.unassigned, max_lines, 0, INNER - dishes_x - amount_width - FIGURE_GAP)

    def paint(draw, x, y):
        baseline = y + 38
        draw_text(draw, x, baseline, label, _label(), p.muted, tracking=2)
        if dishes and dishes[0]:
            draw_text(draw, x + dishes_x, baseline, dishes[0], _dish(), p.muted)
        draw_text(draw, x + INNER - amount_width, baseline, amount, _small_figure(), p.muted)
        for index, line in enumerate(dishes[1:], start=1):
            draw_text(draw, x, baseline + index * DISH_LEADING, line, _dish(), p.muted)

    return Row(52 + DISH_LEADING * max(0, len(dishes) - 1), paint)


def _body(
    copy: _Copy, max_lines: int, seat_limit: int | None, photos: Mapping[int, Image.Image]
) -> list[Row]:
    summary = copy.summary
    seats = summary.seats if seat_limit is None else summary.seats[:seat_limit]
    rows: list[Row] = []
    for index, seat in enumerate(seats):
        if index and max_lines > 1:
            rows.append(gap(SEAT_GAP))
        rows.append(_seat_row(copy, seat, photos.get(seat.telegram_id) if seat.telegram_id else None, max_lines))
    if len(seats) < len(summary.seats):
        rows.append(_note(copy.palette, copy("share_more_people", n=len(summary.seats) - len(seats))))
    if not summary.seats:
        rows.append(_note(copy.palette, copy("share_nobody_yet")))
    if summary.unassigned_total > 0:
        rows += [_rule(copy.palette), _unassigned(copy, max_lines)]
    return rows


def _meta(summary: BillSummary, language: str, now: datetime, zone: ZoneInfo) -> str:
    if summary.is_closed:
        return t(language, "share_closed")
    moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    parts = []
    if summary.created_at:
        created = summary.created_at if summary.created_at.tzinfo else summary.created_at.replace(tzinfo=timezone.utc)
        parts.append(created.astimezone(zone).strftime("%d.%m.%Y"))
    parts.append(moment.astimezone(zone).strftime("%H:%M"))
    return " · ".join(parts)


def _layout(copy: _Copy, now: datetime, zone: ZoneInfo, photos: Mapping[int, Image.Image]) -> list[Row]:
    summary = copy.summary
    head = _title_rows(copy, _meta(summary, copy.language, now, zone)) + [_rule(copy.palette)]
    tail = (_progress(copy) if summary.to_collect > 0 else []) + [_total(copy)]
    tail = [_rule(copy.palette), *tail] if summary.to_collect > 0 else tail
    budget = MAX_HEIGHT - 2 * MARGIN - SHADOW[1] - 2 * PAD - sum(row.height for row in head + tail)

    # Fewer lines of dishes per person first, then fewer people: who owes what
    # is what the picture is for, and the full list is in the message under it.
    # The dishes on a name's own line cost no height, so they always stay.
    attempts = [(lines, None) for lines in range(DISH_LINES, 0, -1)]
    attempts += [(1, limit) for limit in range(len(summary.seats) - 1, 0, -1)]
    body: list[Row] = []
    for max_lines, limit in attempts:
        body = _body(copy, max_lines, limit, photos)
        if sum(row.height for row in body) <= budget:
            break
    return head + body + [gap(6)] + tail


def render_card(
    summary: BillSummary,
    language: str,
    now: datetime,
    zone: ZoneInfo,
    photos: Mapping[int, Image.Image] | None = None,
    theme: str = DEFAULT_THEME,
) -> bytes:
    """The card as a PNG, in the colours of the app's `theme`. `photos` are
    profile photos by Telegram id; anyone without one gets their initial."""
    palette = PALETTES[resolve_theme(theme)]
    rows = _layout(_Copy(summary, language, palette), now, zone, photos or {})
    card_height = 2 * PAD + sum(row.height for row in rows)
    height = min(MAX_HEIGHT, 2 * MARGIN + card_height + SHADOW[1])
    image = Image.new("RGB", (WIDTH, height), palette.page)
    draw = ImageDraw.Draw(image)

    left, top = MARGIN, MARGIN
    card = (left, top, left + CARD_WIDTH, top + card_height)
    shadow = (card[0] + SHADOW[0], card[1] + SHADOW[1], card[2] + SHADOW[0], card[3] + SHADOW[1])
    draw.rounded_rectangle(shadow, radius=22, fill=palette.shadow)
    draw.rounded_rectangle(card, radius=22, fill=palette.card, outline=palette.outline, width=4)

    y = top + PAD
    for row in rows:
        row.paint(draw, left + PAD, y)
        for picture, dx, dy in row.pictures:
            image.paste(picture, (left + PAD + dx, y + dy), picture)
        y += row.height

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
