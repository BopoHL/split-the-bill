"""Labeling in the admin panel: how the job is doing, and the history run
the admin starts, pauses and resumes."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Bill, BillItem
from app.services.labeling_control import LabelingControl


@pytest.fixture
def admin(client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("OPENAI_LABEL_MODEL", raising=False)
    from app.routers import admin as admin_router

    admin_router._LOGIN_ATTEMPTS.clear()
    assert client.post("/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}).status_code == 200
    return client


def test_the_panel_shows_the_job_and_runs_the_history_on_request(admin: TestClient, session: Session):
    long_ago = datetime.utcnow() - timedelta(days=30)
    bill = Bill(owner_id=1, title="Ужин", created_at=long_ago, updated_at=long_ago)
    session.add(bill)
    session.commit()
    session.add(BillItem(bill_id=bill.id, name="Плов", price=100, item_sum=100, updated_at=long_ago))
    session.commit()

    before = admin.get("/admin/labeling").json()
    assert (before["key_set"], before["model"], before["since"], before["history"]) == (True, "gpt-6-luna", None, None)

    started = admin.post("/admin/labeling/history").json()
    assert started["since"] is not None
    assert {key: started["history"][key] for key in ("state", "lines_done", "lines_total", "bills_done", "bills_total")} == {
        "state": "running", "lines_done": 0, "lines_total": 1, "bills_done": 0, "bills_total": 1,
    }
    assert admin.post("/admin/labeling/history").status_code == 409

    assert admin.post("/admin/labeling/history/pause").json()["history"]["state"] == "paused"
    assert admin.post("/admin/labeling/history").json()["history"]["state"] == "running"


def test_the_history_does_not_start_without_a_model_key(admin: TestClient, session: Session, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")

    assert admin.get("/admin/labeling").json()["key_set"] is False
    refused = admin.post("/admin/labeling/history")

    assert (refused.status_code, refused.json()["detail"]) == (409, "OPENAI_API_KEY is not set")
    assert LabelingControl(session).history() is None


def test_only_the_admin_sees_it(client: TestClient):
    assert client.get("/admin/labeling").status_code == 401
