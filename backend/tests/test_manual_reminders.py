"""Reminders the owner sends by hand: who gets one, how often, and how each one
gets through — from the bot, or through the sender accounts when the bot is
blocked. Telegram is stubbed at both edges: the Bot API and the accounts."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.services.shared_bill_service as shared
from app.jobs import manual_reminders
from app.models import (
    FreeReminderUse,
    Bill,
    BillItem,
    BillUser,
    Invite,
    InviteChannel,
    ManualReminder,
    ProGrant,
    SenderAccount,
    SenderAccountStatus,
    SharedBillMessage,
    User,
)
from app.services import sender_telegram
import app.services.reminder_service as reminder_service
from app.services.reminder_service import ReminderService, WhyNobody, count_reminder
from app.utils import crypto
from tests.telegram_world import next_update_id

OWNER = 7001
DANA = 101  # joined, has a username
OLEG = 102  # joined, no username


@pytest.fixture
def telegram(monkeypatch):
    """The bot's sends and the accounts' sends, with what each should answer."""
    state = {
        "bot_blocked": set(),
        "bot_sent": [],
        "bot_tries": [],
        "prepared": [],
        "account_sends": [],
        "previews": [],
        # session -> what the account's send does: None (sent) or an exception
        "accounts": {},
    }

    class _NoFaces:
        @staticmethod
        def for_people(telegram_ids):
            return {}

    def send_message(chat_id, text, markup, **kwargs):
        state["bot_tries"].append(chat_id)
        if chat_id in state["bot_blocked"]:
            raise RuntimeError("Telegram error: Forbidden: bot was blocked by the user")
        state["bot_sent"].append(chat_id)
        return {"message_id": 1}

    def save_prepared(uid, **message):
        state["prepared"].append(uid)
        return f"PREPARED-{uid}"

    def send_prepared(session, prepared_id, username, telegram_id, preview_url=None):
        state["account_sends"].append((session, prepared_id, username))
        state["previews"].append(preview_url)
        outcome = state["accounts"].get(session)
        if outcome:
            raise outcome

    monkeypatch.setattr(shared, "profile_photos", _NoFaces())
    monkeypatch.setattr(shared, "send_message", send_message)
    monkeypatch.setattr(shared, "save_prepared_text_message", save_prepared)
    monkeypatch.setattr(shared, "answer_callback_query", lambda *a, **k: None)
    monkeypatch.setattr(sender_telegram, "send_prepared", send_prepared)
    monkeypatch.setenv("TG_API_ID", "1")
    monkeypatch.setenv("TG_API_HASH", "h")
    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)
    return state


def _join(client: TestClient, code: str, seat_id: int, telegram_id: int, username: str | None):
    client.post("/telegram/webhook", json={"update_id": next_update_id(), "callback_query": {
        "id": "cb", "data": f"share_seat:{code}:{seat_id}", "chat_instance": "1", "inline_message_id": "SHARED",
        "from": {"id": telegram_id, "first_name": f"U{telegram_id}", **({"username": username} if username else {})},
    }})


def _table(client: TestClient, session: Session, telegram) -> tuple[dict, dict[str, BillUser]]:
    """Owner — with Pro, which reminders take — Dana and Oleg on their seats
    with a dish each, and one guest seat nobody took, with a dish too."""
    owner = client.post("/users/", json={"telegram_id": OWNER, "username": "leo", "name": "Leonid"}).json()
    session.add(ProGrant(user_id=owner["id"], source="promo", starts_at=datetime(2026, 1, 1), ends_at=datetime(2100, 1, 1)))
    session.commit()
    bill = client.post("/bills/", json={
        "owner_id": owner["id"], "total_sum": 0, "title": "Ужин", "include_owner": True,
        "expected_people": 4, "payment_details": "8600 1234 5678 9012",
    }).json()
    client.post(f"/bills/{bill['id']}/prepare-share", json={})
    code = session.exec(select(SharedBillMessage)).one().invite_code
    guests = session.exec(
        select(BillUser).where(BillUser.bill_id == bill["id"], BillUser.user_id.is_(None)).order_by(BillUser.seat_index)
    ).all()
    _join(client, code, guests[0].id, DANA, "dana")
    _join(client, code, guests[1].id, OLEG, None)
    seats = {"dana": guests[0], "oleg": guests[1], "guest": guests[2]}
    for name, seat in seats.items():
        item = client.post(f"/bills/{bill['id']}/items", json={"name": f"Плов {name}", "price": 30000, "count": 1}).json()
        client.post(f"/bills/{bill['id']}/items/{item['id']}/assign", json={"participant_id": seat.id, "is_assigned": True})
    session.expire_all()
    telegram["prepared"].clear()
    return bill, seats


def _account(session: Session, n: int, **fields) -> SenderAccount:
    account = SenderAccount(
        phone=f"+99890000000{n}",
        session_enc=crypto.encrypt(f"session-{n}"),
        telegram_id=500 + n,
        status=fields.pop("status", SenderAccountStatus.ACTIVE),
        **fields,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _remind(client: TestClient, bill: dict, participant_id: int | None = None, actor: int = OWNER):
    client.act_as(actor)
    try:
        return client.post(f"/bills/{bill['id']}/reminders", json={"participant_id": participant_id})
    finally:
        client.act_as(None)


def _deliver(session: Session, now: datetime | None = None) -> None:
    manual_reminders.run(session, now)
    session.expire_all()


def _reminder_of(client: TestClient, bill: dict, seat: BillUser) -> dict | None:
    client.act_as(OWNER)
    detail = client.get(f"/bills/{bill['id']}").json()
    client.act_as(None)
    return next(p for p in detail["participants"] if p["id"] == seat.id)["reminder"]


def _latest(session: Session, seat: BillUser) -> ManualReminder:
    session.expire_all()
    return session.exec(
        select(ManualReminder).where(ManualReminder.participant_id == seat.id).order_by(ManualReminder.id.desc())
    ).first()


def test_the_owner_reminds_one_person_and_the_bot_delivers_it(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)

    response = _remind(client, bill, seats["dana"].id)

    assert response.status_code == 200
    assert response.json() == {"queued": 1, "skipped": []}
    assert _reminder_of(client, bill, seats["dana"])["status"] == "pending"

    _deliver(session)

    assert telegram["bot_sent"] == [DANA]
    reminder = _latest(session, seats["dana"])
    assert (reminder.status, reminder.channel) == ("sent", "bot")
    assert session.exec(select(User).where(User.telegram_id == DANA)).one().settings["bot_blocked"] is False
    state = _reminder_of(client, bill, seats["dana"])
    assert state["status"] == "sent"
    assert datetime.fromisoformat(state["next_at"]) == (reminder.created_at + timedelta(hours=1)).replace(tzinfo=timezone.utc)


def _results(session: Session, product_events) -> list[tuple[int, dict]]:
    """reminder_result as sent, by the person's telegram id."""
    by_id = {str(user.id): user.telegram_id for user in session.exec(select(User)).all()}
    return sorted(
        ((by_id[distinct_id], properties) for event, distinct_id, properties in product_events if event == "reminder_result"),
        key=lambda result: result[0],
    )


