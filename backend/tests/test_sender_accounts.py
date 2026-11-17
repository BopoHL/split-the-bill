"""Accounts that deliver reminders the bot cannot: logged in from the admin
panel in three steps, and kept or set aside as Telegram treats them.

Telethon itself is stubbed; what is tested is the login state machine, the
rotation, and how Telegram's refusals are read."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from telethon import errors
from telethon.tl.types import Message, MessageEntityBold, MessageMediaWebPage, PeerUser, WebPage, WebPagePending

import app.services.bot_flow_service as flow
from app.models import SenderAccount, SenderAccountStatus, User
from app.services import sender_telegram
from app.services.sender_accounts import SenderAccountService
from app.utils import crypto
from tests.telegram_world import next_update_id


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    monkeypatch.setenv("TG_API_ID", "12345")
    monkeypatch.setenv("TG_API_HASH", "hash")
    from app.routers import admin

    admin._LOGIN_ATTEMPTS.clear()


@pytest.fixture
def telegram(monkeypatch):
    """Telegram's side of logging in, as a script the test sets up."""
    calls: dict[str, list] = {"send_code": [], "code": [], "password": [], "log_out": []}
    script: dict = {"code": "logged_in", "password": "logged_in"}

    def send_code(phone):
        calls["send_code"].append(phone)
        return sender_telegram.CodeSent(session="half-made", phone_code_hash="hash-1")

    def logged_in():
        return sender_telegram.LoggedIn(session="whole", telegram_id=777, username="sender_one", display_name="Sender One")

    def sign_in_with_code(session, phone, code, phone_code_hash):
        calls["code"].append((session, phone, code, phone_code_hash))
        if script["code"] == "password":
            raise sender_telegram.PasswordNeeded()
        if script["code"] == "wrong":
            raise sender_telegram.LoginRefused("Wrong code")
        return logged_in()

    def sign_in_with_password(session, password):
        calls["password"].append((session, password))
        if script["password"] == "wrong":
            raise sender_telegram.LoginRefused("Wrong password")
        return logged_in()

    monkeypatch.setattr(sender_telegram, "send_code", send_code)
    monkeypatch.setattr(sender_telegram, "sign_in_with_code", sign_in_with_code)
    monkeypatch.setattr(sender_telegram, "sign_in_with_password", sign_in_with_password)
    monkeypatch.setattr(sender_telegram, "log_out", lambda session: calls["log_out"].append(session))
    return {"calls": calls, "script": script}


def _login(client: TestClient) -> None:
    assert client.post(
        "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
    ).status_code == 200


def test_an_account_logs_in_with_the_code_telegram_sends(client: TestClient, session: Session, telegram):
    _login(client)

    started = client.post("/admin/senders", json={"phone": "+998 90 123-45-67"})
    assert started.status_code == 200
    assert started.json()["status"] == "awaiting_code"
    assert telegram["calls"]["send_code"] == ["+998901234567"]

    account = session.get(SenderAccount, started.json()["id"])
    assert account.session_enc != "half-made" and crypto.decrypt(account.session_enc) == "half-made"

    done = client.post(f"/admin/senders/{account.id}/code", json={"code": " 12345 "})
    assert done.status_code == 200
    body = done.json()
    assert body["status"] == "active"
    assert (body["telegram_id"], body["username"], body["display_name"]) == (777, "sender_one", "Sender One")
    assert telegram["calls"]["code"] == [("half-made", "+998901234567", "12345", "hash-1")]

    session.refresh(account)
    assert crypto.decrypt(account.session_enc) == "whole"
    assert account.phone_code_hash is None


