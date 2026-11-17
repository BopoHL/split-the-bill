from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import ProOffer, ProPlan, ProSource
from app.services.app_settings import PRO_OFFER_HOURS_KEY, PRO_OFFER_PERCENT_KEY, set_setting
from app.services.pro import OFFER_CHECKOUT_GRACE, ProService, invoice_payload
from tests.pro_world import NOW, grant


def _stars(pro: ProService, user_id: int, now) -> dict[str, tuple[int, int | None]]:
    return {plan.value: (price.stars, price.was) for plan, price in pro.price_list(user_id, now).items()}


def test_the_offer_is_made_once_and_takes_off_only_what_is_paid_up_front(session: Session, people, product_events):
    leo, _ = people
    pro = ProService(session)

    offer = pro.start_offer(leo.id, NOW)

    assert (offer.percent, offer.ends_at) == (40, NOW + timedelta(hours=48))
    assert _stars(pro, leo.id, NOW) == {"month": (100, None), "half_year": (300, 500), "year": (540, 900)}
    assert pro.start_offer(leo.id, NOW + timedelta(hours=1)).id == offer.id
    assert product_events == [("pro_offer_started", str(leo.id), {"surface": "server", "percent": 40, "hours": 48})]


def test_once_it_runs_out_it_is_gone_for_good(session: Session, people):
    leo, _ = people
    pro = ProService(session)
    pro.start_offer(leo.id, NOW)
    later = NOW + timedelta(hours=48)

    assert pro.start_offer(leo.id, later) is None
    assert _stars(pro, leo.id, later)["year"] == (900, None)
    assert len(session.exec(select(ProOffer)).all()) == 1


def test_nobody_who_has_paid_is_offered_it_nor_anyone_while_it_is_switched_off(session: Session, people):
    leo, ann = people
    grant(session, leo, ProSource.PURCHASE, NOW - timedelta(days=400), 365)
    set_setting(session, PRO_OFFER_PERCENT_KEY, "0")
    pro = ProService(session)

    assert pro.start_offer(ann.id, NOW) is None
    set_setting(session, PRO_OFFER_PERCENT_KEY, "25")
    set_setting(session, PRO_OFFER_HOURS_KEY, "6")
    assert pro.start_offer(leo.id, NOW) is None
    assert (pro.start_offer(ann.id, NOW).percent, pro.offer(ann.id, NOW).ends_at) == (25, NOW + timedelta(hours=6))


def test_the_invoice_charges_the_offer_and_checkout_honours_it_a_little_past_its_end(session: Session, people):
    leo, _ = people
    pro = ProService(session)
    offer = pro.start_offer(leo.id, NOW)
    payload = invoice_payload(ProPlan.YEAR, leo.id)

    assert pro.invoice(leo, ProPlan.YEAR, "ru", NOW)["prices"][0]["amount"] == 540
    assert pro.checkout_problem(payload, leo.telegram_id, "XTR", 540, NOW) is None
    assert pro.checkout_problem(payload, leo.telegram_id, "XTR", 900, NOW) == "pro_price_changed"
    assert pro.checkout_problem(payload, leo.telegram_id, "XTR", 540, offer.ends_at + OFFER_CHECKOUT_GRACE / 2) is None
    assert pro.checkout_problem(payload, leo.telegram_id, "XTR", 540, offer.ends_at + OFFER_CHECKOUT_GRACE) == "pro_price_changed"
    assert pro.checkout_problem(payload, leo.telegram_id, "XTR", 900, offer.ends_at + OFFER_CHECKOUT_GRACE) is None


def test_the_app_starts_the_offer_when_the_paywall_opens_and_only_then(client: TestClient, session: Session, people):
    leo, _ = people
    client.act_as(leo.telegram_id)

    assert client.get(f"/users/{leo.id}/pro").json()["offer"] is None
    started = client.post(f"/users/{leo.id}/pro/offer").json()

    assert started["offer"]["percent"] == 40
    assert started["offer"]["ends_at"].endswith("Z")
    assert {plan["plan"]: (plan["stars"], plan["was_stars"]) for plan in started["plans"]} == {
        "month": (100, None), "half_year": (300, 500), "year": (540, 900),
    }
    assert client.get(f"/users/{leo.id}/pro").json()["offer"] == started["offer"]


def test_the_offer_is_on_the_first_purchase_only(session: Session, people):
    """Bought at −40%, a second year a minute later was −40% again."""
    leo, _ = people
    pro = ProService(session)
    pro.start_offer(leo.id, NOW)
    grant(session, leo, ProSource.PURCHASE, NOW, 365)

    assert pro.offer(leo.id, NOW + timedelta(minutes=10)) is None
    assert _stars(pro, leo.id, NOW + timedelta(minutes=10))["year"] == (900, None)
