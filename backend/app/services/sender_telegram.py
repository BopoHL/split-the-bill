"""Telegram as a sender account sees it, over MTProto.

The Bot API cannot write to someone who blocked the bot. A user account can,
as long as it can find the person — which takes a public username, or a chat
they already share. The message it sends is still the bot's own post: the bot
prepares it for the account (savePreparedInlineMessage) and the account sends
that, so the person gets the same picture and buttons, «via» the bot.

Everything that needs Telethon lives here, behind plain functions that run an
event loop of their own: the callers are sync request handlers and jobs.
"""
import asyncio
import hashlib
import logging
import os
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from weakref import WeakValueDictionary

from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.messages import (
    GetPreparedInlineMessageRequest,
    GetWebPagePreviewRequest,
    SendInlineBotResultRequest,
)
from telethon.tl.types import MessageMediaWebPage, WebPage, WebPagePending

from app.utils.telegram import bot_username

logger = logging.getLogger(__name__)

# How long an account rests when Telegram limits it without saying for how
# long: a spam limit is lifted in about a day, a dropped connection retried soon.
PEER_FLOOD_REST_SECONDS = 24 * 60 * 60
CONNECTION_REST_SECONDS = 5 * 60
CONNECT_TIMEOUT_SECONDS = 15
# Telegram fetches the picture a post links to in its own time, and a post sent
# before it has arrives without one: give it a few seconds to come.
PREVIEW_WAIT_SECONDS = 8
PREVIEW_POLL_SECONDS = 1
LOGIN_CODE_MAX_AGE = timedelta(minutes=5)
LOGIN_CODE_TIMEOUT_SECONDS = 25

_SESSION_LOCKS = WeakValueDictionary()
_SESSION_LOCKS_GUARD = Lock()


def _session_lock(session: str):
    """The API and scheduler share one backend process. Keep their connections
    to the same saved login sequential, without retaining its secret as a key."""
    fingerprint = hashlib.sha256(session.encode()).digest()
    with _SESSION_LOCKS_GUARD:
        lock = _SESSION_LOCKS.get(fingerprint)
        if lock is None:
            lock = Lock()
            _SESSION_LOCKS[fingerprint] = lock
        return lock


class MtprotoNotConfigured(RuntimeError):
    """TG_API_ID / TG_API_HASH are not set: no account can be used at all."""


def _credentials() -> tuple[int, str]:
    api_id, api_hash = os.getenv("TG_API_ID"), os.getenv("TG_API_HASH")
    if not api_id or not api_hash:
        raise MtprotoNotConfigured("TG_API_ID and TG_API_HASH are not configured")
    return int(api_id), api_hash


def is_configured() -> bool:
    try:
        _credentials()
    except MtprotoNotConfigured:
        return False
    return True


def _client(session: str = "") -> TelegramClient:
    api_id, api_hash = _credentials()
    # A flood wait is reported at once rather than slept through inside a job:
    # the account is rested and the next one tries.
    return TelegramClient(StringSession(session), api_id, api_hash, timeout=CONNECT_TIMEOUT_SECONDS, flood_sleep_threshold=0)


# ── Logging in ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CodeSent:
    session: str
    phone_code_hash: str


@dataclass(frozen=True)
class LoggedIn:
    session: str
    telegram_id: int
    username: str | None
    display_name: str


class PasswordNeeded(Exception):
    """The account has two-step verification on; its password comes next."""


class LoginRefused(Exception):
    """Telegram said no — a wrong code or password, an unknown number. The
    message is what to show the operator."""


def send_code(phone: str) -> CodeSent:
    async def run() -> CodeSent:
        client = _client()
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            return CodeSent(session=client.session.save(), phone_code_hash=sent.phone_code_hash)
        except (errors.PhoneNumberInvalidError, errors.PhoneNumberBannedError, errors.PhoneNumberFloodError) as error:
            raise LoginRefused(_login_message(error)) from error
        except errors.FloodWaitError as error:
            raise LoginRefused(f"Telegram asks to wait {error.seconds} s before the next code") from error
        finally:
            await client.disconnect()

    return asyncio.run(run())


def sign_in_with_code(session: str, phone: str, code: str, phone_code_hash: str) -> LoggedIn:
    async def run() -> LoggedIn:
        client = _client(session)
        await client.connect()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            return await _finish(client)
        except errors.SessionPasswordNeededError as error:
            raise PasswordNeeded() from error
        except (
            errors.PhoneCodeInvalidError,
            errors.PhoneCodeExpiredError,
            errors.PhoneNumberUnoccupiedError,
            errors.PhoneNumberBannedError,
        ) as error:
            raise LoginRefused(_login_message(error)) from error
        finally:
            await client.disconnect()

    return asyncio.run(run())


