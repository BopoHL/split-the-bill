"""A person's report for a month, a year or all time, drawn as one long paper
receipt: the totals, where the money went month by month, who sat at the
table, what was ordered and where, the badges earned, and the sum at the foot.

It is the analytics screen's numbers in a form to share — Telegram sends it as
a photo — so it keeps the app's look: paper, ink outline, hard shadow,
monospace figures, dotted leaders and dashed rules.
"""
import io
from collections import defaultdict
from datetime import date, timedelta

from PIL import Image, ImageDraw

from app.schemas.analytics_schemas import AnalyticsResponse
from app.services.analytics import Period, PeriodKind
from app.services.drawing import (
    PALETTES, Palette, Row, dashes, draw_text, fit, gap, leader, load_font, printable, resolve_theme, text_width,
)
from app.utils.currency import currency_symbol, format_number
from app.utils.report_copy import ReportCopy

WIDTH = 1080
MARGIN = 28
SHADOW = (10, 12)
PAD = 60
CARD_WIDTH = WIDTH - 2 * MARGIN - SHADOW[0]
INNER = CARD_WIDTH - 2 * PAD
LINE = 52
INDENT = 40
# The least room between a label and the figure on its right.
FIGURE_GAP = 48
TOP_PEOPLE = 5
TOP_DISHES = 5
TOP_PLACES = 4
# How a badge leans, in turn: a stamp pressed by hand is never straight.
STAMP_TILTS = (-4, 3, -2, 2)
# The barcode at the foot, bar and space widths in turn.
BARCODE = (3, 2, 4, 1, 3, 2, 5, 1, 2, 3, 1, 4, 2, 1, 3, 2, 5, 1, 2, 4, 1, 3, 2, 1, 4, 2, 3, 1, 5, 2, 1, 3, 2, 4, 1, 2, 3, 1, 4, 2)
BARCODE_UNIT = 4
GROUP_ORDER = ("food", "drink", "dessert", "alcohol", "fee", "other")


def _brand():
    return load_font("Onest-ExtraBold.ttf", 60)


def _body():
    return load_font("JetBrainsMono-Medium.ttf", 32)


def _bold():
    return load_font("JetBrainsMono-Bold.ttf", 32)


def _small():
    return load_font("JetBrainsMono-Medium.ttf", 27)


def _total_label():
    return load_font("JetBrainsMono-Bold.ttf", 44)


def _total_figure():
    return load_font("JetBrainsMono-Bold.ttf", 52)


class _Report:
    def __init__(self, data: AnalyticsResponse, period: Period, name: str, language: str, palette: Palette, today: date):
        self.data = data
        self.period = period
        self.name = name
        self.copy = ReportCopy(language)
        self.palette = palette
        self.today = today

    def money(self, amount: float) -> str:
        return format_number(round(amount * 100))

    def whole(self, amount: float) -> str:
        """An average: its kopecks are noise, so it is said in whole units."""
        return format_number(round(amount) * 100)

    def currency(self) -> str:
        return currency_symbol(self.data.currency, self.copy.language)


def report_title(period: Period, copy: ReportCopy) -> str:
    if period.kind == PeriodKind.MONTH:
        return copy("report_month", month=copy.month(period.month), year=period.year)
    if period.kind == PeriodKind.YEAR:
        return copy("report_year", year=period.year)
    return copy("report_all")


def _span(report: _Report) -> str:
    """The days the report covers, up to today: «01.01 — 03.10»."""
    period, today = report.period, report.today
    if period.kind == PeriodKind.ALL:
        first = report.data.period
        start = date(first.first_year, first.first_month or 1, 1) if first.first_year else today
        return f"{start:%m.%Y} — {today:%d.%m.%Y}"
    if period.kind == PeriodKind.YEAR:
        start, end = date(period.year, 1, 1), date(period.year, 12, 31)
    else:
        start = date(period.year, period.month, 1)
        end = date(period.year + (period.month == 12), period.month % 12 + 1, 1) - timedelta(days=1)
    return f"{start:%d.%m} — {min(end, today):%d.%m}"


def _centred(text: str, font, fill: str, height: int, baseline: int, tracking: int = 0) -> Row:
    def paint(draw, x, y):
        draw_text(draw, x + (INNER - text_width(text, font, tracking)) / 2, y + baseline, text, font, fill, tracking)

    return Row(height, paint)


def _brand_row(palette: Palette) -> Row:
    parts = (("SPLIT", palette.ink), ("·", palette.accent), ("BILL", palette.ink))
    width = sum(text_width(part, _brand()) for part, _ in parts) + 2 * 6

    def paint(draw, x, y):
        left = x + (INNER - width) / 2
        for part, fill in parts:
            draw_text(draw, left, y + 60, part, _brand(), fill)
            left += text_width(part, _brand()) + 6

    return Row(78, paint)


