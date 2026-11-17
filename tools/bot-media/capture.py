"""Screenshots of the Mini App for the bot's pictures, in every language.

    python capture.py            # every language
    python capture.py uz         # one

Runs a backend of its own on a throwaway SQLite database and a Next dev server
against it, seeds a dinner with friends and photographs it the way the people
at the table see it, into shots/<lang>/. Your own database and bot are never
touched. Needs the backend's requirements, the frontend's node_modules and
`pip install playwright` (CHROMIUM_PATH points it at a Chromium of your own).
Stop your own `next dev` first: one frontend folder runs one dev server.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import httpx
from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LANGUAGES = ("ru", "uz", "en")
API_PORT, APP_PORT = 8765, 3765
API = f"http://localhost:{API_PORT}/api"
APP = f"http://localhost:{APP_PORT}"

# The dev mock's people (frontend/src/lib/telegram/devMock.ts), renamed: the
# pictures are public.
OWNER, FRIEND, GUEST = 100000000, 100000001, 100000002
MOCK_USER = {OWNER: "leonid", FRIEND: "alice", GUEST: "bob"}

DINNER = {
    "ru": {
        "people": {OWNER: "Тимур", FRIEND: "Алишер", GUEST: "Мадина"},
        "title": "Ужин в «Плов Центре»",
        "coffee": ("Кофе после работы", [("Капучино", 28000), ("Чизкейк", 35000)]),
        "items": ["Плов", "Шашлык из баранины", "Салат «Ачичук»", "Лепёшка", "Зелёный чай, чайник", "Самса"],
        "ui": {"next": "Далее", "receipt": "Чек", "choose": "Выбрать позиции"},
    },
    "uz": {
        "people": {OWNER: "Temur", FRIEND: "Alisher", GUEST: "Madina"},
        "title": "«Plov Markazi»da kechki ovqat",
        "coffee": ("Ishdan keyin qahva", [("Kapuchino", 28000), ("Chizkeyk", 35000)]),
        "items": ["Osh", "Qo‘y go‘shtidan shashlik", "Achchiq-chuchuk", "Non", "Ko‘k choy, choynak", "Somsa"],
        "ui": {"next": "Keyingi", "receipt": "Chek", "choose": "Pozitsiyalarni tanlash"},
    },
    "en": {
        "people": {OWNER: "Tim", FRIEND: "Alisher", GUEST: "Madina"},
        "title": "Dinner at Plov Center",
        "coffee": ("Coffee after work", [("Cappuccino", 28000), ("Cheesecake", 35000)]),
        "items": ["Plov", "Lamb kebab", "Tomato and onion salad", "Flatbread", "Green tea, pot", "Samsa"],
        "ui": {"next": "Next", "receipt": "Receipt", "choose": "Choose items"},
    },
}
# Price and how many, in the order of the names above.
PRICES = [(55000, 2), (32000, 3), (18000, 1), (6000, 2), (12000, 2), (9000, 4)]
CARD = "8600 1234 5678 9012"

# What the dev build draws on top of the app, and the home-screen banner,
# which a shortcut already added keeps away.
CHROME = "nextjs-portal{display:none!important} div[style*='z-index: 9999'][style*='position: fixed']{display:none!important}"
WITHOUT_DEV_CONTROLS = """
document.evaluate("//*[starts-with(normalize-space(text()), 'DEV: add mock user')]", document, null, 9, null)
  .singleNodeValue?.parentElement?.remove();
