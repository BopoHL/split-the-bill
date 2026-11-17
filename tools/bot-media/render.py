"""Draws the bot's pictures from the HTML here into frontend/public/bot/.

    python render.py            # every language
    python render.py ru         # one

Reads the screenshots capture.py left in shots/<lang>/. After a redraw, bump
BOT_MEDIA_VERSION on the server: Telegram keeps a picture by its address.
"""
import io
import os
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "frontend" / "public" / "bot"
LANGUAGES = ("ru", "uz", "en")
GUIDE_STEPS = 5
# Drawn at twice the size and kept there: Telegram shows photos up to 2560px.
SCALE = 2


def _save(png: bytes, path: Path) -> None:
    """A palette of 256 colours is plenty for flat UI and quarters the file."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    image.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)


def _draw(page, template: str, query: str, size: tuple[int, int], path: Path) -> None:
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(f"{(HERE / template).as_uri()}?{query}", wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_function("[...document.images].every((img) => img.complete && img.naturalWidth > 0)")
    _save(page.locator(".canvas").screenshot(), path)
    print(path.relative_to(HERE.parents[1]))


def main(languages: tuple[str, ...]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        # CHROMIUM_PATH: a Chromium of your own when Playwright's download is not to hand.
        browser = playwright.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        page = browser.new_page(device_scale_factor=SCALE)
        for language in languages:
            _draw(page, "welcome.html", f"lang={language}", (1280, 720), OUT / f"welcome-{language}.png")
            for step in range(1, GUIDE_STEPS + 1):
                _draw(page, "guide.html", f"lang={language}&step={step}", (1200, 900), OUT / f"guide-{language}-{step}.png")
        browser.close()


if __name__ == "__main__":
    main(tuple(sys.argv[1:]) or LANGUAGES)
