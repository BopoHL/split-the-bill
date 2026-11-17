"""Payment reminders: who gets nudged, how often, and when we stop.

The job recomputes eligibility from the bills on every tick, so these tests
drive it directly with a controlled clock rather than through the scheduler.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.services.shared_bill_service as shared
from app.jobs import payment_reminders
from app.models import Bill, PaymentReminder, ProGrant, ProSource
from sqlmodel import select


class _NoFaces:
    @staticmethod
    def for_people(telegram_ids):
        return {}


@pytest.fixture(autouse=True)
def _no_faces(monkeypatch):
    monkeypatch.setattr(shared, "profile_photos", _NoFaces())


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing Telegram messages instead of sending them."""
    outbox = []

    def fake_send(chat_id, text, reply_markup=None, parse_mode="HTML", link_preview_options=None):
        outbox.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return {"ok": True}

    monkeypatch.setattr(shared, "send_message", fake_send)
    return outbox


def _settled_bill(client: TestClient, session, tg=900, amount=100.0, pro=True):
    """An open bill where everything is allocated and the guest hasn't paid —
    its owner with Pro, which reminders take, unless told otherwise."""
    owner = client.post("/users/", json={"telegram_id": tg, "username": "owner"}).json()["id"]
    if pro:
        _give_pro(session, owner)
    guest_user = client.post(
        "/users/", json={"telegram_id": tg + 1, "username": "guest"}
    ).json()["id"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner, "total_sum": 0, "title": "Dinner",
            "include_owner": True, "expected_people": 2,
            "payment_details": "8600 1234 5678 9012",
        },
    ).json()
    bid = bill["id"]

    seat = next(
        p for p in client.get(f"/bills/{bid}?user_id={owner}").json()["participants"]
        if p["user_id"] is None
    )
    client.post(f"/bills/{bid}/seats/{seat['id']}/claim", json={"user_id": guest_user})

    item = client.post(
        f"/bills/{bid}/items", json={"name": "Plov", "price": amount, "count": 1}
    ).json()
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": item["id"], "participant_id": seat["id"], "is_assigned": True}]},
    )
    return owner, guest_user, bid, seat["id"]


def _give_pro(session, user_id: int, ends_at: datetime = datetime(2100, 1, 1)) -> None:
    session.add(ProGrant(user_id=user_id, source=ProSource.PROMO, starts_at=datetime(2026, 1, 1), ends_at=ends_at))
    session.commit()


# Well outside the quiet window in any plausible timezone.
NOON = datetime(2026, 8, 11, 9, 0)


def test_first_tick_only_arms_the_reminder(client: TestClient, session, sent):
    _settled_bill(client, session, tg=900)

    assert payment_reminders.run(session, NOON) == 0
    reminder = session.exec(select(PaymentReminder)).one()
    assert reminder.sent_count == 0
    assert reminder.next_due_at > NOON
    assert sent == []


def test_reminder_goes_out_once_it_is_due(client: TestClient, session, sent):
    _settled_bill(client, session, tg=902)
    payment_reminders.run(session, NOON)

    assert payment_reminders.run(session, NOON + timedelta(minutes=16)) == 1
    assert len(sent) == 1
    body = sent[0]["text"]
    assert "Dinner" in body
    assert "8600123456789012" in body  # the card is right there to copy
    buttons = [button for row in sent[0]["markup"]["inline_keyboard"] for button in row]
    assert any(button.get("callback_data", "").startswith("share_paid:") for button in buttons)
    assert any(button.get("url", "").startswith("https://t.me/") for button in buttons)


def test_intervals_grow_instead_of_repeating_every_15_minutes(client: TestClient, session, sent):
    _settled_bill(client, session, tg=904)
    payment_reminders.run(session, NOON)

    now = NOON + timedelta(minutes=16)
    payment_reminders.run(session, now)
    first = session.exec(select(PaymentReminder)).one()
    gap_after_first = first.next_due_at - now

    now2 = first.next_due_at
    payment_reminders.run(session, now2)
    session.expire_all()
    second = session.exec(select(PaymentReminder)).one()
    gap_after_second = second.next_due_at - now2

    assert gap_after_first == timedelta(minutes=30)
    assert gap_after_second == timedelta(minutes=60)
    assert second.sent_count == 2


def test_the_owner_is_never_reminded(client: TestClient, session, sent):
    owner, _, bid, _ = _settled_bill(client, session, tg=906)
    payment_reminders.run(session, NOON)
    payment_reminders.run(session, NOON + timedelta(minutes=16))

    owner_tg = 906
    assert all(m["chat_id"] != owner_tg for m in sent)


