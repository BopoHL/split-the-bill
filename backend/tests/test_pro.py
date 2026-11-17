"""Pro: who has it until when, paying with Telegram Stars, promo codes, the
free day's scans, the notice before it ends, and the admin's side of it."""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.routers.pro as pro_router
import app.services.pro_payments as pro_payments
from app.models import ProGrant, PromoCode, ProPlan, ProSource, ProSubscription, TelegramUpdate, User
from app.services.app_settings import set_setting
from app.services.bot_updates import BotUpdates
from app.services.pro import PromoError, ProService, invoice_payload
from app.services.telegram_updates import TelegramUpdateQueue
from tests.pro_world import NOW, grant
from tests.telegram_world import WORKER, next_update_id


def _payment(plan: ProPlan, user: User, charge: str, stars: int, **subscription) -> dict:
    return {
        "currency": "XTR",
        "total_amount": stars,
        "invoice_payload": invoice_payload(plan, user.id),
        "telegram_payment_charge_id": charge,
        **subscription,
    }


def test_pro_is_whatever_grant_covers_now(session: Session, people):
    leo, ann = people
    pro = ProService(session)
    grant(session, leo, ProSource.TRIAL, NOW - timedelta(days=1), 7)

    status = pro.status(leo.id, NOW)
    assert (status.active, status.trial, status.until) == (True, True, NOW + timedelta(days=6))
    assert not pro.is_pro(ann.id, NOW)
    assert not pro.is_pro(leo.id, NOW + timedelta(days=7))
    assert pro.pro_among({leo.id, ann.id}, NOW) == {leo.id}


def test_what_is_bought_starts_where_the_trial_ends(session: Session, people):
    leo, _ = people
    pro = ProService(session)
    grant(session, leo, ProSource.TRIAL, NOW, 7)

    year = pro.record_payment(leo.telegram_id, _payment(ProPlan.YEAR, leo, "c-1", 900), NOW)

    assert (year.source, year.starts_at, year.ends_at) == ("purchase", NOW + timedelta(days=7), NOW + timedelta(days=372))
    assert pro.status(leo.id, NOW).until == NOW + timedelta(days=372)


def test_a_payment_reported_twice_is_granted_once_and_a_month_is_a_subscription(session: Session, people):
    leo, _ = people
    pro = ProService(session)

    first = pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True), NOW,
    )
    again = pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True), NOW,
    )
    renewal = pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-2", 100, is_recurring=True), NOW + timedelta(days=29),
    )

    assert first.id == again.id
    assert first.source == "subscription"
    assert renewal.starts_at == first.ends_at
    assert pro.status(leo.id, NOW).subscription
    # Telegram knows the subscription by its first payment, renewals and all.
    assert first.subscription_id == renewal.subscription_id
    assert session.get(ProSubscription, first.subscription_id).charge_id == "c-1"


def test_a_renewal_belongs_to_the_subscription_still_renewing(session: Session, people):
    leo, _ = people
    pro = ProService(session)
    first = pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True), NOW,
    )
    stopped = pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-5", 100, is_recurring=True, is_first_recurring=True), NOW,
    )
    subscription = session.get(ProSubscription, stopped.subscription_id)
    subscription.renewal_canceled_at = NOW
    session.add(subscription)
    session.commit()

    renewal = pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-2", 100, is_recurring=True), NOW + timedelta(days=29),
    )

    assert renewal.subscription_id == first.subscription_id


def test_a_payment_for_someone_else_grants_nothing(session: Session, people):
    leo, ann = people

    assert ProService(session).record_payment(ann.telegram_id, _payment(ProPlan.YEAR, leo, "c-9", 900), NOW) is None
    assert session.exec(select(ProGrant)).all() == []


