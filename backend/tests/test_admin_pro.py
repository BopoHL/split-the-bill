"""Pro in the admin panel: prices, the free day's scans, who has it, promo codes."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import ProSource
from tests.pro_world import grant


@pytest.fixture
def admin(client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    from app.routers import admin as admin_router

    admin_router._LOGIN_ATTEMPTS.clear()
    assert client.post("/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}).status_code == 200
    return client


def test_the_admin_sets_prices_and_the_free_scans(admin: TestClient, session: Session, people):
    leo, _ = people
    grant(session, leo, ProSource.PURCHASE, datetime.utcnow() - timedelta(days=1), 30).stars = 500
    session.commit()

    body = admin.put("/admin/pro", json={"prices": {"month": 150}, "free_scans_per_day": 5}).json()

    assert body["prices"] == {"month": 150, "half_year": 500, "year": 900}
    assert body["free_scans_per_day"] == 5
    assert (body["stats"]["active"], body["stats"]["paying"], body["stats"]["stars_total"]) == (1, 1, 500)
    assert admin.put("/admin/pro", json={"prices": {"month": 0}}).status_code == 400
    assert admin.put("/admin/pro", json={"prices": {"week": 10}}).status_code == 400


def test_the_admin_sets_the_first_purchase_offer(admin: TestClient):
    assert (admin.get("/admin/pro").json()["offer_percent"], admin.get("/admin/pro").json()["offer_hours"]) == (40, 48)

    body = admin.put("/admin/pro", json={"offer_percent": 0, "offer_hours": 24}).json()

    assert (body["offer_percent"], body["offer_hours"]) == (0, 24)
    assert admin.put("/admin/pro", json={"offer_percent": 95}).status_code == 400
    assert admin.put("/admin/pro", json={"offer_hours": 0}).status_code == 400


def test_a_struck_out_was_price_shows_above_the_price_and_can_be_taken_away(admin: TestClient, session: Session, people):
    leo, _ = people

    body = admin.put("/admin/pro", json={"was_prices": {"year": 1200, "month": 150}}).json()
    assert body["was_prices"] == {"month": 150, "half_year": None, "year": 1200}
    assert admin.put("/admin/pro", json={"was_prices": {"year": 900}}).status_code == 400
    # A refused change writes nothing, the price beside it included.
    assert admin.put("/admin/pro", json={"prices": {"half_year": 600}, "was_prices": {"half_year": 550}}).status_code == 400
    assert admin.get("/admin/pro").json()["prices"]["half_year"] == 500

    admin.act_as(leo.telegram_id)
    plans = {plan["plan"]: plan["was_stars"] for plan in admin.get(f"/users/{leo.id}/pro").json()["plans"]}
    assert plans == {"month": 150, "half_year": None, "year": 1200}

    admin.act_as(None)
    # A price raised to it leaves nothing to strike out.
    admin.put("/admin/pro", json={"prices": {"month": 150}})
    admin.act_as(leo.telegram_id)
    assert admin.get(f"/users/{leo.id}/pro").json()["plans"][0]["was_stars"] is None

    admin.act_as(None)
    assert admin.put("/admin/pro", json={"was_prices": {"year": None}}).json()["was_prices"]["year"] is None


def test_the_admin_makes_and_switches_off_promo_codes(admin: TestClient):
    named = admin.post("/admin/pro/promo-codes", json={"code": "launch-50", "days": 30, "max_uses": 50}).json()
    made_up = admin.post("/admin/pro/promo-codes", json={"days": 7}).json()

    assert (named["code"], named["max_uses"], named["is_active"]) == ("LAUNCH-50", 50, True)
    assert len(made_up["code"]) == 8
    assert admin.post("/admin/pro/promo-codes", json={"code": "LAUNCH-50", "days": 1}).status_code == 409
    assert admin.post("/admin/pro/promo-codes", json={"code": "x!", "days": 1}).status_code == 400
    assert admin.patch(f"/admin/pro/promo-codes/{named['id']}", json={"is_active": False}).json()["is_active"] is False
    assert [code["code"] for code in admin.get("/admin/pro/promo-codes").json()] == [made_up["code"], "LAUNCH-50"]


def test_a_promo_code_ends_at_the_moment_given_in_any_zone(admin: TestClient):
    tashkent = admin.post("/admin/pro/promo-codes", json={"days": 7, "expires_at": "2026-11-01T00:00:00+05:00"}).json()
    utc = admin.post("/admin/pro/promo-codes", json={"days": 7, "expires_at": "2026-11-01T00:00:00"}).json()

    assert tashkent["expires_at"].startswith("2026-10-31T19:00:00")
    assert utc["expires_at"].startswith("2026-11-01T00:00:00")