def sign_in_with_password(session: str, password: str) -> LoggedIn:
    async def run() -> LoggedIn:
        client = _client(session)
        await client.connect()
        try:
            await client.sign_in(password=password)
            return await _finish(client)
        except errors.PasswordHashInvalidError as error:
            raise LoginRefused("Wrong password") from error
        finally:
            await client.disconnect()

    return asyncio.run(run())


async def _finish(client: TelegramClient) -> LoggedIn:
    me = await client.get_me()
    # The bot can only prepare a message for someone it has met.
    await client.send_message(bot_username(), "/start")
    name = " ".join(part for part in (me.first_name, me.last_name) if part).strip()
    return LoggedIn(
        session=client.session.save(),
        telegram_id=me.id,
        username=me.username,
        display_name=name or me.username or str(me.id),
    )


def log_out(session: str) -> None:
    """End the login on Telegram's side too, so it leaves the account's list of
    sessions. Best effort: an account that is already gone has nothing to end."""

    async def run() -> None:
        client = _client(session)
        await client.connect()
        try:
            await client.log_out()
        finally:
            await client.disconnect()

    try:
        with _session_lock(session):
            asyncio.run(run())
    except (errors.RPCError, OSError, asyncio.TimeoutError, ConnectionError):
        pass


_LOGIN_MESSAGES = {
    errors.PhoneNumberInvalidError: "Telegram does not know this number",
    errors.PhoneNumberBannedError: "This number is banned in Telegram",
    errors.PhoneNumberFloodError: "Too many codes asked for this number; try later",
    errors.PhoneCodeInvalidError: "Wrong code",
    errors.PhoneCodeExpiredError: "The code has expired; start again",
    errors.PhoneNumberUnoccupiedError: "There is no Telegram account on this number",
}


def _login_message(error: Exception) -> str:
    return next((text for kind, text in _LOGIN_MESSAGES.items() if isinstance(error, kind)), str(error))