def test_the_invoice_is_in_stars_and_only_a_month_renews(session: Session, people):
    leo, _ = people
    pro = ProService(session)
    set_setting(session, "pro_price_year", "777")

    month = pro.invoice(leo, ProPlan.MONTH, "ru", NOW)
    year = pro.invoice(leo, ProPlan.YEAR, "en", NOW)

    assert (month["currency"], month["subscription_period"], month["prices"][0]["amount"]) == ("XTR", 2592000, 100)
    assert "subscription_period" not in year
    assert (year["prices"][0]["amount"], year["payload"]) == (777, f"pro:year:{leo.id}")


def test_checkout_lets_through_only_the_payer_at_todays_price(session: Session, people):
    leo, ann = people
    pro = ProService(session)
    payload = invoice_payload(ProPlan.HALF_YEAR, leo.id)

    assert pro.checkout_problem(payload, leo.telegram_id, "XTR", 500, NOW) is None
    assert pro.checkout_problem(payload, ann.telegram_id, "XTR", 500, NOW) == "pro_checkout_failed"
    assert pro.checkout_problem(payload, leo.telegram_id, "XTR", 400, NOW) == "pro_price_changed"
    assert pro.checkout_problem("something:else", leo.telegram_id, "XTR", 500, NOW) == "pro_checkout_failed"


def test_checkout_never_stands_between_a_subscription_and_its_renewal(session: Session, people):
    leo, _ = people
    pro = ProService(session)
    pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True), NOW,
    )

    assert pro.checkout_problem(invoice_payload(ProPlan.MONTH, leo.id), leo.telegram_id, "XTR", 100, NOW) is None


def test_a_promo_code_works_once_per_person_while_it_lasts(session: Session, people):
    leo, ann = people
    pro = ProService(session)
    session.add_all([
        PromoCode(code="FRIENDS", days=30, max_uses=1),
        PromoCode(code="OLD", days=30, expires_at=NOW - timedelta(days=1)),
    ])
    session.commit()

    grant = pro.redeem(leo.id, " friends ", NOW)
    assert (grant.source, grant.ends_at) == ("promo", NOW + timedelta(days=30))
    for user, code, reason in [
        (leo, "FRIENDS", "PROMO_ALREADY_USED"),
        (ann, "FRIENDS", "PROMO_USED_UP"),
        (ann, "OLD", "PROMO_EXPIRED"),
        (ann, "NOPE", "PROMO_UNKNOWN"),
    ]:
        with pytest.raises(PromoError, match=reason):
            pro.redeem(user.id, code, NOW)


def test_the_same_code_twice_is_refused(session: Session, people):
    leo, _ = people
    session.add(PromoCode(code="TWICE", days=7))
    session.commit()
    ProService(session).redeem(leo.id, "TWICE", NOW)

    with pytest.raises(PromoError, match="PROMO_ALREADY_USED"):
        ProService(session).redeem(leo.id, "TWICE", NOW)


def test_the_app_learns_status_prices_and_scans_left(client: TestClient, session: Session, people):
    leo, _ = people
    grant(session, leo, ProSource.TRIAL, datetime.utcnow() - timedelta(days=1), 7)

    body = client.get(f"/users/{leo.id}/pro").json()

    assert (body["active"], body["trial"], body["scans_left_today"]) == (True, True, None)
    assert [(plan["plan"], plan["stars"], plan["recurring"]) for plan in body["plans"]] == [
        ("month", 100, True), ("half_year", 500, False), ("year", 900, False),
    ]


def test_the_app_gets_an_invoice_link_and_redeems_codes(client: TestClient, session: Session, people, monkeypatch):
    leo, ann = people
    asked = []
    monkeypatch.setattr(pro_router, "create_invoice_link", lambda invoice: asked.append(invoice) or "https://t.me/$abc")
    session.add(PromoCode(code="HELLO", days=14))
    session.commit()

    assert client.post(f"/users/{leo.id}/pro/invoice", json={"plan": "year"}).json() == {"link": "https://t.me/$abc"}
    assert asked[0]["title"] == "Split·Bill Pro на год"
    assert client.post(f"/users/{leo.id}/pro/invoice", json={"plan": "week"}).status_code == 400
    assert client.post(f"/users/{leo.id}/pro/redeem", json={"code": "hello"}).json()["active"]
    assert client.post(f"/users/{leo.id}/pro/redeem", json={"code": "hello"}).json()["detail"] == {"code": "PROMO_ALREADY_USED"}

    client.act_as(ann.telegram_id)
    assert client.get(f"/users/{leo.id}/pro").status_code == 403