def _head(report: _Report) -> list[Row]:
    p = report.palette
    title = report_title(report.period, report.copy).upper()
    meta = f"{printable(report.name) or '—'} · {_span(report)}"
    return [
        _brand_row(p),
        _centred(fit(title, _bold(), INNER), _bold(), p.ink, 54, 40, tracking=3),
        _centred(fit(meta, _small(), INNER), _small(), p.muted, 44, 34),
    ]


def _rule(palette: Palette) -> Row:
    return Row(56, lambda draw, x, y: dashes(draw, palette, x, x + INNER, y + 28, fill=palette.outline))


def _heading(palette: Palette, text: str) -> Row:
    return Row(LINE + 8, lambda draw, x, y: draw_text(draw, x, y + 40, text.upper(), _bold(), palette.ink, tracking=3))


def _line(palette: Palette, label: str, value: str, strong: bool = False, indent: int = 0) -> Row:
    """A label, a dotted leader and a figure on the right."""
    label_font = _bold() if strong else _body()
    value_font = _bold() if strong else _body()
    label_fill = palette.ink if strong or not indent else palette.muted
    value_width = text_width(value, value_font)
    shown = fit(label, label_font, INNER - indent - value_width - FIGURE_GAP)

    def paint(draw, x, y):
        baseline = y + 38
        draw_text(draw, x + indent, baseline, shown, label_font, label_fill)
        leader(draw, palette, x + indent + text_width(shown, label_font), x + INNER - value_width, baseline - 4)
        draw_text(draw, x + INNER - value_width, baseline, value, value_font, palette.ink)

    return Row(LINE, paint)


def _note(palette: Palette, text: str, indent: int = 0) -> Row:
    shown = fit(text, _body(), INNER - indent)
    return Row(LINE, lambda draw, x, y: draw_text(draw, x + indent, y + 38, shown, _body(), palette.muted))


def _totals(report: _Report) -> list[Row]:
    overview, copy, p = report.data.overview, report.copy, report.palette
    rows = [
        _line(p, copy("bills").upper(), str(overview.bills), strong=True),
        _line(p, copy("owned"), str(overview.owned), indent=INDENT),
        _line(p, copy("joined"), str(overview.joined), indent=INDENT),
        _line(p, copy("spent").upper(), report.money(overview.spent), strong=True),
        _line(p, copy("average").upper(), report.whole(overview.average_bill), strong=True),
    ]
    if overview.biggest:
        rows.append(_line(p, copy("biggest").upper(), report.money(overview.biggest.total), strong=True))
        title = printable(overview.biggest.title or "")
        if title:
            rows.append(_note(p, title, indent=INDENT))
    return rows


def _bar_row(palette: Palette, label: str, share: float, value: str, highlight: bool) -> Row:
    label_width = 110
    value_width = 230

    def paint(draw, x, y):
        baseline = y + 36
        draw_text(draw, x, baseline, label, _body(), palette.muted)
        left = x + label_width
        room = INNER - label_width - value_width - 20
        if share > 0:
            right = left + max(10, room * share)
            draw.rounded_rectangle((left, y + 13, right, y + 37), radius=8, fill=palette.accent if highlight else palette.ink)
            draw.rectangle((left, y + 13, left + 8, y + 37), fill=palette.accent if highlight else palette.ink)
        draw_text(draw, x + INNER - text_width(value, _bold()), baseline, value, _bold(), palette.ink)

    return Row(48, paint)


def _spread(report: _Report) -> list[Row]:
    """Where the money went over the period: by month in a year, by year over
    all time, and by weekday — counting bills — within a month."""
    data, copy, p = report.data, report.copy, report.palette
    if report.period.kind == PeriodKind.MONTH:
        counts = data.overview.weekdays
        top = max(counts) or 1
        busiest = counts.index(max(counts))
        rows = [
            _bar_row(p, day, count / top, f"×{count}" if count else "—", index == busiest and count > 0)
            for index, (day, count) in enumerate(zip(copy.weekdays(), counts))
        ]
        return [_heading(p, copy("by_weekday")), *rows]

    sums: dict[str, float] = defaultdict(float)
    for point in data.overview.timeline:
        key = point.key[:4] if report.period.kind == PeriodKind.ALL else point.key
        sums[key] += point.amount
    # From the first month with a bill in it: a year begun in August is not
    # seven empty lines.
    keys = list(sums)
    while keys and not sums[keys[0]]:
        keys.pop(0)
    if not keys:
        return []
    top = max(sums.values())

    def label(key: str) -> str:
        return key if report.period.kind == PeriodKind.ALL else copy.short_month(int(key[5:7]))

    rows = [
        _bar_row(p, label(key), sums[key] / top, report.money(sums[key]) if sums[key] else "—", sums[key] == top)
        for key in keys
    ]
    heading = copy("by_year") if report.period.kind == PeriodKind.ALL else copy("by_month")
    return [_heading(p, heading), *rows]