def test_paying_stops_the_reminders(client: TestClient, session, sent):
    owner, guest, bid, seat_id = _settled_bill(client, session, tg=908)
    payment_reminders.run(session, NOON)
    client.post(
        f"/bills/{bid}/participants/{seat_id}/payment",
        json={"is_paid": True, "user_id": guest},
    )

    assert payment_reminders.run(session, NOON + timedelta(minutes=16)) == 0
    assert sent == []
    session.expire_all()
    assert session.exec(select(PaymentReminder)).one().next_due_at is None


def test_old_bills_do_not_start_payment_reminders(client: TestClient, session, sent):
    _, _, bid, _ = _settled_bill(client, session, tg=909)
    bill = session.get(Bill, bid)
    bill.created_at = payment_reminders.local_day_start(NOON) - timedelta(seconds=1)
    session.add(bill)
    session.commit()

    assert payment_reminders.run(session, NOON) == 0
    assert session.exec(select(PaymentReminder)).first() is None
    assert sent == []


@pytest.mark.parametrize("quiet, morning", [
    ("23:00-09:00", datetime(2026, 8, 12, 4, 0)),  # 09:00 next day in Tashkent
    ("23:00-10:00", datetime(2026, 8, 12, 5, 0)),  # 10:00
])
def test_a_reminder_put_off_by_the_night_still_goes_out_in_the_morning(client: TestClient, session, sent, monkeypatch, quiet, morning):
    monkeypatch.setenv("REMINDER_QUIET_HOURS", quiet)
    late_evening = datetime(2026, 8, 11, 17, 50)  # 22:50 in Tashkent, quiet from 23:00
    _, _, bid, _ = _settled_bill(client, session, tg=914)
    bill = session.get(Bill, bid)
    bill.created_at = late_evening
    session.add(bill)
    session.commit()
    payment_reminders.run(session, late_evening)

    assert payment_reminders.run(session, morning) == 1
    assert len(sent) == 1


def test_an_unallocated_remainder_holds_the_reminders_back(client: TestClient, session, sent):
    """While part of the bill is unassigned the amount could still change."""
    owner, _, bid, _ = _settled_bill(client, session, tg=910)
    client.post(f"/bills/{bid}/items", json={"name": "Tea", "price": 20, "count": 1})

    assert payment_reminders.run(session, NOON) == 0
    assert session.exec(select(PaymentReminder)).first() is None


def test_a_deleted_bill_stops_reminding(client: TestClient, session, sent):
    owner, _, bid, _ = _settled_bill(client, session, tg=912)
    payment_reminders.run(session, NOON)
    client.delete(f"/bills/{bid}?user_id={owner}")

    assert payment_reminders.run(session, NOON + timedelta(minutes=16)) == 0
    assert sent == []


def test_a_blocked_bot_mutes_the_reminder_for_good(client: TestClient, session, monkeypatch):
    _settled_bill(client, session, tg=914)
    payment_reminders.run(session, NOON)

    def blocked(*args, **kwargs):
        raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(shared, "send_message", blocked)
    assert payment_reminders.run(session, NOON + timedelta(minutes=16)) == 0

    session.expire_all()
    assert session.exec(select(PaymentReminder)).one().muted_at is not None


def _results(product_events) -> list[tuple[str, dict]]:
    return [(distinct_id, properties) for event, distinct_id, properties in product_events if event == "reminder_result"]


def test_an_automatic_reminder_is_counted_for_the_person_reminded(client: TestClient, session, sent, product_events):
    _, guest, bill_id, _ = _settled_bill(client, session, tg=930)
    payment_reminders.run(session, NOON)

    payment_reminders.run(session, NOON + timedelta(minutes=16))

    assert _results(product_events) == [
        (str(guest), {"surface": "server", "bill_id": bill_id, "auto": True, "ok": True, "channel": "bot"}),
    ]


def test_a_blocked_bot_is_counted_once_as_the_end_of_automatic_reminders(
    client: TestClient, session, monkeypatch, product_events
):
    _, guest, bill_id, _ = _settled_bill(client, session, tg=932)
    payment_reminders.run(session, NOON)

    def blocked(*args, **kwargs):
        raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(shared, "send_message", blocked)
    payment_reminders.run(session, NOON + timedelta(minutes=16))
    payment_reminders.run(session, NOON + timedelta(hours=5))

    assert _results(product_events) == [
        (str(guest), {"surface": "server", "bill_id": bill_id, "auto": True, "ok": False, "reason": "unreachable"}),
    ]


