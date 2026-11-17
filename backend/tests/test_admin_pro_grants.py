"""Pro grants in the admin panel: who has Pro, since when, for how long and
why — and taking it back: ending it now, refunding the Stars, stopping a
subscription from renewing. Telegram is stubbed."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import ProGrant, ProPlan, ProSource, ProSubscription, PromoCode, User
from app.services.pro import ProService, invoice_payload
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


def _paid(session: Session, user: User, plan: ProPlan, charge: str, stars: int, now: datetime, **flags) -> ProGrant:
    payment = {
        "currency": "XTR",
        "total_amount": stars,
        "invoice_payload": invoice_payload(plan, user.id),
        "telegram_payment_charge_id": charge,
        **flags,
    }
    return ProService(session).record_payment(user.telegram_id, payment, now)


def _rows(admin: TestClient, **params) -> list[dict]:
    return admin.get("/admin/pro/grants", params=params).json()["items"]


def test_every_grant_is_listed_newest_first_with_whose_it_is_and_what_can_be_done(
    admin: TestClient, session: Session, people, stars
):
    leo, ann = people
    now = datetime.utcnow()
    code = PromoCode(code="LAUNCH", days=14)
    session.add(code)
    session.commit()
    ProService(session).redeem(ann.id, "launch", now - timedelta(days=2))
    year = _paid(session, leo, ProPlan.YEAR, "c-year", 900, now - timedelta(days=1))

    rows = _rows(admin)

    assert [(row["user"]["username"], row["source"]) for row in rows] == [("leo", "purchase"), ("ann", "promo")]
    bought, promo = rows
    assert (bought["id"], bought["plan"], bought["days"], bought["stars"], bought["state"]) == (year.id, "year", 365, 900, "active")
    assert bought["actions"] == ["revoke", "refund"]
    assert (promo["promo_code"], promo["days"], promo["stars"], promo["actions"]) == ("LAUNCH", 14, None, ["revoke"])
    assert [row["source"] for row in _rows(admin, source="promo")] == ["promo"]
    assert [row["user"]["username"] for row in _rows(admin, q="@ann")] == ["ann"]
    assert [row["user"]["username"] for row in _rows(admin, user_id=leo.id)] == ["leo"]
    assert admin.get("/admin/pro/grants", params={"source": "gift"}).status_code == 422


def test_taking_back_a_promo_moves_up_what_was_bought_after_it(admin: TestClient, session: Session, people, stars):
    leo, _ = people
    now = datetime.utcnow()
    promo = grant(session, leo, ProSource.PROMO, now - timedelta(days=1), 10)
    year = _paid(session, leo, ProPlan.YEAR, "c-year", 900, now)
    queued_for = year.ends_at - year.starts_at

    taken = admin.post(f"/admin/pro/grants/{promo.id}/revoke").json()

    assert (taken["state"], taken["actions"]) == ("revoked", [])
    session.expire_all()
    moved = session.get(ProGrant, year.id)
    # The year paid for starts now, not where the promo would have ended.
    assert abs(moved.starts_at - datetime.utcnow()) < timedelta(minutes=1)
    assert moved.ends_at - moved.starts_at == queued_for
    assert ProService(session).is_pro(leo.id, datetime.utcnow())
    assert [row["source"] for row in _rows(admin, running=True)] == ["purchase"]
    assert admin.post(f"/admin/pro/grants/{promo.id}/revoke").status_code == 409
    assert stars["refunds"] == stars["renewals"] == []


def test_taking_back_a_subscription_month_stops_it_renewing_first(admin: TestClient, session: Session, people, stars):
    leo, _ = people
    now = datetime.utcnow()
    first = _paid(session, leo, ProPlan.MONTH, "c-first", 100, now - timedelta(days=31), is_recurring=True, is_first_recurring=True)
    month = _paid(session, leo, ProPlan.MONTH, "c-renewal", 100, now - timedelta(days=1), is_recurring=True)
    first_row = next(row for row in _rows(admin) if row["id"] == first.id)
    assert first_row["actions"] == ["refund"]

    taken = admin.post(f"/admin/pro/grants/{month.id}/revoke").json()

    # Telegram knows the subscription by its first payment.
    assert stars["renewals"] == [(leo.telegram_id, "c-first", True)]
    assert taken["state"] == "revoked" and taken["renewal_canceled_at"] is not None
    assert not ProService(session).is_pro(leo.id, datetime.utcnow())


def test_a_refund_gives_the_stars_back_and_ends_what_they_paid_for(
    admin: TestClient, session: Session, people, stars, product_events
):
    leo, _ = people
    year = _paid(session, leo, ProPlan.YEAR, "c-year", 900, datetime.utcnow())

    refunded = admin.post(f"/admin/pro/grants/{year.id}/refund").json()

    assert stars["refunds"] == [(leo.telegram_id, "c-year")]
    assert (refunded["state"], refunded["actions"]) == ("refunded", [])
    assert refunded["refunded_at"] is not None and refunded["revoked_at"] is not None
    assert not ProService(session).is_pro(leo.id, datetime.utcnow())
    assert admin.get("/admin/pro").json()["stats"]["stars_total"] == 0
    assert admin.post(f"/admin/pro/grants/{year.id}/refund").status_code == 409
    assert product_events == [
        ("pro_refunded", str(leo.id), {"surface": "server", "plan": "year", "stars": 900, "source": "purchase"}),
    ]


def test_a_refund_telegram_refuses_changes_nothing(admin: TestClient, session: Session, people, stars):
    leo, _ = people
    year = _paid(session, leo, ProPlan.YEAR, "c-year", 900, datetime.utcnow())
    stars["fail"] = "CHARGE_ID_INVALID"

    answer = admin.post(f"/admin/pro/grants/{year.id}/refund")

    assert (answer.status_code, answer.json()["detail"]) == (502, "Telegram error: CHARGE_ID_INVALID")
    session.expire_all()
    kept = session.get(ProGrant, year.id)
    assert (kept.refunded_at, kept.revoked_at) == (None, None)
    assert ProService(session).is_pro(leo.id, datetime.utcnow())


def test_a_refund_whose_answer_was_lost_ends_the_pro_when_tried_again(admin: TestClient, session: Session, people, stars):
    """The Stars went back but the reply did not: «already refunded» on the
    next try means done, or every retry fails and the Pro stays for free."""
    leo, _ = people
    year = _paid(session, leo, ProPlan.YEAR, "c-year", 900, datetime.utcnow())
    stars["fail"] = "CHARGE_ALREADY_REFUNDED"

    refunded = admin.post(f"/admin/pro/grants/{year.id}/refund")

    assert refunded.status_code == 200 and refunded.json()["state"] == "refunded"
    assert not ProService(session).is_pro(leo.id, datetime.utcnow())


def test_a_subscription_stops_renewing_and_may_renew_again(admin: TestClient, session: Session, people, stars):
    leo, _ = people
    month = _paid(session, leo, ProPlan.MONTH, "c-first", 100, datetime.utcnow(), is_recurring=True, is_first_recurring=True)
    renewal = f"/admin/pro/subscriptions/{month.subscription_id}/renewal"

    stopped = admin.put(renewal, json={"canceled": True}).json()

    assert stopped["actions"] == ["revoke", "refund", "allow_renewal"]
    # Pro stays to the end of the month paid for.
    assert ProService(session).is_pro(leo.id, datetime.utcnow())
    assert admin.put(renewal, json={"canceled": True}).status_code == 409

    allowed = admin.put(renewal, json={"canceled": False}).json()

    assert allowed["actions"] == ["revoke", "refund", "stop_renewal"]
    assert stars["renewals"] == [(leo.telegram_id, "c-first", True), (leo.telegram_id, "c-first", False)]
    session.expire_all()
    assert session.get(ProSubscription, month.subscription_id).renewal_canceled_at is None
    assert admin.put("/admin/pro/subscriptions/999/renewal", json={"canceled": True}).status_code == 404