def test_the_bot_takes_the_payment_and_says_thanks(session: Session, people, monkeypatch):
    leo, _ = people
    answers, sent = [], []
    monkeypatch.setattr(pro_payments, "answer_pre_checkout_query", lambda query_id, error=None: answers.append((query_id, error)))
    monkeypatch.setattr(pro_payments, "send_message", lambda chat_id, text, *a, **k: sent.append((chat_id, text)))
    updates = BotUpdates(session)

    updates.handle({"pre_checkout_query": {
        "id": "q1", "from": {"id": leo.telegram_id}, "currency": "XTR", "total_amount": 900,
        "invoice_payload": invoice_payload(ProPlan.YEAR, leo.id),
    }})
    updates.handle({"pre_checkout_query": {
        "id": "q2", "from": {"id": leo.telegram_id}, "currency": "XTR", "total_amount": 1,
        "invoice_payload": invoice_payload(ProPlan.YEAR, leo.id),
    }})
    updates.handle({"message": {
        "chat": {"id": leo.telegram_id}, "from": {"id": leo.telegram_id},
        "successful_payment": _payment(ProPlan.YEAR, leo, "c-1", 900),
    }})

    assert answers == [("q1", None), ("q2", "Цена изменилась. Откройте оплату в приложении ещё раз.")]
    assert ProService(session).is_pro(leo.id, datetime.utcnow())
    assert sent[0][0] == leo.telegram_id and sent[0][1].startswith("⭐ Pro включён до ")


def test_a_payment_is_counted_once_however_often_telegram_reports_it(
    session: Session, people, told, product_events
):
    leo, _ = people
    updates = BotUpdates(session)
    paid = _paid_update(leo, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True))

    updates.handle(paid)
    updates.handle(paid)
    updates.handle(_paid_update(leo, _payment(ProPlan.MONTH, leo, "c-2", 100, is_recurring=True)))

    assert product_events == [
        ("pro_purchased", str(leo.id), {"surface": "server", "plan": "month", "stars": 100, "source": "subscription", "renewal": False}),
        ("pro_purchased", str(leo.id), {"surface": "server", "plan": "month", "stars": 100, "source": "subscription", "renewal": True}),
    ]


def _paid_update(user: User, payment: dict) -> dict:
    return {"message": {"chat": {"id": user.telegram_id}, "from": {"id": user.telegram_id}, "successful_payment": payment}}


@pytest.fixture
def told(monkeypatch) -> list[str]:
    sent = []
    monkeypatch.setattr(pro_payments, "send_message", lambda chat_id, text, *a, **k: sent.append(text))
    return sent


def test_a_second_subscription_is_given_back_and_stops_renewing(session: Session, people, stars, told, product_events):
    leo, _ = people
    now = datetime.utcnow()
    pro = ProService(session)
    updates = BotUpdates(session)
    first = pro.record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True), now,
    )
    # A month link the bot sent before the subscription began, paid after.
    second = _paid_update(leo, _payment(ProPlan.MONTH, leo, "c-7", 100, is_recurring=True, is_first_recurring=True))

    updates.handle(second)
    updates.handle(second)

    assert stars["renewals"] == [(leo.telegram_id, "c-7", True)]
    assert stars["refunds"] == [(leo.telegram_id, "c-7")]
    assert told == ["Подписка на месяц у вас уже идёт и продлевается сама, поэтому вторую мы отменили и вернули звёзды."]
    assert [event for event, _, _ in product_events] == ["pro_purchased", "pro_refunded"]
    status = pro.status(leo.id, now)
    assert (status.until, status.subscription) == (first.ends_at, True)

    updates.handle(_paid_update(
        leo, _payment(ProPlan.MONTH, leo, "c-2", 100, is_recurring=True),
    ))

    renewal = session.exec(select(ProGrant).where(ProGrant.charge_id == "c-2")).one()
    assert (renewal.subscription_id, renewal.refunded_at) == (first.subscription_id, None)
    assert stars["refunds"] == [(leo.telegram_id, "c-7")]
    assert told[-1].startswith("⭐ Pro включён до ")


