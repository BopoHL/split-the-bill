"""The accounts that deliver reminders the bot cannot, as the operator keeps them.

Logging one in takes three requests — the number, then the code Telegram sends
to it, then the two-step password if there is one — so the half-made login is
kept on the row between them. From then on the row is the account's health: in
use, resting after Telegram held it back, or banned for good.
"""
import asyncio
import re
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from sqlmodel import Session, func, or_, select
from telethon.errors import RPCError

from app.models import ManualReminder, SenderAccount, SenderAccountStatus
from app.services import sender_telegram
from app.utils import crypto

# Telegram shuts out accounts that write to strangers in a burst: each account
# waits a minute between sends and stops for the day after a day's share.
SEND_GAP = timedelta(minutes=1)
SENDS_PER_DAY = 20


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        raise HTTPException(status_code=422, detail="Enter the number with its country code")
    return f"+{digits}"


class SenderAccountService:
    def __init__(self, session: Session):
        self.session = session

    def accounts(self) -> list[SenderAccount]:
        return list(self.session.exec(select(SenderAccount).order_by(SenderAccount.id)).all())

    def get(self, account_id: int) -> SenderAccount:
        account = self.session.get(SenderAccount, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        return account

    def is_sender(self, telegram_id: int | None) -> bool:
        if not telegram_id:
            return False
        return self.session.exec(
            select(SenderAccount.id).where(SenderAccount.telegram_id == telegram_id)
        ).first() is not None

    # ── Logging in ───────────────────────────────────────────────────────────

    def start_login(self, phone: str) -> SenderAccount:
        self._require_configured()
        phone = normalize_phone(phone)
        account = self.session.exec(select(SenderAccount).where(SenderAccount.phone == phone)).first()
        if account and account.status in (SenderAccountStatus.ACTIVE, SenderAccountStatus.RESTING):
            raise HTTPException(status_code=409, detail="This account is already logged in")
        sent = self._telegram(lambda: sender_telegram.send_code(phone))
        account = account or SenderAccount(phone=phone)
        account.session_enc = crypto.encrypt(sent.session)
        account.phone_code_hash = sent.phone_code_hash
        account.status = SenderAccountStatus.AWAITING_CODE
        account.last_error = None
        return self._save(account)

    def submit_code(self, account_id: int, code: str) -> SenderAccount:
        account = self._in_login(account_id, SenderAccountStatus.AWAITING_CODE)
        session = crypto.decrypt(account.session_enc)
        try:
            logged_in = self._telegram(
                lambda: sender_telegram.sign_in_with_code(session, account.phone, code.strip(), account.phone_code_hash)
            )
        except sender_telegram.PasswordNeeded:
            account.status = SenderAccountStatus.AWAITING_PASSWORD
            return self._save(account)
        return self._logged_in(account, logged_in)

    def submit_password(self, account_id: int, password: str) -> SenderAccount:
        account = self._in_login(account_id, SenderAccountStatus.AWAITING_PASSWORD)
        session = crypto.decrypt(account.session_enc)
        logged_in = self._telegram(lambda: sender_telegram.sign_in_with_password(session, password))
        return self._logged_in(account, logged_in)

    def _logged_in(self, account: SenderAccount, logged_in: sender_telegram.LoggedIn) -> SenderAccount:
        account.session_enc = crypto.encrypt(logged_in.session)
        account.phone_code_hash = None
        account.telegram_id = logged_in.telegram_id
        account.username = logged_in.username
        account.display_name = logged_in.display_name
        account.status = SenderAccountStatus.ACTIVE
        account.rest_until = None
        account.last_error = None
        return self._save(account)

    def _in_login(self, account_id: int, step: SenderAccountStatus) -> SenderAccount:
        account = self.get(account_id)
        if account.status != step or not account.session_enc:
            raise HTTPException(status_code=409, detail="Start the login again")
        return account

    # ── Operating ────────────────────────────────────────────────────────────

    def login_code(self, account_id: int) -> sender_telegram.LoginCode | None:
        self._require_configured()
        account = self.get(account_id)
        if not account.telegram_id or not account.session_enc or account.status not in (
            SenderAccountStatus.ACTIVE, SenderAccountStatus.RESTING, SenderAccountStatus.DISABLED,
        ):
            raise HTTPException(status_code=409, detail="Для чтения кода нужна действующая сессия аккаунта")
        try:
            session = crypto.decrypt(account.session_enc)
        except (InvalidTag, ValueError) as error:
            raise HTTPException(status_code=409, detail="Не удалось прочитать сохранённую сессию аккаунта") from error
        try:
            return sender_telegram.read_login_code(session, account.telegram_id)
        except sender_telegram.AccountTrouble as error:
            raise HTTPException(status_code=409 if error.banned else 503, detail=str(error)) from error

    def set_enabled(self, account_id: int, enabled: bool) -> SenderAccount:
        account = self.get(account_id)
        if account.telegram_id is None:
            raise HTTPException(status_code=409, detail="Finish logging in first")
        if enabled and account.status == SenderAccountStatus.BANNED:
            raise HTTPException(status_code=409, detail="Telegram banned this account")
        account.status = SenderAccountStatus.ACTIVE if enabled else SenderAccountStatus.DISABLED
        account.rest_until = None
        return self._save(account)

    def remove(self, account_id: int) -> None:
        account = self.get(account_id)
        if account.session_enc and account.telegram_id and sender_telegram.is_configured():
            sender_telegram.log_out(crypto.decrypt(account.session_enc))
        self.session.delete(account)
        self.session.commit()

    def available(self, now: datetime) -> list[SenderAccount]:
        """The accounts to try, least recently used first, so the sending
        spreads across them instead of wearing out the first one."""
        accounts = self.session.exec(
            select(SenderAccount).where(
                or_(
                    SenderAccount.status == SenderAccountStatus.ACTIVE,
                    (SenderAccount.status == SenderAccountStatus.RESTING) & (SenderAccount.rest_until <= now),
                )
            )
        ).all()
        sent_today = dict(self.session.exec(
            select(ManualReminder.sender_account_id, func.count())
            .where(ManualReminder.sent_at >= now - timedelta(days=1), ManualReminder.sender_account_id.is_not(None))
            .group_by(ManualReminder.sender_account_id)
        ).all())
        accounts = [account for account in accounts if sent_today.get(account.id, 0) < SENDS_PER_DAY]
        return sorted(accounts, key=lambda account: (account.last_used_at or datetime.min, account.id))

    @staticmethod
    def catching_breath(account: SenderAccount, now: datetime) -> bool:
        """Sent a moment ago: it waits before writing to the next stranger."""
        return account.last_used_at is not None and now - account.last_used_at < SEND_GAP

    def record_sent(self, account: SenderAccount, now: datetime) -> None:
        account.status = SenderAccountStatus.ACTIVE
        account.rest_until = None
        account.last_used_at = now
        account.sent_count += 1
        self._save(account)

    def record_trouble(self, account: SenderAccount, trouble: sender_telegram.AccountTrouble, now: datetime) -> None:
        account.last_error = str(trouble)
        account.last_used_at = now
        if trouble.banned:
            account.status = SenderAccountStatus.BANNED
            account.rest_until = None
        elif trouble.rest_seconds:
            account.status = SenderAccountStatus.RESTING
            account.rest_until = now + timedelta(seconds=trouble.rest_seconds)
        self._save(account)

    def session_of(self, account: SenderAccount) -> str:
        try:
            return crypto.decrypt(account.session_enc)
        except (InvalidTag, ValueError) as error:
            # Saved under another key: unusable until it is logged in again.
            raise sender_telegram.AccountTrouble("The saved login cannot be read", banned=True) from error

    def _save(self, account: SenderAccount) -> SenderAccount:
        self.session.add(account)
        self.session.commit()
        self.session.refresh(account)
        return account

    @staticmethod
    def _require_configured() -> None:
        if not sender_telegram.is_configured():
            raise HTTPException(status_code=503, detail="TG_API_ID and TG_API_HASH are not configured")

    @staticmethod
    def _telegram(call):
        try:
            return call()
        except sender_telegram.LoginRefused as refusal:
            raise HTTPException(status_code=422, detail=str(refusal)) from refusal
        except (OSError, ConnectionError, asyncio.TimeoutError) as error:
            raise HTTPException(status_code=502, detail="Could not reach Telegram") from error
        except RPCError as error:
            raise HTTPException(status_code=422, detail=f"Telegram: {error.message}") from error