def _people(report: _Report) -> list[Row]:
    people, copy, p = report.data.people, report.copy, report.palette
    if not people.companions:
        return []
    rows = [_heading(p, copy("people"))]
    rows += [
        _line(p, printable(companion.name or "") or "—", f"×{companion.together}")
        for companion in people.companions[:TOP_PEOPLE]
    ]
    if people.speed:
        fastest = people.speed[0]
        rows.append(_note(p, copy("fastest", name=printable(fastest.name or "") or "—", wait=copy.wait(fastest.minutes))))
    return rows


def _champion(report: _Report) -> Row | None:
    champions, copy, p = report.data.food.champions, report.copy, report.palette
    if not champions:
        return None
    champion = champions[0]
    lines = [
        (copy("champion", kind=printable(champion.name)).upper(), _bold()),
        (copy("champion_often", dish=printable(champion.often), count=champion.often_count), _body()),
        (copy("champion_priciest", dish=printable(champion.priciest), price=report.money(champion.priciest_price)), _body()),
    ]
    inset = 26

    def paint(draw, x, y):
        top = y + 12
        draw.rounded_rectangle((x, top, x + INNER, top + 2 * inset + 46 * len(lines)), radius=8, outline=p.outline, width=3)
        for index, (text, font) in enumerate(lines):
            draw_text(draw, x + inset, top + inset + 34 + 46 * index, fit(text, font, INNER - 2 * inset), font, p.ink)

    return Row(24 + 2 * inset + 46 * len(lines), paint)


def _groups(report: _Report) -> list[Row]:
    """The money's split between food, drinks and the rest: one bar in the
    chart colours, and what each colour is underneath."""
    groups, copy, p = report.data.food.groups, report.copy, report.palette
    spent = sum(group.amount for group in groups if group.amount > 0)
    if spent <= 0:
        return []
    shares = [
        (group.group if group.group in GROUP_ORDER else "other", group.amount / spent)
        for group in groups if group.amount > 0
    ]
    shares.sort(key=lambda share: GROUP_ORDER.index(share[0]))
    tones = dict(zip(GROUP_ORDER, p.charts))

    def paint_bar(draw, x, y):
        left = x
        for index, (group, share) in enumerate(shares):
            right = x + INNER if index == len(shares) - 1 else left + INNER * share
            if right - left >= 2:
                draw.rectangle((left, y + 12, right - 3, y + 38), fill=tones[group])
            left = right

    items = [(tones[group], f"{copy('group_' + group)} {round(share * 100)}%") for group, share in shares]
    legend: list[list[tuple[str, str]]] = [[]]
    used = 0
    for tone, text in items:
        width = 26 + text_width(text, _small()) + 34
        if legend[-1] and used + width > INNER:
            legend.append([])
            used = 0
        legend[-1].append((tone, text))
        used += width

    def legend_row(line: list[tuple[str, str]]) -> Row:
        def paint(draw, x, y):
            left = x
            for tone, text in line:
                draw.rounded_rectangle((left, y + 14, left + 18, y + 32), radius=4, fill=tone)
                draw_text(draw, left + 26, y + 32, text, _small(), p.muted)
                left += 26 + text_width(text, _small()) + 34

        return Row(44, paint)

    return [Row(50, paint_bar), *[legend_row(line) for line in legend]]


def _food(report: _Report) -> list[Row]:
    food, copy, p = report.data.food, report.copy, report.palette
    if not food.top and not food.groups:
        return []
    rows = [_heading(p, copy("dishes"))]
    rows += [_line(p, printable(dish.name) or "—", f"×{dish.count}") for dish in food.top[:TOP_DISHES]]
    champion = _champion(report)
    if champion:
        rows.append(champion)
    return rows + [gap(8), *_groups(report)]


def _places(report: _Report) -> list[Row]:
    places, copy, p = report.data.places, report.copy, report.palette
    if not places.top:
        return []
    rows = [_heading(p, copy("places"))]
    rows += [
        _line(p, printable(place.name) or "—", copy.counted(place.visits, "times"))
        for place in places.top[:TOP_PLACES]
    ]
    return rows