def test_a_refund_telegram_refuses_comes_again_with_the_payment(session: Session, people, stars, told):
    leo, _ = people
    now = datetime.utcnow()
    updates = BotUpdates(session)
    ProService(session).record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True), now,
    )
    second = _paid_update(leo, _payment(ProPlan.MONTH, leo, "c-7", 100, is_recurring=True, is_first_recurring=True))

    stars["fail"] = "INTERNAL_ERROR"
    with pytest.raises(HTTPException):
        updates.handle(second)
    stars["fail"] = None
    updates.handle(second)

    assert stars["refunds"] == [(leo.telegram_id, "c-7")]
    assert told == ["Подписка на месяц у вас уже идёт и продлевается сама, поэтому вторую мы отменили и вернули звёзды."]


def test_a_subscription_after_one_that_stopped_renewing_is_kept(session: Session, people, stars, told):
    leo, _ = people
    now = datetime.utcnow()
    first = ProService(session).record_payment(
        leo.telegram_id, _payment(ProPlan.MONTH, leo, "c-1", 100, is_recurring=True, is_first_recurring=True), now,
    )
    stopped = session.get(ProSubscription, first.subscription_id)
    stopped.renewal_canceled_at = now
    session.add(stopped)
    session.commit()

    BotUpdates(session).handle(_paid_update(
        leo, _payment(ProPlan.MONTH, leo, "c-7", 100, is_recurring=True, is_first_recurring=True),
    ))

    assert stars["refunds"] == stars["renewals"] == []
    assert told[-1].startswith("⭐ Pro включён до ")
    assert ProService(session).status(leo.id, now).until == first.ends_at + timedelta(days=30)


def test_a_subscription_paid_ahead_counts_even_behind_the_trial(client: TestClient, session: Session, people, monkeypatch):
    leo, _ = people
    now = datetime.utcnow()
    grant(session, leo, ProSource.TRIAL, now - timedelta(days=1), 7)
    ProService(session).record_payment(leo.telegram_id, _payment(ProPlan.MONTH, leo, "sub-1", 100), now)
    monkeypatch.setattr(pro_router, "create_invoice_link", lambda invoice: "https://t.me/$abc")

    assert ProService(session).status(leo.id, now).subscription
    month = client.post(f"/users/{leo.id}/pro/invoice", json={"plan": "month"})
    assert (month.status_code, month.json()["detail"]) == (409, "SUBSCRIPTION_ACTIVE")
    assert client.post(f"/users/{leo.id}/pro/invoice", json={"plan": "year"}).status_code == 200


def test_a_subscription_whose_renewal_was_stopped_lets_a_new_month_be_bought(
    client: TestClient, session: Session, people, monkeypatch
):
    leo, _ = people
    now = datetime.utcnow()
    pro = ProService(session)
    pro.record_payment(leo.telegram_id, _payment(ProPlan.MONTH, leo, "sub-1", 100), now)
    subscription = session.exec(select(ProSubscription).where(ProSubscription.user_id == leo.id)).one()
    subscription.renewal_canceled_at = now
    session.add(subscription)
    session.commit()
    monkeypatch.setattr(pro_router, "create_invoice_link", lambda invoice: "https://t.me/$abc")

    assert pro.status(leo.id, now).active and not pro.status(leo.id, now).subscription
    assert client.post(f"/users/{leo.id}/pro/invoice", json={"plan": "month"}).status_code == 200


