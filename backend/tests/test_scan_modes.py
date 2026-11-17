"""Three ways to read a receipt, and the switch that picks one.

The modes fail differently — OCR flattens the layout, a vision model can misread
a glyph — so which one is better is a question about real receipts. These tests
only prove the switch reaches the model and that every scan records who read it.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.worker as worker
from app.models import AppSetting, ScanMode
from app.routers import admin as admin_router
from app.services.app_settings import (
    LABEL_MODEL_KEY, RECEIPT_MODEL_KEY, SCAN_MODE_KEY, get_label_model, get_receipt_model, get_scan_mode,
)


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    from app.routers import admin

    admin._LOGIN_ATTEMPTS.clear()


def _login(client: TestClient) -> None:
    assert (
        client.post(
            "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
        ).status_code
        == 200
    )


def test_the_default_reader_is_the_one_that_was_always_there(session: Session):
    assert get_scan_mode(session) == ScanMode.OCR_LLM


def test_an_unreadable_setting_falls_back_instead_of_stopping_every_scan(session: Session):
    session.add(AppSetting(key=SCAN_MODE_KEY, value="telepathy"))
    session.commit()

    assert get_scan_mode(session) == ScanMode.OCR_LLM


def test_the_operator_can_switch_readers_and_read_it_back(client: TestClient):
    _login(client)

    assert client.get("/admin/settings").json()["scan_mode"] == "ocr_llm"
    assert client.put("/admin/settings", json={"scan_mode": "vision"}).status_code == 200
    assert client.get("/admin/settings").json()["scan_mode"] == "vision"

    refused = client.put("/admin/settings", json={"scan_mode": "telepathy"})
    assert refused.status_code == 400
    assert client.get("/admin/settings").json()["scan_mode"] == "vision"


def test_receipts_are_read_by_gpt_6_luna_unless_told_otherwise(session: Session, monkeypatch):
    monkeypatch.delenv("OPENAI_RECEIPT_MODEL", raising=False)
    assert get_receipt_model(session) == "gpt-6-luna"

    monkeypatch.setenv("OPENAI_RECEIPT_MODEL", "gpt-5.6-luna")
    assert get_receipt_model(session) == "gpt-5.6-luna"

    session.add(AppSetting(key=RECEIPT_MODEL_KEY, value="gpt-6-sol"))
    session.commit()
    assert get_receipt_model(session) == "gpt-6-sol"


def test_the_operator_switches_the_model_once_openai_knows_it(client: TestClient, monkeypatch):
    known = {"gpt-6-luna", "gpt-6-sol"}
    monkeypatch.delenv("OPENAI_RECEIPT_MODEL", raising=False)
    monkeypatch.setattr(admin_router, "model_exists", lambda name: name in known)
    _login(client)

    assert client.get("/admin/settings").json()["receipt_model"] == "gpt-6-luna"
    switched = client.put("/admin/settings", json={"receipt_model": "gpt-6-sol"})
    assert switched.status_code == 200
    assert switched.json()["receipt_model"] == "gpt-6-sol"

    typo = client.put("/admin/settings", json={"receipt_model": "gpt-6-sool"})
    assert typo.status_code == 400
    assert client.get("/admin/settings").json()["receipt_model"] == "gpt-6-sol"


def test_lines_are_labeled_by_gpt_6_luna_whatever_reads_receipts(session: Session, monkeypatch):
    monkeypatch.delenv("OPENAI_LABEL_MODEL", raising=False)
    session.add(AppSetting(key=RECEIPT_MODEL_KEY, value="gpt-6-sol"))
    session.commit()
    assert get_label_model(session) == "gpt-6-luna"

    monkeypatch.setenv("OPENAI_LABEL_MODEL", "gpt-5.6-luna")
    assert get_label_model(session) == "gpt-5.6-luna"

    session.add(AppSetting(key=LABEL_MODEL_KEY, value="gpt-6-sol"))
    session.commit()
    assert get_label_model(session) == "gpt-6-sol"


def test_the_operator_switches_the_labeling_model_apart_from_the_reading_one(client: TestClient, monkeypatch):
    monkeypatch.delenv("OPENAI_LABEL_MODEL", raising=False)
    monkeypatch.setattr(admin_router, "model_exists", lambda name: name in {"gpt-6-luna", "gpt-5.6-luna"})
    _login(client)

    switched = client.put("/admin/settings", json={"label_model": "gpt-5.6-luna"}).json()

    assert (switched["label_model"], switched["receipt_model"]) == ("gpt-5.6-luna", "gpt-6-luna")
    assert client.put("/admin/settings", json={"label_model": "gpt-6-sool"}).status_code == 400
    assert client.get("/admin/settings").json()["label_model"] == "gpt-5.6-luna"


def test_a_model_openai_could_not_be_asked_about_is_not_saved(client: TestClient, monkeypatch):
    def offline(_name):
        raise ConnectionError("no route to api.openai.com")

    monkeypatch.setattr(admin_router, "model_exists", offline)
    _login(client)

    refused = client.put("/admin/settings", json={"receipt_model": "gpt-6-sol"})

    assert refused.status_code == 502
    assert client.get("/admin/settings").json()["receipt_model"] != "gpt-6-sol"


def test_settings_are_closed_without_a_session(client: TestClient):
    assert client.get("/admin/settings").status_code == 401
    assert client.put("/admin/settings", json={"scan_mode": "vision"}).status_code == 401


class _Capture:
    """Stands in for the OpenAI client and keeps what it was asked."""

    def __init__(self):
        self.kwargs = {}

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        payload = json.dumps({"title": "T", "total_sum": 100, "items": []})
        return type(
            "R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": payload})()})()]}
        )()


@pytest.fixture
def captured(monkeypatch) -> _Capture:
    capture = _Capture()
    monkeypatch.setattr(
        worker,
        "get_openai_client",
        lambda: type("Client", (), {"chat": type("Chat", (), {"completions": type("Completions", (), {"create": staticmethod(capture)})()})()})(),
    )
    return capture


def _content(capture: _Capture):
    return capture.kwargs["messages"][1]["content"]


@pytest.mark.asyncio
async def test_ocr_mode_sends_text_and_no_picture(captured):
    await worker._gpt_structure("COLA 100", None, model="gpt-6-luna")

    body = _content(captured)
    assert isinstance(body, str)
    assert "COLA 100" in body


@pytest.mark.asyncio
async def test_vision_mode_sends_the_photo_and_says_so(captured):
    await worker._gpt_structure(None, None, image=b"\xff\xd8jpeg", model="gpt-6-luna")

    body = _content(captured)
    parts = {part["type"] for part in body}
    assert parts == {"text", "image_url"}
    image = next(part for part in body if part["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "attached as a photo" in next(p for p in body if p["type"] == "text")["text"]


@pytest.mark.asyncio
async def test_hybrid_sends_both_and_names_which_one_wins(captured):
    await worker._gpt_structure("COLA 100", None, image=b"\xff\xd8jpeg", model="gpt-6-luna")

    body = _content(captured)
    text = next(part for part in body if part["type"] == "text")["text"]
    assert any(part["type"] == "image_url" for part in body)
    assert "COLA 100" in text
    # The photo carries the layout; the text is only a second opinion on glyphs.
    assert "prefer the photo" in text