"""
PERSONA = """
(() => {
  const people = %s;
  let installed;
  Object.defineProperty(window, 'Telegram', {
    configurable: true,
    get() { return installed; },
    set(value) {
      const app = value && value.WebApp;
      const user = app && app.initDataUnsafe && app.initDataUnsafe.user;
      if (user && people[user.id]) {
        const persona = {id: user.id, first_name: people[user.id], language_code: '%s', allows_write_to_pm: true};
        app.initDataUnsafe.user = persona;
        const data = new URLSearchParams(app.initData);
        data.set('user', JSON.stringify(persona));
        app.initData = data.toString();
        app.checkHomeScreenStatus = (done) => done && done('added');
      }
      installed = value;
    },
  });
})();
"""


def _server_env(**extra: str) -> dict[str, str]:
    """Blank wherever a .env could reach the real database or the real bot."""
    env = {**os.environ, "DB_HOST": "", "DB_USER": "", "DB_PASSWORD": "", "DB_NAME": "", "TG_TOKEN": "", "TG_WEBHOOK_SECRET": ""}
    return {**env, **extra}


def _wait_for(url: str, seconds: int = 120) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up")


@contextmanager
def _running(command: list[str], cwd: Path, env: dict[str, str], ready: str):
    # A group of its own: npx leaves the Next server it starts running otherwise.
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    try:
        _wait_for(ready)
        yield
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=20)


@contextmanager
def _backend():
    """A fresh database each time, so every language starts from the same ids."""
    with tempfile.TemporaryDirectory() as folder:
        env = _server_env(PYTHONPATH=str(ROOT / "backend"), ENV="development", ALLOW_UNSIGNED_INIT_DATA="1")
        tables = "import app.models; from sqlmodel import SQLModel; from app.database import engine; SQLModel.metadata.create_all(engine)"
        subprocess.run([sys.executable, "-c", tables], cwd=folder, env=env, check=True)
        command = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(API_PORT)]
        with _running(command, Path(folder), env, f"{API}/app-config"):
            yield


@contextmanager
def _frontend():
    env = _server_env(NEXT_PUBLIC_API_URL=API, NEXT_TELEMETRY_DISABLED="1")
    with _running(["npx", "next", "dev", "-p", str(APP_PORT)], ROOT / "frontend", env, APP):
        yield


def _init_data(telegram_id: int, name: str, language: str) -> str:
    user = {"id": telegram_id, "first_name": name, "language_code": language}
    return urlencode({"user": json.dumps(user), "auth_date": str(int(time.time())), "hash": "mock"})


def _seed(language: str) -> dict:
    """The dinner, as the app would have it once the receipt was read and two
    friends sat down: the owner, Alisher (paid), Madina, and a guest's seat."""
    dinner = DINNER[language]
    clients, users = {}, {}
    for telegram_id, name in dinner["people"].items():
        data = _init_data(telegram_id, name, language)
        client = httpx.Client(base_url=API, headers={"X-Telegram-Init-Data": data}, timeout=20)
        user = client.post("/users/", json={"telegram_id": telegram_id, "init_data": data}).raise_for_status().json()
        client.patch(f"/users/{user['id']}/settings", json={"language": language, "currency": "uzs", "onboarding_completed": True}).raise_for_status()
        clients[telegram_id], users[telegram_id] = client, user
    owner = clients[OWNER]

    def bill(title: str, people: int) -> dict:
        return owner.post("/bills/", json={
            "owner_id": users[OWNER]["id"], "total_sum": 0, "title": title, "payment_details": CARD,
            "expected_people": people, "include_owner": True, "currency": "uzs",
        }).raise_for_status().json()

    coffee_title, coffee_items = dinner["coffee"]
    coffee = bill(coffee_title, 3)
    for name, price in coffee_items:
        owner.post(f"/bills/{coffee['id']}/items", json={"name": name, "price": price, "count": 2}).raise_for_status()

    dinner_bill = bill(dinner["title"], 4)
    items = [
        owner.post(f"/bills/{dinner_bill['id']}/items", json={"name": name, "price": price, "count": count}).raise_for_status().json()["id"]
        for name, (price, count) in zip(dinner["items"], PRICES)
    ]
    seats = owner.get(f"/bills/public/{dinner_bill['public_token']}/seats").raise_for_status().json()["seats"]
    free = [seat["id"] for seat in seats if not seat["is_taken"]]
    for telegram_id, seat in zip((FRIEND, GUEST), free):
        clients[telegram_id].post(
            f"/bills/{dinner_bill['id']}/seats/{seat}/claim",
            json={
                "user_id": users[telegram_id]["id"], "invite_code": None, "confirm_move": False,
                # A newcomer needs the invite link's token to take a seat.
                "token": dinner_bill["public_token"],
            },
        ).raise_for_status()

    detail = owner.get(f"/bills/{dinner_bill['id']}", params={"user_id": users[OWNER]["id"]}).raise_for_status().json()
    me, friend, guest, empty = [p["id"] for p in sorted(detail["participants"], key=lambda p: p["seat_index"])]
    plov, kebab, salad, bread, tea, samsa = items
    portions = [
        (plov, me, 0), (plov, friend, 1), (kebab, me, 0), (kebab, guest, 1), (kebab, empty, 2), (salad, guest, 0),
        (samsa, friend, 0), (samsa, friend, 1), (samsa, empty, 2), (samsa, me, 3),
    ]
    owner.post(f"/bills/{dinner_bill['id']}/items/assign-batch", params={"requester_id": users[OWNER]["id"]}, json={
        "shared": [{"item_id": bread, "is_shared_globally": True}, {"item_id": tea, "is_shared_globally": True}],
        "ops": [{"item_id": item, "participant_id": seat, "is_assigned": True, "portion_index": index} for item, seat, index in portions],
    }).raise_for_status()
    clients[FRIEND].post(
        f"/bills/{dinner_bill['id']}/participants/{friend}/payment",
        json={"is_paid": True, "user_id": users[FRIEND]["id"]},
    ).raise_for_status()
    return dinner_bill