def _stamp(palette: Palette, text: str, tone: str, tilt: float) -> Image.Image:
    """A badge as a rubber stamp: a rounded frame round its name, pressed at a slant."""
    scale = 2
    font = load_font("JetBrainsMono-Bold.ttf", 30 * scale)
    tracking = 3 * scale
    width = text_width(text, font, tracking) + 2 * 22 * scale
    height = 60 * scale
    tile = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=9 * scale, outline=tone, width=4 * scale)
    draw_text(draw, 22 * scale, 41 * scale, text, font, tone, tracking)
    tilted = tile.rotate(tilt, resample=Image.BICUBIC, expand=True)
    return tilted.resize((tilted.width // scale, tilted.height // scale), Image.LANCZOS)


def _badges(report: _Report) -> list[Row]:
    badges, copy, p = report.data.badges, report.copy, report.palette
    if not badges:
        return []
    tones = (p.accent, p.ink, p.green, p.charts[3])
    stamps = [
        _stamp(p, copy(f"badge_{badge.key}").upper(), tones[index % len(tones)], STAMP_TILTS[index % len(STAMP_TILTS)])
        for index, badge in enumerate(badges)
    ]
    lines: list[list[Image.Image]] = [[]]
    used = 0
    for stamp in stamps:
        if lines[-1] and used + stamp.width > INNER:
            lines.append([])
            used = 0
        lines[-1].append(stamp)
        used += stamp.width + 20

    def stamp_row(line: list[Image.Image]) -> Row:
        height = max(stamp.height for stamp in line)
        pictures, left = [], 0
        for stamp in line:
            pictures.append((stamp, left, (height - stamp.height) // 2 + 6))
            left += stamp.width + 20
        return Row(height + 12, lambda draw, x, y: None, pictures=tuple(pictures))

    return [_heading(p, copy("badges")), gap(6), *[stamp_row(line) for line in lines]]


def _total(report: _Report) -> list[Row]:
    copy, p = report.copy, report.palette
    figure = f"{report.money(report.data.overview.spent)} {report.currency()}".strip()
    label = copy("total").upper()

    def paint(draw, x, y):
        draw.line((x, y + 14, x + INNER, y + 14), fill=p.outline, width=4)
        baseline = y + 88
        draw_text(draw, x, baseline, label, _total_label(), p.ink)
        draw_text(draw, x + INNER - text_width(figure, _total_figure()), baseline, figure, _total_figure(), p.ink)

    rows = [Row(108, paint)]
    others = report.data.other_currency_bills
    if others:
        note = copy("other_currency", count=copy.counted(others, "bills"))
        rows.append(Row(44, lambda draw, x, y: draw_text(
            draw, x + INNER - text_width(note, _small()), y + 30, note, _small(), p.muted,
        )))
    return rows


def _foot(report: _Report) -> list[Row]:
    p = report.palette
    width = sum(BARCODE) * BARCODE_UNIT

    def paint_barcode(draw, x, y):
        left = x + (INNER - width) / 2
        for index, bar in enumerate(BARCODE):
            if index % 2 == 0:
                draw.rectangle((left, y + 30, left + bar * BARCODE_UNIT - 1, y + 130), fill=p.ink)
            left += bar * BARCODE_UNIT

    return [Row(140, paint_barcode), _centred(report.copy("thanks").upper(), _small(), p.muted, 60, 42, tracking=3)]


def _layout(report: _Report) -> list[Row]:
    rows = [*_head(report), _rule(report.palette), *_totals(report)]
    for section in (_spread, _people, _food, _places, _badges):
        found = section(report)
        if found:
            rows += [_rule(report.palette), *found]
    return rows + [gap(18), *_total(report), *_foot(report)]


def render_report(
    data: AnalyticsResponse, period: Period, name: str, language: str, today: date, theme: str | None = None,
) -> bytes:
    """The report as a JPEG — the format Telegram takes a shared photo in — in
    the colours of the app's `theme`."""
    palette = PALETTES[resolve_theme(theme)]
    rows = _layout(_Report(data, period, name, language, palette, today))
    card_height = 2 * PAD + sum(row.height for row in rows)
    image = Image.new("RGB", (WIDTH, 2 * MARGIN + card_height + SHADOW[1]), palette.page)
    draw = ImageDraw.Draw(image)

    card = (MARGIN, MARGIN, MARGIN + CARD_WIDTH, MARGIN + card_height)
    draw.rounded_rectangle(
        (card[0] + SHADOW[0], card[1] + SHADOW[1], card[2] + SHADOW[0], card[3] + SHADOW[1]), radius=14, fill=palette.shadow,
    )
    draw.rounded_rectangle(card, radius=14, fill=palette.card, outline=palette.outline, width=4)

    y = MARGIN + PAD
    for row in rows:
        row.paint(draw, MARGIN + PAD, y)
        for picture, dx, dy in row.pictures:
            image.paste(picture, (MARGIN + PAD + dx, y + dy), picture)
        y += row.height

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()
