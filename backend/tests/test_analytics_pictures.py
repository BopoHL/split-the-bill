"""The analytics pictures' signed addresses: handed only to the person, good
only for what they were signed for, and enough on their own for Telegram to
fetch a picture or for the receipt to go out as a photo."""
import io
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.services.analytics_pictures as analytics_pictures
from app.services.analytics import Period, PeriodKind
from app.services.picture_links import address_for, asked
from app.services.report_card import WIDTH

SEPTEMBER = Period(PeriodKind.MONTH, 2026, 9)
MOMENT = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _bot_token(monkeypatch):
    monkeypatch.setenv("TG_TOKEN", "123:test-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split.example")


def _size(jpeg: bytes) -> tuple[int, int]:
    picture = Image.open(io.BytesIO(jpeg))
    assert picture.format == "JPEG"
    return picture.size


def test_an_address_holds_only_for_what_it_was_signed_for():
    address = address_for(7, "receipt", SEPTEMBER, "dark", MOMENT)
    query = parse_qs(urlparse(address.url("https://split.example")).query)
    signature = query["sig"][0]

    def read(**changes):
        fields = dict(user_id=7, picture="receipt", kind=PeriodKind.MONTH, year=2026, month=9, theme="dark", expires=address.expires)
        fields.update(changes)
        return asked(**fields)

    assert read().holds(signature, MOMENT)
    assert not read(user_id=8).holds(signature, MOMENT)
    assert not read(month=8).holds(signature, MOMENT)
    assert not read(picture="bills").holds(signature, MOMENT)
    assert not read(theme="light").holds(signature, MOMENT)
    assert not read().holds(signature, MOMENT + timedelta(days=2))


def test_a_year_hands_out_the_receipt_and_its_stories(client: TestClient, world):
    answer = client.get(f"/users/{world['me'].id}/analytics/pictures", params={"period": "year", "year": 2026})

    assert answer.status_code == 200
    body = answer.json()
    assert body["receipt"].startswith(f"https://split.example/api/public/analytics/{world['me'].id}/receipt.jpg?")
    assert [story["story"] for story in body["stories"]] == ["bills", "dish", "person"]
    assert body["story_text"].startswith("Мои итоги 2026 в Split·Bill https://t.me/")

    month = client.get(f"/users/{world['me'].id}/analytics/pictures", params={"period": "month", "year": 2026, "month": 9}).json()
    assert (month["stories"], month["story_text"]) == ([], None)


def test_only_i_get_my_addresses_and_only_with_pro(client: TestClient, world):
    client.act_as(world["alice"].telegram_id)

    assert client.get(f"/users/{world['me'].id}/analytics/pictures").status_code == 403
    assert client.post(f"/users/{world['me'].id}/analytics/prepare-share").status_code == 403
    without = client.get(f"/users/{world['alice'].id}/analytics/pictures")
    assert (without.status_code, without.json()["detail"]) == (402, {"code": "PRO_REQUIRED", "feature": "analytics"})


def _path(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    return parsed.path.removeprefix("/api"), {key: values[0] for key, values in parse_qs(parsed.query).items()}


def test_a_signed_address_opens_the_picture_without_a_session(client: TestClient, world):
    body = client.get(f"/users/{world['me'].id}/analytics/pictures", params={"period": "year", "year": 2026}).json()
    client.act_as(None)

    path, query = _path(body["receipt"])
    receipt = client.get(path, params=query, headers={"X-Telegram-Init-Data": ""})
    assert (receipt.status_code, receipt.headers["content-type"]) == (200, "image/jpeg")
    assert _size(receipt.content)[0] == WIDTH

    path, query = _path(body["stories"][1]["url"])
    story = client.get(path, params={**query, "download": "true"}, headers={"X-Telegram-Init-Data": ""})
    assert _size(story.content) == (1080, 1920)
    assert story.headers["content-disposition"] == 'attachment; filename="split-bill-dish.jpg"'

    forged = client.get(path, params={**query, "sig": "0" * 32}, headers={"X-Telegram-Init-Data": ""})
    assert forged.status_code == 403


def test_a_story_is_only_for_a_year(client: TestClient, world):
    month = Period(PeriodKind.MONTH, 2026, 9)
    address = address_for(world["me"].id, "dish", month, "light", datetime.now(timezone.utc))
    path, query = _path(address.url("https://split.example"))

    assert client.get(path, params=query, headers={"X-Telegram-Init-Data": ""}).status_code == 404


def test_the_receipt_goes_to_telegram_as_a_photo(client: TestClient, world, monkeypatch):
    sent = {}

    def save(telegram_user_id, **message):
        sent.update(message, user=telegram_user_id)
        return "prepared-1"

    monkeypatch.setattr(analytics_pictures, "save_prepared_photo_message", save)
    answer = client.post(f"/users/{world['me'].id}/analytics/prepare-share", params={"period": "month", "year": 2026, "month": 9})

    assert answer.json() == {"prepared_message_id": "prepared-1"}
    assert sent["user"] == world["me"].telegram_id
    assert sent["photo_url"].startswith(f"https://split.example/api/public/analytics/{world['me'].id}/receipt.jpg?")
    assert sent["caption"] == "Отчёт за сентябрь 2026 — Split·Bill"
    assert sent["reply_markup"]["inline_keyboard"][0][0]["url"].startswith("https://t.me/")