class Camera:
    def __init__(self, browser, language: str, folder: Path):
        self.browser, self.language, self.folder = browser, language, folder
        self.people = DINNER[language]["people"]

    def _persona(self, init_data: str) -> str:
        fields = dict(parse_qsl(init_data))
        if "user" in fields:
            user = json.loads(fields["user"])
            name = self.people.get(user["id"], user.get("first_name"))
            fields["user"] = json.dumps({"id": user["id"], "first_name": name, "language_code": self.language, "allows_write_to_pm": True})
        return urlencode(fields)

    def _as_persona(self, route, request) -> None:
        headers = dict(request.headers)
        if "x-telegram-init-data" in headers:
            headers["x-telegram-init-data"] = self._persona(headers["x-telegram-init-data"])
        body = request.post_data
        if body and request.url.rstrip("/").endswith("/api/users"):
            payload = json.loads(body)
            payload.pop("avatar_url", None)
            if payload.get("init_data"):
                payload["init_data"] = self._persona(payload["init_data"])
            body = json.dumps(payload)
        route.continue_(headers=headers, post_data=body)

    @contextmanager
    def open(self, telegram_id: int, path: str):
        context = self.browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3)
        context.route(f"{API}/**", self._as_persona)
        context.route("https://t.me/**", lambda route, request: route.abort())
        context.add_init_script(PERSONA % (json.dumps({str(k): v for k, v in self.people.items()}), self.language))
        page = context.new_page()
        separator = "&" if "?" in path else "?"
        page.goto(f"{APP}{path}{separator}mockUser={MOCK_USER[telegram_id]}", wait_until="networkidle")
        page.wait_for_timeout(1500)
        try:
            yield page
        finally:
            context.close()

    def shoot(self, page: Page, name: str, dialog: bool = False) -> None:
        page.add_style_tag(content=CHROME)
        page.evaluate(WITHOUT_DEV_CONTROLS)
        page.wait_for_timeout(600)
        target = page.locator("[role=dialog]").first if dialog else page
        target.screenshot(path=self.folder / f"{name}.png")


def capture(browser, language: str) -> None:
    folder = HERE / "shots" / language
    folder.mkdir(parents=True, exist_ok=True)
    ui = DINNER[language]["ui"]
    with _backend():
        bill = _seed(language)
        camera = Camera(browser, language, folder)
        with camera.open(OWNER, "/") as page:
            camera.shoot(page, "home")
            page.locator("button:has(svg.lucide-plus)").first.click()
            for name in ("wizard-people", "wizard-card"):
                camera.shoot(page, name, dialog=True)
                page.locator(f'text="{ui["next"]}"').first.click()
            camera.shoot(page, "wizard-source", dialog=True)
        with camera.open(OWNER, f"/bill/{bill['id']}") as page:
            camera.shoot(page, "owner")
            page.locator(f'text="{ui["receipt"]}"').first.click()
            camera.shoot(page, "receipt")
        with camera.open(GUEST, f"/bill/{bill['id']}") as page:
            camera.shoot(page, "guest")
            page.locator(f'text="{ui["choose"]}"').first.click()
            camera.shoot(page, "guest-pick", dialog=True)
        card = httpx.get(f"{API}/bills/public/{bill['public_token']}/card.png", params={"lang": language, "theme": "light"})
        (folder / "card.png").write_bytes(card.raise_for_status().content)
    print(f"shots/{language}")


def main(languages: tuple[str, ...]) -> None:
    with _frontend(), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
        for language in languages:
            capture(browser, language)
        browser.close()


if __name__ == "__main__":
    main(tuple(sys.argv[1:]) or LANGUAGES)
