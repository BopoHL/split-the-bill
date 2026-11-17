"""What the app's pictures are drawn with: its colours, its fonts and the
pieces of a paper receipt — words cut to fit, dotted leaders, dashed rules — so
a shared bill and a person's report read as the app does."""
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"


@dataclass(frozen=True)
class Palette:
    """The app's colours for one theme, as the pictures use them."""

    page: str
    card: str
    ink: str
    # The «Bold» outlines and hard shadows: the ink itself in the light theme,
    # softened apart from it in the dark one, as in the app.
    outline: str
    shadow: str
    muted: str
    faint: str
    line: str
    track: str
    green: str
    on_green: str
    accent: str
    on_accent: str
    # The analytics charts' fills, in the app's order: --chart-1 to --chart-5,
    # then --chart-other.
    charts: tuple[str, ...]


PALETTES = {
    "light": Palette(
        page="#efe7d8", card="#fbf7ee", ink="#1b1813", outline="#1b1813", shadow="#1b1813",
        muted="#6c6354", faint="#9b917d", line="#cdc1a7", track="#e7ddc9", green="#2f7d4f", on_green="#ffffff",
        accent="#e1442f", on_accent="#ffffff",
        charts=("#d9442f", "#1f74a6", "#b8840f", "#8a3f8f", "#5f7d23", "#9b917d"),
    ),
    # «Warm graphite», the app's dark theme.
    "dark": Palette(
        page="#22201c", card="#2a2723", ink="#dcd2c1", outline="#574d41", shadow="#100e0c",
        muted="#a89c88", faint="#7b7061", line="#3f3830", track="#312d28", green="#7eaa82", on_green="#1a1815",
        accent="#c95f44", on_accent="#ede4d4",
        charts=("#df553b", "#3a8ccc", "#c08a1c", "#a35fa6", "#789636", "#7b7061"),
    ),
    # Arctic Polar Night with the frost blue for an accent.
    "nord": Palette(
        page="#2e3440", card="#3b4252", ink="#e5e9f0", outline="#56627a", shadow="#20242d",
        muted="#a7b1c2", faint="#7b869a", line="#4c566a", track="#434c5e", green="#a3be8c", on_green="#2e3440",
        accent="#88c0d0", on_accent="#2e3440",
        charts=("#88c0d0", "#d08770", "#ebcb8b", "#b48ead", "#a3be8c", "#6b768a"),
    ),
    # Nord's Snow Storm by day: pale blue-grey paper, the deep frost blue.
    "nord_frost": Palette(
        page="#e5e9f0", card="#f5f7fa", ink="#2e3440", outline="#2e3440", shadow="#2e3440",
        muted="#4c566a", faint="#7b8698", line="#c5cdd9", track="#dce2ea", green="#557d43", on_green="#ffffff",
        accent="#5e81ac", on_accent="#ffffff",
        charts=("#5e81ac", "#c46d3f", "#b8901c", "#9a6f93", "#5f8a45", "#9aa3b2"),
    ),
    # Cherry blossom: pink paper and a cherry accent.
    "sakura": Palette(
        page="#f4e6e6", card="#fdf5f4", ink="#2d1b20", outline="#2d1b20", shadow="#2d1b20",
        muted="#7a5f66", faint="#a88f95", line="#e2c9cc", track="#efdcdc", green="#3f7d55", on_green="#ffffff",
        accent="#c8466c", on_accent="#ffffff",
        charts=("#c8466c", "#2f6fa3", "#b8840f", "#7c4f9e", "#5f7d23", "#a88f95"),
    ),
    # Night blue with an amber light.
    "midnight": Palette(
        page="#121826", card="#1a2234", ink="#dde3ee", outline="#3a4762", shadow="#0a0e17",
        muted="#9aa6bd", faint="#6c7891", line="#2d3850", track="#222b40", green="#6fc39a", on_green="#121826",
        accent="#f0a54a", on_accent="#121826",
        charts=("#f0a54a", "#5aa9e6", "#e27a8f", "#a98ae0", "#79c27f", "#6c7891"),
    ),
}
DEFAULT_THEME = "light"


def resolve_theme(value: str | None) -> str:
    return value if value in PALETTES else DEFAULT_THEME


@lru_cache(maxsize=None)
def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


# The fonts cover Latin and Cyrillic; a name with an emoji or another script
# would print boxes, so those characters are left out of the picture only.
_KEEP = set("ʻʼ×·—–…№%&@#$€₽£¥+/=()[]'\"‘’«»")


def printable(text: str) -> str:
    kept = []
    for char in text:
        if char.isspace():
            kept.append(" ")
            continue
        category = unicodedata.category(char)
        if char in _KEEP:
            kept.append(char)
        elif category[0] in "LN":
            if unicodedata.name(char, "").startswith(("LATIN", "CYRILLIC", "DIGIT", "GREEK")) or char.isdigit():
                kept.append(char)
        elif category[0] == "P" or category == "Sc":
            kept.append(char)
    return " ".join("".join(kept).split())


def text_width(text: str, font: ImageFont.FreeTypeFont, tracking: int = 0) -> int:
    return int(font.getlength(text)) + tracking * max(0, len(text) - 1)


def fit(text: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    if text_width(text, font) <= width:
        return text
    while text and text_width(text + "…", font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(text: str, font: ImageFont.FreeTypeFont, width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    words = text.split()
    while words and len(lines) < max_lines:
        line = words.pop(0)
        while words and text_width(f"{line} {words[0]}", font) <= width:
            line = f"{line} {words.pop(0)}"
        lines.append(line)
    if words:
        lines[-1] = fit(f"{lines[-1]} {' '.join(words)}", font, width)
    return [fit(line, font, width) for line in lines]


def draw_text(draw: ImageDraw.ImageDraw, x: float, baseline: float, text: str, font, fill: str, tracking: int = 0) -> None:
    if not tracking:
        draw.text((x, baseline), text, font=font, fill=fill, anchor="ls")
        return
    for char in text:
        draw.text((x, baseline), char, font=font, fill=fill, anchor="ls")
        x += font.getlength(char) + tracking


def leader(draw: ImageDraw.ImageDraw, palette: Palette, start: float, end: float, y: float) -> None:
    """The dotted line from a label to the figure set on the right of it."""
    x = start + 12
    while x < end - 12:
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=palette.line)
        x += 11


def dashes(draw: ImageDraw.ImageDraw, palette: Palette, left: float, right: float, y: float, fill: str | None = None) -> None:
    """A dashed rule across, in the hairline colour unless told otherwise."""
    x = left
    while x < right:
        draw.line((x, y, min(x + 10, right), y), fill=fill or palette.line, width=3)
        x += 18


@dataclass
class Row:
    """A band of a picture laid out top to bottom: how tall it is, and how to
    paint it from its top-left corner."""

    height: int
    paint: Callable[[ImageDraw.ImageDraw, int, int], None]
    # Pictures laid over the row once it is drawn, at offsets from its corner.
    pictures: tuple[tuple[Image.Image, int, int], ...] = ()


def gap(height: int) -> Row:
    return Row(height, lambda draw, x, y: None)