def test_how_each_reminder_ended_is_counted_for_whoever_it_was_meant_for(
    client: TestClient, session: Session, telegram, product_events
):
    bill, seats = _table(client, session, telegram)
    telegram["bot_blocked"].add(OLEG)

    _remind(client, bill)
    _deliver(session)

    assert _results(session, product_events) == [
        (DANA, {"surface": "server", "bill_id": bill["id"], "auto": False, "ok": True, "channel": "bot"}),
        (OLEG, {"surface": "server", "bill_id": bill["id"], "auto": False, "ok": False, "reason": "unreachable"}),
    ]


def test_a_reminder_an_account_delivered_is_counted_with_that_channel(
    client: TestClient, session: Session, telegram, product_events
):
    bill, seats = _table(client, session, telegram)
    telegram["bot_blocked"].add(DANA)
    _account(session, 1)

    _remind(client, bill, seats["dana"].id)
    _deliver(session)

    assert _results(session, product_events) == [
        (DANA, {"surface": "server", "bill_id": bill["id"], "auto": False, "ok": True, "channel": "account"}),
    ]


def test_a_reminder_that_could_not_be_counted_stays_sent(client: TestClient, session: Session, telegram, monkeypatch):
    bill, seats = _table(client, session, telegram)

    def broken(*args, **kwargs):
        raise RuntimeError("analytics down")

    monkeypatch.setattr(reminder_service, "count_reminder", broken)
    _remind(client, bill, seats["dana"].id)
    _deliver(session)

    assert telegram["bot_sent"] == [DANA]
    reminder = _latest(session, seats["dana"])
    assert (reminder.status, reminder.channel) == ("sent", "bot")