def test_a_payment_in_anything_but_stars_grants_nothing(session: Session, people):
    leo, _ = people

    assert ProService(session).record_payment(leo.telegram_id, {**_payment(ProPlan.YEAR, leo, "c-x", 900), "currency": "USD"}, NOW) is None


def test_a_promo_code_whose_uses_are_gone_is_refused(session: Session, people):
    leo, _ = people
    session.add(PromoCode(code="LAST", days=7, max_uses=2, uses=2))
    session.commit()

    with pytest.raises(PromoError, match="PROMO_USED_UP"):
        ProService(session).redeem(leo.id, "LAST", NOW)
    assert session.exec(select(PromoCode).where(PromoCode.code == "LAST")).one().uses == 2


def test_payments_are_only_taken_from_a_webhook_with_its_secret(client: TestClient, session: Session, people, monkeypatch):
    leo, _ = people
    monkeypatch.setattr(pro_payments, "send_message", lambda *a, **k: None)
    update = {"update_id": next_update_id(), "message": {
        "chat": {"id": leo.telegram_id}, "from": {"id": leo.telegram_id},
        "successful_payment": _payment(ProPlan.YEAR, leo, "c-forged", 900),
    }}

    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)
    assert client.post("/telegram/webhook", json=update).status_code == 200
    assert not ProService(session).is_pro(leo.id, datetime.utcnow())

    monkeypatch.setenv("TG_WEBHOOK_SECRET", "s3")
    headers = {"X-Telegram-Bot-Api-Secret-Token": "s3"}
    assert client.post("/telegram/webhook", json=update, headers=headers).status_code == 200
    assert ProService(session).is_pro(leo.id, datetime.utcnow())


def test_a_payment_that_fails_to_record_is_tried_again(client: TestClient, session: Session, people, monkeypatch):
    """Given up, the Stars would be gone and Pro never given."""
    leo, _ = people
    monkeypatch.setenv("TG_WEBHOOK_SECRET", "s3")
    monkeypatch.setattr(pro_payments, "send_message", lambda *a, **k: None)
    record = ProService.record_payment

    def broken(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(ProService, "record_payment", broken)
    update_id = next_update_id()
    assert client.post(
        "/telegram/webhook",
        json={"update_id": update_id, "message": {"chat": {"id": 1}, "from": {"id": leo.telegram_id},
                                                  "successful_payment": _payment(ProPlan.YEAR, leo, "c-2", 900)}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3"},
    ).status_code == 200

    kept = session.get(TelegramUpdate, update_id)
    assert kept.done_at is None and "db gone" in kept.error
    assert not ProService(session).is_pro(leo.id, datetime.utcnow())

    monkeypatch.setattr(ProService, "record_payment", record)
    queue = TelegramUpdateQueue(session)
    assert list(queue.claim(kept.not_before, limit=10, holder=WORKER)) == [update_id]
    queue.handle(update_id, holder=WORKER)

    assert ProService(session).is_pro(leo.id, datetime.utcnow())
    assert session.get(TelegramUpdate, update_id).done_at is not None

def test_a_promo_code_is_not_found_by_trying_them_all(client: TestClient, session: Session, people):
    leo, _ = people
    client.act_as(leo.telegram_id)

    misses = [client.post(f"/users/{leo.id}/pro/redeem", json={"code": f"GUESS{i}"}).status_code for i in range(5)]
    stopped = client.post(f"/users/{leo.id}/pro/redeem", json={"code": "GUESS6"})

    assert misses == [400] * 5
    assert (stopped.status_code, stopped.json()["detail"]) == (429, {"code": "PROMO_TOO_MANY"})


def test_the_end_of_pro_reaches_the_app_with_its_zone(client: TestClient, session: Session, people):
    """Without one, a phone read 21:30 UTC as its own 21:30 and showed a day early."""
    leo, _ = people
    grant(session, leo, ProSource.PROMO, datetime.utcnow() - timedelta(days=1), 30)
    client.act_as(leo.telegram_id)

    until = client.get(f"/users/{leo.id}/pro").json()["until"]

    assert until.endswith(("Z", "+00:00"))