def test_two_step_verification_asks_for_the_password_next(client: TestClient, telegram):
    _login(client)
    telegram["script"]["code"] = "password"
    account_id = client.post("/admin/senders", json={"phone": "+998901234567"}).json()["id"]

    assert client.post(f"/admin/senders/{account_id}/code", json={"code": "1"}).json()["status"] == "awaiting_password"

    telegram["script"]["password"] = "wrong"
    refused = client.post(f"/admin/senders/{account_id}/password", json={"password": "nope"})
    assert refused.status_code == 422 and refused.json()["detail"] == "Wrong password"

    telegram["script"]["password"] = "logged_in"
    assert client.post(f"/admin/senders/{account_id}/password", json={"password": "pw"}).json()["status"] == "active"
    assert telegram["calls"]["password"][-1] == ("half-made", "pw")


def test_a_wrong_code_is_said_and_the_login_waits(client: TestClient, telegram):
    _login(client)
    telegram["script"]["code"] = "wrong"
    account_id = client.post("/admin/senders", json={"phone": "+998901234567"}).json()["id"]

    refused = client.post(f"/admin/senders/{account_id}/code", json={"code": "1"})
    assert refused.status_code == 422 and refused.json()["detail"] == "Wrong code"
    assert client.get("/admin/senders").json()["accounts"][0]["status"] == "awaiting_code"
    # Skipping ahead is not a way in.
    assert client.post(f"/admin/senders/{account_id}/password", json={"password": "x"}).status_code == 409


def test_a_logged_in_number_is_not_logged_in_twice(client: TestClient, telegram):
    _login(client)
    account_id = client.post("/admin/senders", json={"phone": "+998901234567"}).json()["id"]
    client.post(f"/admin/senders/{account_id}/code", json={"code": "1"})

    assert client.post("/admin/senders", json={"phone": "998901234567"}).status_code == 409
    assert client.post("/admin/senders", json={"phone": "12"}).status_code == 422


def test_without_api_credentials_nothing_logs_in(client: TestClient, telegram, monkeypatch):
    _login(client)
    monkeypatch.delenv("TG_API_ID")

    assert client.get("/admin/senders").json() == {"configured": False, "accounts": []}
    assert client.post("/admin/senders", json={"phone": "+998901234567"}).status_code == 503


def test_the_panel_needs_the_admin(client: TestClient):
    assert client.get("/admin/senders").status_code == 401


def test_an_account_is_turned_off_and_on_and_removed_with_its_login(client: TestClient, telegram):
    _login(client)
    account_id = client.post("/admin/senders", json={"phone": "+998901234567"}).json()["id"]
    client.post(f"/admin/senders/{account_id}/code", json={"code": "1"})

    assert client.put(f"/admin/senders/{account_id}/enabled", json={"enabled": False}).json()["status"] == "disabled"
    assert client.put(f"/admin/senders/{account_id}/enabled", json={"enabled": True}).json()["status"] == "active"

    assert client.delete(f"/admin/senders/{account_id}").status_code == 204
    assert telegram["calls"]["log_out"] == ["whole"]
    assert client.get("/admin/senders").json()["accounts"] == []


