"""The bot's notice that Pro is about to end: once, a day before a trial
ends, three before anything bought, never for a subscription that renews."""
from datetime import timedelta

from sqlmodel import Session

import app.jobs.pro_ending as pro_ending
from app.models import ProSource, ProSubscription, User
from tests.pro_world import NOW, grant


def test_the_bot_says_when_pro_is_about_to_end_once(session: Session, people, monkeypatch):
    leo, ann = people
    sent = []
    monkeypatch.setattr(pro_ending, "send_message", lambda chat_id, text, markup=None: sent.append((chat_id, text, markup)))
    grant(session, leo, ProSource.TRIAL, NOW - timedelta(days=6, hours=4), 7)
    grant(session, ann, ProSource.PURCHASE, NOW - timedelta(days=170), 172)
    grant(session, ann, ProSource.PROMO, NOW + timedelta(days=2), 30)

    assert pro_ending.run(session, NOW) == 1
    assert pro_ending.run(session, NOW + timedelta(minutes=1)) == 0
    chat_id, text, markup = sent[0]
    assert chat_id == leo.telegram_id and text.startswith("Пробная неделя Pro закончится")
    assert markup["inline_keyboard"][0][0]["url"].endswith("startapp=pro")


def test_the_notice_waits_out_the_night(session: Session, people, monkeypatch):
    leo, _ = people
    sent = []
    monkeypatch.setattr(pro_ending, "send_message", lambda *a, **k: sent.append(a))
    night = NOW.replace(hour=20)  # 01:00 in Tashkent
    grant(session, leo, ProSource.TRIAL, night - timedelta(days=6, hours=4), 7)

    assert pro_ending.run(session, night) == 0
    assert pro_ending.run(session, night + timedelta(hours=9)) == 1


def test_a_subscription_is_not_warned_about(session: Session, people, monkeypatch):
    leo, _ = people
    sent = []
    monkeypatch.setattr(pro_ending, "send_message", lambda *a, **k: sent.append(a))
    grant(session, leo, ProSource.SUBSCRIPTION, NOW - timedelta(days=29), 30)

    assert pro_ending.run(session, NOW) == 0


def test_a_subscription_whose_renewal_was_stopped_is_warned_about(session: Session, people, monkeypatch):
    leo, _ = people
    sent = []
    monkeypatch.setattr(pro_ending, "send_message", lambda chat_id, text, markup=None: sent.append(text))
    stopped = ProSubscription(user_id=leo.id, charge_id="sub-1", renewal_canceled_at=NOW - timedelta(days=5))
    session.add(stopped)
    session.commit()
    month = grant(session, leo, ProSource.SUBSCRIPTION, NOW - timedelta(days=28), 30)
    month.subscription_id = stopped.id
    session.add(month)
    session.commit()

    assert pro_ending.run(session, NOW) == 1
    assert sent[0].startswith("Pro закончится")


def test_trials_not_yet_due_do_not_crowd_out_a_purchase_that_is(session: Session, people, monkeypatch):
    leo, _ = people
    sent = []
    monkeypatch.setattr(pro_ending, "send_message", lambda chat_id, *a, **k: sent.append(chat_id))
    monkeypatch.setattr(pro_ending, "BATCH", 3)
    for index in range(5):
        early = User(telegram_id=1000 + index, name=f"Trial {index}")
        session.add(early)
        session.commit()
        grant(session, early, ProSource.TRIAL, NOW - timedelta(days=5), 7)
    grant(session, leo, ProSource.PURCHASE, NOW - timedelta(days=180), 182)

    assert pro_ending.run(session, NOW) == 1
    assert sent == [leo.telegram_id]