def test_without_pro_each_person_is_reminded_once(client: TestClient, session, sent):
    _settled_bill(client, session, tg=918, pro=False)
    payment_reminders.run(session, NOON)

    assert payment_reminders.run(session, NOON + timedelta(minutes=16)) == 1
    assert payment_reminders.run(session, NOON + timedelta(hours=3)) == 0
    assert len(sent) == 1
    session.expire_all()
    assert session.exec(select(PaymentReminder)).one().next_due_at is None


def test_reminders_go_quiet_when_pro_ends_and_come_back_with_it(client: TestClient, session, sent):
    owner, _, _, _ = _settled_bill(client, session, tg=920, pro=False)
    _give_pro(session, owner, ends_at=NOON + timedelta(minutes=30))
    payment_reminders.run(session, NOON)
    assert payment_reminders.run(session, NOON + timedelta(minutes=16)) == 1

    # Pro has ended and the free reminder is spent.
    assert payment_reminders.run(session, NOON + timedelta(minutes=50)) == 0
    session.expire_all()
    assert session.exec(select(PaymentReminder)).one().next_due_at is None

    _give_pro(session, owner)
    later = NOON + timedelta(hours=1)
    payment_reminders.run(session, later)
    assert payment_reminders.run(session, later + timedelta(minutes=31)) == 1
    assert len(sent) == 2


def test_scheduler_lock_is_a_no_op_outside_postgres(session):
    """Tests run on SQLite, where there is only ever one process."""
    from app.scheduler import advisory_lock

    with advisory_lock(session.get_bind(), 1) as acquired:
        assert acquired is True


class _FakePostgres:
    """Just enough of an Engine to exercise the branch SQLite never reaches:
    every connection it hands out is recorded, with what ran on it."""

    def __init__(self, acquired=True):
        self.dialect = SimpleNamespace(name="postgresql")
        self.connections = []
        self._acquired = acquired

    def connect(self):
        connection = _FakeConnection(self._acquired)
        self.connections.append(connection)
        return connection


class _FakeConnection:
    def __init__(self, acquired):
        self.calls = []
        self.options = {}
        self.closed = False
        self._acquired = acquired

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def execution_options(self, **options):
        self.options |= options
        return self

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return SimpleNamespace(scalar=lambda: self._acquired)


def test_advisory_lock_is_held_on_a_connection_of_its_own():
    """Not the job's session: that one gives its connection back to the pool
    at every commit, and the lock would stay behind on it."""
    from app.scheduler import advisory_lock

    engine = _FakePostgres()
    with advisory_lock(engine, 4242) as acquired:
        assert acquired is True
        [connection] = engine.connections
        assert not connection.closed

    assert connection.options == {"isolation_level": "AUTOCOMMIT"}
    assert [params for _, params in connection.calls] == [{"key": 4242}, {"key": 4242}]
    assert "pg_try_advisory_lock" in connection.calls[0][0]
    assert "pg_advisory_unlock" in connection.calls[1][0]
    assert connection.closed


def test_a_lock_held_elsewhere_skips_the_job_without_unlocking_it():
    from app.scheduler import advisory_lock

    engine = _FakePostgres(acquired=False)
    with advisory_lock(engine, 1) as acquired:
        assert acquired is False

    # Only the attempt — releasing a lock we never took would free another replica's.
    assert len(engine.connections[0].calls) == 1


def test_a_bug_in_the_reminder_job_is_not_mistaken_for_a_telegram_refusal(
    client: TestClient, session, monkeypatch
):
    """A missing import once turned into one warning per user and a feature
    that silently never ran. Telegram saying no is routine; this is not."""
    _settled_bill(client, session, tg=916)
    payment_reminders.run(session, NOON)

    def broken(*args, **kwargs):
        raise NameError("mini_app_link is not defined")

    monkeypatch.setattr(shared, "send_message", broken)
    with pytest.raises(NameError):
        payment_reminders.run(session, NOON + timedelta(minutes=16))

    session.expire_all()
    reminder = session.exec(select(PaymentReminder)).one()
    # Nothing went out, so nothing is marked as sent — and nothing is muted,
    # which is what a real refusal would have done.
    assert reminder.sent_count == 0
    assert reminder.muted_at is None