def test_an_outcome_with_no_name_is_not_counted(product_events):
    count_reminder(1, 2, auto=False, failure="carrier_pigeon")

    assert product_events == []


def test_one_person_is_reminded_once_an_hour(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    _remind(client, bill, seats["dana"].id)
    _deliver(session)

    again = _remind(client, bill, seats["dana"].id).json()
    assert again == {"queued": 0, "skipped": [{"participant_id": seats["dana"].id, "reason": "cooldown"}]}

    reminder = _latest(session, seats["dana"])
    reminder.created_at -= timedelta(minutes=61)
    session.add(reminder)
    session.commit()
    assert _remind(client, bill, seats["dana"].id).json()["queued"] == 1


def test_reminding_everyone_skips_who_cannot_or_need_not_be_reminded(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    seats["oleg"].is_paid = True
    session.add(seats["oleg"])
    session.commit()

    body = _remind(client, bill).json()

    owner_seat = session.exec(
        select(BillUser).where(BillUser.bill_id == bill["id"], BillUser.seat_index == 0)
    ).one()
    assert body["queued"] == 1
    assert {(s["participant_id"], s["reason"]) for s in body["skipped"]} == {
        (owner_seat.id, "owner"), (seats["oleg"].id, "paid"), (seats["guest"].id, "guest"),
    }


def test_only_the_owner_of_an_open_bill_sends_reminders(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)

    assert _remind(client, bill, seats["oleg"].id, actor=DANA).status_code == 403

    stored = session.get(Bill, bill["id"])
    stored.status = "closed"
    session.add(stored)
    session.commit()
    assert _remind(client, bill, seats["dana"].id).status_code == 409


def test_a_blocked_bot_hands_the_reminder_to_the_next_account_that_can_send(
    client: TestClient, session: Session, telegram, monkeypatch
):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split.test")
    bill, seats = _table(client, session, telegram)
    telegram["bot_blocked"].add(DANA)
    limited = _account(session, 1)
    working = _account(session, 2)
    telegram["accounts"]["session-1"] = sender_telegram.AccountTrouble("Flood wait 30 s", rest_seconds=30)
    now = datetime(2026, 10, 1, 12, 0)

    _remind(client, bill, seats["dana"].id)
    _deliver(session, now)

    assert telegram["account_sends"] == [
        ("session-1", "PREPARED-501", "dana"),
        ("session-2", "PREPARED-502", "dana"),
    ]
    reminder = _latest(session, seats["dana"])
    assert (reminder.status, reminder.channel, reminder.sender_account_id) == ("sent", "account", working.id)
    session.refresh(limited)
    session.refresh(working)
    assert (limited.status, limited.rest_until) == (SenderAccountStatus.RESTING, now + timedelta(seconds=30))
    # The bot bounced: until Dana lets it write again, her taps lead to its chat.
    assert session.exec(select(User).where(User.telegram_id == DANA)).one().settings["bot_blocked"] is True
    assert (working.status, working.sent_count) == (SenderAccountStatus.ACTIVE, 1)
    # The account waits for the bill's picture: the post shows it above the text.
    assert all(url.startswith("https://split.test/api/bills/public/") for url in telegram["previews"])
    # Prepared twice, tracked once: the post that went out is kept current.
    assert len(session.exec(select(SharedBillMessage).where(SharedBillMessage.language == "ru")).all()) == 2


def test_an_account_that_just_wrote_waits_a_minute_before_the_next_stranger(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    telegram["bot_blocked"].add(DANA)
    now = datetime(2026, 10, 1, 12, 0)
    _account(session, 1, last_used_at=now - timedelta(seconds=10))

    _remind(client, bill, seats["dana"].id)
    _deliver(session, now)

    assert telegram["account_sends"] == []
    assert _latest(session, seats["dana"]).status == "pending"
    _deliver(session, now + timedelta(seconds=30))
    _deliver(session, now + timedelta(minutes=1))
    assert [send[0] for send in telegram["account_sends"]] == ["session-1"]
    assert _latest(session, seats["dana"]).status == "sent"
    # The bot bounced once; while the reminder waited it was not asked again.
    assert telegram["bot_tries"] == [DANA]


def test_someone_without_a_username_cannot_be_reached_past_a_blocked_bot(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    telegram["bot_blocked"].add(OLEG)
    _account(session, 1)

    _remind(client, bill, seats["oleg"].id)
    _deliver(session)

    assert telegram["account_sends"] == []
    reminder = _latest(session, seats["oleg"])
    assert (reminder.status, reminder.failure) == ("failed", "unreachable")
    # Trying again within the hour would only cost an account.
    assert _remind(client, bill, seats["oleg"].id).json()["skipped"][0]["reason"] == "cooldown"


def test_a_person_no_account_can_write_to_stops_the_chain(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    telegram["bot_blocked"].add(DANA)
    _account(session, 1)
    _account(session, 2)
    telegram["accounts"]["session-1"] = sender_telegram.RecipientUnreachable("UserPrivacyRestrictedError")

    _remind(client, bill, seats["dana"].id)
    _deliver(session)

    assert [send[0] for send in telegram["account_sends"]] == ["session-1"]
    assert _latest(session, seats["dana"]).failure == "unreachable"


def test_when_every_account_is_spent_the_reminder_says_so(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    telegram["bot_blocked"].add(DANA)
    banned = _account(session, 1)
    _account(session, 2, status=SenderAccountStatus.DISABLED)
    telegram["accounts"]["session-1"] = sender_telegram.AccountTrouble("UserDeactivatedBanError", banned=True)

    _remind(client, bill, seats["dana"].id)
    _deliver(session)

    reminder = _latest(session, seats["dana"])
    assert (reminder.status, reminder.failure) == ("failed", "no_senders")
    session.refresh(banned)
    assert banned.status == SenderAccountStatus.BANNED
    # Nothing was wrong with Dana: she can be tried again once there are accounts.
    assert _remind(client, bill, seats["dana"].id).json()["queued"] == 1


def test_a_share_paid_before_the_reminder_went_out_is_left_alone(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    _remind(client, bill, seats["dana"].id)
    seat = session.get(BillUser, seats["dana"].id)
    seat.is_paid = True
    session.add(seat)
    session.commit()

    _deliver(session)

    assert telegram["bot_sent"] == []
    assert _latest(session, seats["dana"]).failure == "settled"


def test_what_the_owner_is_owed_and_a_reminder_to_all_of_it(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    owner_id = session.exec(select(User).where(User.telegram_id == OWNER)).one().id
    client.act_as(OWNER)

    owed = client.get(f"/users/{owner_id}/owed").json()
    assert owed == {
        "totals": [{"currency": "uzs", "amount": 90000.0}], "people": 3, "bills": 1, "remindable": 2,
        "next_reminder_at": None, "why_nobody": None,
    }

    sent = client.post(f"/users/{owner_id}/owed/reminders").json()
    assert sent["queued"] == 2
    after = client.get(f"/users/{owner_id}/owed").json()
    assert after["remindable"] == 0
    # The reminders just asked for hold everyone for the hour; the app counts down to its end.
    wait = datetime.fromisoformat(after["next_reminder_at"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=59) < wait <= timedelta(hours=1)

    demo = session.get(Bill, bill["id"])
    demo.is_demo = True
    session.add(demo)
    session.commit()
    assert client.get(f"/users/{owner_id}/owed").json() == {
        "totals": [], "people": 0, "bills": 0, "remindable": 0, "next_reminder_at": None, "why_nobody": "no_bills",
    }
    client.act_as(None)


def test_with_nobody_to_remind_the_owner_is_told_why(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    owner_id = session.exec(select(User).where(User.telegram_id == OWNER)).one().id
    client.act_as(OWNER)

    def paid(*names: str) -> None:
        for name in names:
            seat = session.get(BillUser, seats[name].id)
            seat.is_paid = True
            session.add(seat)
        session.commit()

    paid("dana", "oleg")
    assert client.get(f"/users/{owner_id}/owed").json()["why_nobody"] == "guests"
    paid("guest")
    assert client.get(f"/users/{owner_id}/owed").json()["why_nobody"] == "all_paid"
    client.act_as(None)


def test_why_nobody_names_the_first_thing_to_do():
    bill = Bill(id=1, owner_id=10, title="Ужин")

    def why(*seats: BillUser):
        return ReminderService.why_nobody([bill], {bill.id: [BillUser(bill_id=1, user_id=10), *seats]})

    joined, guest = dict(bill_id=1, user_id=20), dict(bill_id=1, user_id=None)
    assert ReminderService.why_nobody([], {}) is WhyNobody.NO_BILLS
    assert why() is WhyNobody.NO_PEOPLE
    # Someone who joined owes nothing yet: their dishes come before the guests.
    assert why(BillUser(**joined), BillUser(**guest, allocated_amount=300)) is WhyNobody.UNASSIGNED
    assert why(BillUser(**joined, is_paid=True), BillUser(**guest, allocated_amount=300)) is WhyNobody.GUESTS
    assert why(BillUser(**guest)) is WhyNobody.UNASSIGNED
    assert why(BillUser(**joined, allocated_amount=500, is_paid=True)) is WhyNobody.ALL_PAID


def test_a_broken_reminder_does_not_hold_up_the_rest(client: TestClient, session: Session, telegram, monkeypatch):
    bill, seats = _table(client, session, telegram)
    _remind(client, bill)
    calls = []

    def flaky_send(chat_id, text, markup, **kwargs):
        calls.append(chat_id)
        if len(calls) == 1:
            raise KeyError("a bug")
        return {"message_id": 1}

    monkeypatch.setattr(shared, "send_message", flaky_send)
    _deliver(session)

    statuses = sorted(r.status for r in session.exec(select(ManualReminder)).all())
    assert statuses == ["failed", "sent"]


def _without_pro(session: Session) -> User:
    owner = session.exec(select(User).where(User.telegram_id == OWNER)).one()
    session.delete(session.exec(select(ProGrant).where(ProGrant.user_id == owner.id)).one())
    session.commit()
    return owner


def _left(client: TestClient, owner: User) -> int | None:
    client.act_as(OWNER)
    try:
        return client.get(f"/users/{owner.id}/pro").json()["reminders_left_this_month"]
    finally:
        client.act_as(None)


def test_one_person_reminded_by_hand_is_pro(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    _without_pro(session)

    answer = _remind(client, bill, seats["dana"].id)

    assert (answer.status_code, answer.json()["detail"]) == (402, {"code": "PRO_REQUIRED", "feature": "reminders"})
    assert session.exec(select(ManualReminder)).all() == []


def test_remind_everyone_comes_free_three_times_a_month(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    owner = _without_pro(session)
    assert _left(client, owner) == 3

    for left in (2, 1, 0):
        assert _remind(client, bill).json()["queued"] == 2
        assert _left(client, owner) == left
        # Time passes: everyone may be reminded again.
        for reminder in session.exec(select(ManualReminder)).all():
            session.delete(reminder)
        session.commit()

    client.act_as(OWNER)
    owed = client.post(f"/users/{owner.id}/owed/reminders")
    client.act_as(None)
    refused = _remind(client, bill)
    assert (refused.status_code, refused.json()["detail"]) == (402, {"code": "PRO_REQUIRED", "feature": "reminders"})
    assert owed.status_code == 402
    assert session.exec(select(ManualReminder)).all() == []

    # Last month's presses are last month's.
    for used in session.exec(select(FreeReminderUse)).all():
        used.created_at -= timedelta(days=40)
        session.add(used)
    session.commit()
    assert _left(client, owner) == 3


def test_a_free_press_that_reminds_nobody_costs_nothing(client: TestClient, session: Session, telegram):
    bill, _seats = _table(client, session, telegram)
    owner = _without_pro(session)
    _remind(client, bill)

    again = _remind(client, bill)

    assert again.json()["queued"] == 0
    assert _left(client, owner) == 2


def test_with_pro_there_is_nothing_to_count(client: TestClient, session: Session, telegram):
    bill, _seats = _table(client, session, telegram)
    owner = session.exec(select(User).where(User.telegram_id == OWNER)).one()

    _remind(client, bill)

    assert _left(client, owner) is None
    assert session.exec(select(FreeReminderUse)).all() == []


def test_a_reminder_lost_with_its_job_is_replaced_not_sent_twice(client: TestClient, session: Session, telegram):
    bill, seats = _table(client, session, telegram)
    _remind(client, bill, seats["dana"].id)
    lost = _latest(session, seats["dana"])
    lost.created_at -= timedelta(minutes=61)
    session.add(lost)
    session.commit()

    assert _remind(client, bill, seats["dana"].id).json()["queued"] == 1
    _deliver(session)

    assert telegram["bot_sent"] == [DANA]
    session.refresh(lost)
    assert (lost.status, lost.failure) == ("failed", "error")
    assert _latest(session, seats["dana"]).status == "sent"


def test_a_reminder_replaced_while_the_job_held_it_is_not_sent(client: TestClient, session: Session, telegram):
    from app.services.reminder_service import ReminderService

    bill, seats = _table(client, session, telegram)
    _remind(client, bill, seats["dana"].id)
    service = ReminderService(session)
    [taken] = service.pending()
    with Session(session.get_bind()) as elsewhere:
        replaced = elsewhere.get(ManualReminder, taken.id)
        replaced.status = "failed"
        elsewhere.add(replaced)
        elsewhere.commit()

    service.deliver(taken, datetime.utcnow())

    assert telegram["bot_sent"] == []


def test_i_have_paid_in_an_old_reminder_does_not_seat_someone_taken_off_the_bill(
    client: TestClient, session: Session, telegram, monkeypatch
):
    bill, seats = _table(client, session, telegram)
    _remind(client, bill, seats["dana"].id)
    _deliver(session)
    code = session.exec(select(Invite).where(Invite.channel == InviteChannel.REMINDER)).one().code
    owner = session.exec(select(User).where(User.telegram_id == OWNER)).one()
    client.act_as(OWNER)
    client.request("DELETE", f"/bills/{bill['id']}/participants/{seats['dana'].id}", json={"user_id": owner.id})
    client.act_as(None)
    alerts = []
    monkeypatch.setattr(shared, "answer_callback_query", lambda callback_id, text, **kwargs: alerts.append(text))

    client.post("/telegram/webhook", json={"update_id": next_update_id(), "callback_query": {
        "id": "cb", "data": f"share_paid:{code}", "chat_instance": "1", "message": {"message_id": 1, "chat": {"id": DANA}},
        "from": {"id": DANA, "first_name": "Dana", "username": "dana", "language_code": "en"},
    }})

    assert alerts == ["You are no longer on this bill"]
    session.expire_all()
    seat = session.get(BillUser, seats["dana"].id)
    assert (seat.user_id, seat.is_paid) == (None, False)