# Only Telegram's own incoming service messages may supply a login code.
_LOGIN_CODE_PATTERN = re.compile(
    r"(?:login code|код(?:\s+(?:для\s+входа(?:\s+в\s+Telegram)?|подтверждения))?)\s*:\s*([0-9]{5,8})(?![0-9])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LoginCode:
    code: str = field(repr=False)
    received_at: datetime


def _login_code_from(message, now: datetime) -> LoginCode | None:
    if message.out or message.sender_id != 777000 or not message.date:
        return None
    received_at = message.date.astimezone(timezone.utc)
    if not now - LOGIN_CODE_MAX_AGE <= received_at <= now:
        return None
    match = _LOGIN_CODE_PATTERN.search(message.raw_text or "")
    if match:
        return LoginCode(match.group(1), received_at)
    return None


def read_login_code(session: str, telegram_id: int) -> LoginCode | None:
    """Read a recent code through the existing login, without sending a new one
    or marking messages as read. Neither the login nor the code is persisted."""

    async def run() -> LoginCode | None:
        client = _client(session)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise AccountTrouble("Сессия Telegram больше не действительна", banned=True)
            me = await client.get_me()
            if not me or me.id != telegram_id:
                raise AccountTrouble("Сессия не соответствует этому аккаунту", banned=True)
            messages = await client.get_messages(777000, limit=10)
            now = datetime.now(timezone.utc)
            for message in messages:
                code = _login_code_from(message, now)
                if code:
                    return code
            return None
        finally:
            await client.disconnect()

    async def bounded() -> LoginCode | None:
        return await asyncio.wait_for(run(), LOGIN_CODE_TIMEOUT_SECONDS)

    lock = _session_lock(session)
    if not lock.acquire(blocking=False):
        raise AccountTrouble("Аккаунт сейчас занят. Повторите проверку через несколько секунд")
    try:
        return asyncio.run(bounded())
    except _BANNED as error:
        raise AccountTrouble("Сессия Telegram больше не действительна", banned=True) from error
    except errors.FloodWaitError as error:
        raise AccountTrouble(f"Telegram просит подождать {error.seconds} с перед повторной проверкой") from error
    except (errors.RPCError, OSError, asyncio.TimeoutError, ConnectionError, ValueError) as error:
        raise AccountTrouble("Не удалось получить код из Telegram. Попробуйте позже") from error
    finally:
        lock.release()


# ── Delivering ───────────────────────────────────────────────────────────────


class AccountTrouble(Exception):
    """This account could not send; the next one may. `banned` means it never
    will again; otherwise `rest_seconds` says how long to leave it alone (None:
    not at all — it was this one attempt)."""

    def __init__(self, reason: str, *, banned: bool = False, rest_seconds: int | None = None):
        super().__init__(reason)
        self.banned = banned
        self.rest_seconds = rest_seconds


class RecipientUnreachable(Exception):
    """No account can write to this person: they cannot be found by username, or
    their privacy settings keep strangers out. Trying the next account is futile."""


def send_prepared(
    session: str,
    prepared_message_id: str,
    recipient_username: str,
    recipient_telegram_id: int,
    preview_url: str | None = None,
) -> None:
    """Send the bot's prepared post to someone, as this account. The username is
    how a stranger is found; the id makes sure it is still the same person.
    `preview_url` is the picture the post shows above its text."""

    async def run() -> None:
        client = _client(session)
        await asyncio.wait_for(client.connect(), CONNECT_TIMEOUT_SECONDS)
        try:
            if not await client.is_user_authorized():
                raise AccountTrouble("The login is no longer valid", banned=True)
            bot = await client.get_input_entity(bot_username())
            prepared = await client(GetPreparedInlineMessageRequest(bot=bot, id=prepared_message_id))
            try:
                peer = await client.get_input_entity(recipient_username)
            except ValueError as error:
                # Nobody has that username.
                raise RecipientUnreachable(str(error)) from error
            if getattr(peer, "user_id", None) != recipient_telegram_id:
                # They changed their username and someone else has it now.
                raise RecipientUnreachable("The username belongs to someone else now")
            if preview_url and not await _preview_ready(client, preview_url):
                logger.warning("The picture %s was not ready when a reminder went out", preview_url)
            sent = await client(SendInlineBotResultRequest(
                peer=peer,
                query_id=prepared.query_id,
                id=prepared.result.id,
                random_id=random.getrandbits(63),
            ))
            if preview_url and not _shows_picture(sent):
                logger.warning("A reminder to user %s went out without its picture", recipient_telegram_id)
        finally:
            await client.disconnect()

    try:
        with _session_lock(session):
            asyncio.run(run())
    except (AccountTrouble, RecipientUnreachable):
        raise
    except Exception as error:  # noqa: BLE001 — every failure is sorted below
        raise classify(error) from error


async def _preview_ready(client: TelegramClient, url: str) -> bool:
    """Have Telegram fetch a post's picture before the post goes out. The app's
    share sheet gives it the time while the person picks a chat; an account
    sends at once."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PREVIEW_WAIT_SECONDS
    while True:
        preview = await client(GetWebPagePreviewRequest(message=url))
        page = getattr(preview.media, "webpage", None)
        if isinstance(page, WebPage):
            return True
        if not isinstance(page, WebPagePending) or loop.time() >= deadline:
            return False
        await asyncio.sleep(PREVIEW_POLL_SECONDS)


def _shows_picture(sent) -> bool:
    """Whether the message Telegram made carries the picture, as its answer says."""
    messages = [getattr(update, "message", None) for update in getattr(sent, "updates", [])]
    media = [message.media for message in messages if getattr(message, "media", None) is not None]
    return any(isinstance(item, MessageMediaWebPage) and isinstance(item.webpage, WebPage) for item in media)


_BANNED = (
    errors.AuthKeyUnregisteredError,
    errors.UserDeactivatedError,
    errors.UserDeactivatedBanError,
    errors.SessionRevokedError,
    errors.AuthKeyDuplicatedError,
    errors.PhoneNumberBannedError,
    errors.FrozenMethodInvalidError,
)
_UNREACHABLE = (
    errors.UsernameNotOccupiedError,
    errors.UsernameInvalidError,
    errors.UserPrivacyRestrictedError,
    errors.InputUserDeactivatedError,
)
# Refusals Telegram has no named error for in Telethon; they come by message.
_UNREACHABLE_MESSAGES = ("PRIVACY_PREMIUM_REQUIRED", "ALLOW_PAYMENT_REQUIRED")


def classify(error: Exception) -> AccountTrouble | RecipientUnreachable:
    """What a failed send means for the chain: move on to the next account (and
    how to treat this one), or stop — nobody can reach this person."""
    if isinstance(error, _BANNED):
        return AccountTrouble(type(error).__name__, banned=True)
    if isinstance(error, errors.FloodWaitError):
        return AccountTrouble(f"Flood wait {error.seconds} s", rest_seconds=error.seconds)
    if isinstance(error, errors.FloodError):
        return AccountTrouble(type(error).__name__, rest_seconds=getattr(error, "seconds", None) or CONNECTION_REST_SECONDS)
    if isinstance(error, errors.PeerFloodError):
        return AccountTrouble("Spam limit (PEER_FLOOD)", rest_seconds=PEER_FLOOD_REST_SECONDS)
    if isinstance(error, _UNREACHABLE):
        return RecipientUnreachable(type(error).__name__)
    if isinstance(error, errors.RPCError) and any(code in (error.message or "") for code in _UNREACHABLE_MESSAGES):
        return RecipientUnreachable(error.message)
    if isinstance(error, (OSError, ConnectionError, asyncio.TimeoutError)):
        return AccountTrouble(f"Connection failed: {error!r}", rest_seconds=CONNECTION_REST_SECONDS)
    if isinstance(error, MtprotoNotConfigured):
        return AccountTrouble(str(error))
    # Blocked by this very person, an expired prepared message, anything else:
    # this account, this time.
    return AccountTrouble(f"{type(error).__name__}: {error}")