def _active(session: Session, phone: str, **fields) -> SenderAccount:
    account = SenderAccount(
        phone=phone,
        session_enc=crypto.encrypt(f"session-{phone}"),
        telegram_id=int(phone[-4:]),
        status=fields.pop("status", SenderAccountStatus.ACTIVE),
        **fields,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def test_the_least_recently_used_account_goes_first_and_a_rested_one_comes_back(session: Session):
    now = datetime(2026, 10, 1, 12, 0)
    used = _active(session, "+10000001", last_used_at=now - timedelta(minutes=1))
    fresh = _active(session, "+10000002")
    _active(session, "+10000003", status=SenderAccountStatus.BANNED)
    _active(session, "+10000004", status=SenderAccountStatus.DISABLED)
    resting = _active(session, "+10000005", status=SenderAccountStatus.RESTING, rest_until=now + timedelta(hours=1))
    rested = _active(session, "+10000006", status=SenderAccountStatus.RESTING, rest_until=now - timedelta(seconds=1))

    available = SenderAccountService(session).available(now)

    assert [account.id for account in available] == [fresh.id, rested.id, used.id]
    assert resting.id not in [account.id for account in available]


def test_an_account_that_sent_its_share_for_the_day_rests_till_tomorrow(session: Session):
    from app.models import ManualReminder
    from app.services.sender_accounts import SENDS_PER_DAY

    now = datetime(2026, 10, 1, 12, 0)
    busy = _active(session, "+10000001")
    for minute in range(SENDS_PER_DAY):
        session.add(ManualReminder(
            bill_id=1, participant_id=1, requested_by_user_id=1, status="sent",
            sender_account_id=busy.id, sent_at=now - timedelta(hours=23) + timedelta(minutes=minute),
        ))
    session.commit()

    assert busy not in SenderAccountService(session).available(now)
    # The first of them is a day old an hour later.
    assert busy in SenderAccountService(session).available(now + timedelta(hours=1, seconds=1))


def _code_message(text="Login code: 12345. Do not share it.", **fields):
    return Message(
        id=1,
        peer_id=PeerUser(777000),
        from_id=PeerUser(fields.pop("sender_id", 777000)),
        message=text,
        date=fields.pop("date", datetime.now(timezone.utc)),
        **fields,
    )


def _code_client(monkeypatch, messages=(), *, authorized=True, telegram_id=1):
    client = SimpleNamespace(
        connect=AsyncMock(),
        disconnect=AsyncMock(),
        is_user_authorized=AsyncMock(return_value=authorized),
        get_me=AsyncMock(return_value=SimpleNamespace(id=telegram_id)),
        get_messages=AsyncMock(return_value=messages),
    )
    factory = lambda saved_session: client
    monkeypatch.setattr(sender_telegram, "_client", factory)
    return client


def test_a_login_code_is_admin_only_and_does_not_replace_the_saved_session(client, session, monkeypatch, caplog):
    account = _active(session, "+10000001")
    saved_session = account.session_enc
    connection = _code_client(monkeypatch, [_code_message()], telegram_id=account.telegram_id)
    url = f"/admin/senders/{account.id}/login-code"

    assert client.post(url).status_code == 401
    connection.connect.assert_not_called()
    _login(client)
    response = client.post(url)

    assert response.status_code == 200
    assert response.json()["code"] == "12345"
    assert response.json()["received_at"].endswith("Z")
    assert response.headers["Cache-Control"] == "no-store"
    connection.get_messages.assert_awaited_once_with(777000, limit=10)
    connection.disconnect.assert_awaited_once()
    session.refresh(account)
    assert (account.session_enc, account.status, account.sent_count) == (saved_session, "active", 0)
    assert "12345" not in caplog.text
    assert "code" not in client.get("/admin/senders").json()["accounts"][0]


@pytest.mark.parametrize("status", [SenderAccountStatus.RESTING, SenderAccountStatus.DISABLED])
def test_a_paused_sender_can_still_read_its_login_code(client, session, monkeypatch, status):
    account = _active(session, "+10000001", status=status)
    _code_client(monkeypatch, [_code_message()], telegram_id=account.telegram_id)
    _login(client)

    assert client.post(f"/admin/senders/{account.id}/login-code").json()["code"] == "12345"
    session.refresh(account)
    assert account.status == status


# Built when the test runs, not when pytest collects it: a code dated «a minute
# ahead» at collection was already in the past by the time a slow CI run got here.
@pytest.mark.parametrize("message", [
    lambda: _code_message(date=datetime.now(timezone.utc) - timedelta(minutes=6)),
    lambda: _code_message(date=datetime.now(timezone.utc) + timedelta(minutes=1)),
    lambda: _code_message(sender_id=123456),
    lambda: _code_message(out=True),
    lambda: _code_message(text="New login. Device ID 123456. Location: Tashkent."),
    lambda: _code_message(text="New login. Device ID 123456.", entities=[MessageEntityBold(offset=21, length=6)]),
])
def test_old_codes_and_messages_other_than_incoming_telegram_codes_are_ignored(monkeypatch, message):
    connection = _code_client(monkeypatch, [message()])

    assert sender_telegram.read_login_code("saved-session", 1) is None
    connection.disconnect.assert_awaited_once()


@pytest.mark.parametrize("message", [
    lambda: _code_message(text="Код для входа в Telegram: 54321. Никому не передавайте код."),
    lambda: _code_message(text="Ваш код подтверждения: 54321."),
    lambda: _code_message(text="Login code: 54321.", entities=[MessageEntityBold(offset=12, length=5)]),
])
def test_localized_telegram_codes_are_read_without_returning_the_message(monkeypatch, message):
    _code_client(monkeypatch, [message()])

    result = sender_telegram.read_login_code("saved-session", 1)

    assert result.code == "54321"
    assert "54321" not in repr(result)


def test_the_latest_service_code_is_used_even_if_another_notification_arrived_later(monkeypatch):
    _code_client(monkeypatch, [
        _code_message(text="New login from device 123456"),
        _code_message(text="Login code: 54321."),
        _code_message(),
    ])
    assert sender_telegram.read_login_code("saved-session", 1).code == "54321"


@pytest.mark.parametrize("authorized, telegram_id", [(False, 1), (True, 99)])
def test_an_invalid_or_wrong_account_session_is_not_used(client, session, monkeypatch, authorized, telegram_id):
    account = _active(session, "+10000001")
    connection = _code_client(monkeypatch, authorized=authorized, telegram_id=telegram_id)
    _login(client)

    assert client.post(f"/admin/senders/{account.id}/login-code").status_code == 409
    connection.get_messages.assert_not_called()
    connection.disconnect.assert_awaited_once()
    session.refresh(account)
    assert account.status == "active"


def test_empty_service_history_and_telegram_errors_are_handled(client, session, monkeypatch):
    account = _active(session, "+10000001")
    connection = _code_client(monkeypatch)
    _login(client)
    url = f"/admin/senders/{account.id}/login-code"

    assert client.post(url).json() == {"code": None, "received_at": None}
    connection.get_messages.side_effect = errors.FloodWaitError(request=None, capture=30)
    assert client.post(url).status_code == 503
    connection.get_messages.side_effect = errors.SessionRevokedError(request=None)
    assert client.post(url).status_code == 409


def test_a_slow_code_lookup_times_out_and_disconnects(monkeypatch):
    connection = _code_client(monkeypatch)

    async def waiting(*args, **kwargs):
        await asyncio.sleep(10)

    connection.get_messages.side_effect = waiting
    monkeypatch.setattr(sender_telegram, "LOGIN_CODE_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(sender_telegram.AccountTrouble, match="Не удалось получить код"):
        sender_telegram.read_login_code("saved-session", 1)
    connection.disconnect.assert_awaited_once()


def test_a_code_lookup_waits_for_no_other_connection_to_the_same_login(monkeypatch):
    entered, release = Event(), Event()
    sender = _FakeTelethon({"SplitTheBillsBot": 1, "dana": 4040})

    async def sending():
        entered.set()
        assert await asyncio.to_thread(release.wait, 3)

    sender.connect = sending
    calls = []

    def factory(saved_session):
        calls.append(saved_session)
        return sender

    monkeypatch.setattr(sender_telegram, "_client", factory)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(sender_telegram.send_prepared, "shared-login", "PREPARED", "dana", 4040)
        try:
            assert entered.wait(3)
            with pytest.raises(sender_telegram.AccountTrouble, match="сейчас занят"):
                sender_telegram.read_login_code("shared-login", 1)
            assert calls == ["shared-login"]
        finally:
            release.set()
        future.result(timeout=3)

    # The lock is released when delivery ends, so the same login is usable.
    connection = _code_client(monkeypatch)
    assert sender_telegram.read_login_code("shared-login", 1) is None
    connection.disconnect.assert_awaited_once()


def test_unfinished_logins_and_an_unreadable_session_cannot_read_codes(client, session, telegram, monkeypatch):
    _login(client)
    account_id = client.post("/admin/senders", json={"phone": "+998901234567"}).json()["id"]
    connection = _code_client(monkeypatch)
    assert client.post(f"/admin/senders/{account_id}/login-code").status_code == 409
    assert client.post("/admin/senders/999999/login-code").status_code == 404
    account = _active(session, "+10000001")
    account.session_enc = "unreadable"
    session.add(account)
    session.commit()

    assert client.post(f"/admin/senders/{account.id}/login-code").status_code == 409
    connection.connect.assert_not_called()


def test_trouble_rests_or_retires_an_account_and_a_send_brings_it_back(session: Session):
    now = datetime(2026, 10, 1, 12, 0)
    service = SenderAccountService(session)
    account = _active(session, "+10000001")

    service.record_trouble(account, sender_telegram.AccountTrouble("Flood wait 60 s", rest_seconds=60), now)
    assert (account.status, account.rest_until) == (SenderAccountStatus.RESTING, now + timedelta(seconds=60))

    service.record_sent(account, now)
    assert (account.status, account.rest_until, account.sent_count) == (SenderAccountStatus.ACTIVE, None, 1)

    service.record_trouble(account, sender_telegram.AccountTrouble("UserDeactivatedBanError", banned=True), now)
    assert account.status == SenderAccountStatus.BANNED
    assert account.last_error == "UserDeactivatedBanError"


@pytest.mark.parametrize(
    "error, outcome",
    [
        (errors.UserDeactivatedBanError(request=None), ("account", True, None)),
        (errors.AuthKeyUnregisteredError(request=None), ("account", True, None)),
        (errors.FloodWaitError(request=None, capture=42), ("account", False, 42)),
        (errors.PeerFloodError(request=None), ("account", False, sender_telegram.PEER_FLOOD_REST_SECONDS)),
        (errors.UserIsBlockedError(request=None), ("account", False, None)),
        (ConnectionError("reset"), ("account", False, sender_telegram.CONNECTION_REST_SECONDS)),
        (errors.UsernameNotOccupiedError(request=None), ("recipient",)),
        (errors.UserPrivacyRestrictedError(request=None), ("recipient",)),
        (ValueError('No user has "SplitTheBillsBot" as username'), ("account", False, None)),
    ],
)
def test_telegram_refusals_say_whether_the_next_account_may_try(error, outcome):
    read = sender_telegram.classify(error)
    if outcome[0] == "recipient":
        assert isinstance(read, sender_telegram.RecipientUnreachable)
    else:
        assert isinstance(read, sender_telegram.AccountTrouble)
        assert (read.banned, read.rest_seconds) == outcome[1:]


def test_the_bot_leaves_a_sender_account_s_start_alone(client: TestClient, session: Session, monkeypatch):
    sent: list = []
    monkeypatch.setattr(flow, "send_message", lambda *args, **kwargs: sent.append(args) or {"message_id": 1})
    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)
    _active(session, "+998900000777")

    update = {
        "update_id": next_update_id(),
        "message": {
            "message_id": 1,
            "text": "/start",
            "chat": {"id": 777, "type": "private"},
            "from": {"id": 777, "first_name": "Sender"},
        },
    }
    assert client.post("/telegram/webhook", json=update).status_code == 200

    assert sent == []
    assert session.exec(select(User).where(User.telegram_id == 777)).first() is None


class _FakeTelethon:
    """A logged-in account whose username lookups answer from a directory, and
    whose link previews are still being fetched for the first `pending` asks."""

    def __init__(self, directory: dict[str, int], pending: int = 0):
        self.directory = directory
        self.pending = pending
        self.previews_asked = 0
        self.sent = []

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def is_user_authorized(self):
        return True

    async def get_input_entity(self, username):
        if username not in self.directory:
            raise ValueError(f'No user has "{username}" as username')
        return SimpleNamespace(user_id=self.directory[username])

    async def __call__(self, request):
        kind = type(request).__name__
        if kind == "GetPreparedInlineMessageRequest":
            return SimpleNamespace(query_id=1, result=SimpleNamespace(id="result"))
        if kind == "GetWebPagePreviewRequest":
            self.previews_asked += 1
            page = WebPagePending(id=1, date=None) if self.previews_asked <= self.pending else _page(request.message)
            return SimpleNamespace(media=MessageMediaWebPage(webpage=page))
        self.sent.append((request.peer.user_id, self.previews_asked))
        ready = self.previews_asked > self.pending
        media = MessageMediaWebPage(webpage=_page("card") if ready else WebPagePending(id=1, date=None))
        return SimpleNamespace(updates=[SimpleNamespace(message=SimpleNamespace(media=media))])


def _page(url: str) -> WebPage:
    return WebPage(id=1, url=url, display_url=url, hash=0, attributes=[])


def test_a_username_someone_else_took_since_is_not_written_to(monkeypatch):
    account = _FakeTelethon({"SplitTheBillsBot": 1, "dana": 4040})
    monkeypatch.setattr(sender_telegram, "_client", lambda session: account)

    with pytest.raises(sender_telegram.RecipientUnreachable):
        sender_telegram.send_prepared("login", "PREPARED", "dana", recipient_telegram_id=101)
    sender_telegram.send_prepared("login", "PREPARED", "dana", recipient_telegram_id=4040)

    assert account.sent == [(4040, 0)]


def test_only_a_recipient_nobody_finds_stops_the_chain(monkeypatch):
    monkeypatch.setattr(sender_telegram, "_client", lambda session: _FakeTelethon({"SplitTheBillsBot": 1}))
    with pytest.raises(sender_telegram.RecipientUnreachable):
        sender_telegram.send_prepared("login", "PREPARED", "nobody", recipient_telegram_id=101)

    # This account cannot find the bot itself: the next account may still try.
    monkeypatch.setattr(sender_telegram, "_client", lambda session: _FakeTelethon({"dana": 4040}))
    with pytest.raises(sender_telegram.AccountTrouble):
        sender_telegram.send_prepared("login", "PREPARED", "dana", recipient_telegram_id=4040)


def test_a_reminder_waits_for_its_picture_before_it_goes_out(monkeypatch, caplog):
    account = _FakeTelethon({"SplitTheBillsBot": 1, "dana": 4040}, pending=2)
    monkeypatch.setattr(sender_telegram, "_client", lambda session: account)
    monkeypatch.setattr(sender_telegram, "PREVIEW_POLL_SECONDS", 0)

    sender_telegram.send_prepared("login", "PREPARED", "dana", 4040, preview_url="https://app/card.png")

    # Asked until Telegram had fetched it, then sent: the post carries the picture.
    assert account.sent == [(4040, 3)]
    assert "without its picture" not in caplog.text


def test_a_picture_that_never_comes_does_not_hold_the_reminder_back(monkeypatch, caplog):
    account = _FakeTelethon({"SplitTheBillsBot": 1, "dana": 4040}, pending=100)
    monkeypatch.setattr(sender_telegram, "_client", lambda session: account)
    monkeypatch.setattr(sender_telegram, "PREVIEW_WAIT_SECONDS", 0)

    sender_telegram.send_prepared("login", "PREPARED", "dana", 4040, preview_url="https://app/card.png")

    assert account.sent == [(4040, 1)]
    assert "was not ready" in caplog.text and "without its picture" in caplog.text


def test_a_login_that_can_no_longer_be_read_retires_the_account(session: Session):
    account = SenderAccount(phone="+998900000001", session_enc=crypto.encrypt("whole"), telegram_id=501,
                            status=SenderAccountStatus.ACTIVE)
    account.session_enc = account.session_enc[:-8] + "AAAAAAA="
    session.add(account)
    session.commit()

    with pytest.raises(sender_telegram.AccountTrouble) as trouble:
        SenderAccountService(session).session_of(account)

    assert trouble.value.banned is True
