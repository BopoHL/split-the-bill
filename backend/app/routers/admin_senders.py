"""The accounts that deliver reminders the bot cannot, from the admin panel."""
from fastapi import APIRouter, Depends, Response
from sqlmodel import Session

from app.database import get_session
from app.models import SenderAccount
from app.schemas.admin_schemas import (
    AdminSenderAccount,
    AdminSenderAccounts,
    AdminSenderCode,
    AdminSenderEnabled,
    AdminSenderLoginStart,
    AdminSenderLoginCode,
    AdminSenderPassword,
)
from app.services import sender_telegram
from app.services.sender_accounts import SenderAccountService
from app.utils.admin_auth import require_admin

router = APIRouter(prefix="/admin/senders", tags=["admin"], dependencies=[Depends(require_admin)])


def get_sender_accounts(session: Session = Depends(get_session)) -> SenderAccountService:
    return SenderAccountService(session)


def _row(account: SenderAccount) -> AdminSenderAccount:
    return AdminSenderAccount.model_validate(account, from_attributes=True)


@router.get("", response_model=AdminSenderAccounts)
def list_senders(service: SenderAccountService = Depends(get_sender_accounts)):
    return AdminSenderAccounts(
        configured=sender_telegram.is_configured(),
        accounts=[_row(account) for account in service.accounts()],
    )


@router.post("", response_model=AdminSenderAccount)
def start_login(payload: AdminSenderLoginStart, service: SenderAccountService = Depends(get_sender_accounts)):
    """Telegram sends a code to the number; it comes back in the next step."""
    return _row(service.start_login(payload.phone))


@router.post("/{account_id}/code", response_model=AdminSenderAccount)
def submit_code(
    account_id: int,
    payload: AdminSenderCode,
    service: SenderAccountService = Depends(get_sender_accounts),
):
    """Logged in — or awaiting_password when the account has two-step verification."""
    return _row(service.submit_code(account_id, payload.code))


@router.post("/{account_id}/login-code", response_model=AdminSenderLoginCode)
def read_login_code(
    account_id: int,
    response: Response,
    service: SenderAccountService = Depends(get_sender_accounts),
):
    """Only a recent Telegram service code, through the existing sender login."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    code = service.login_code(account_id)
    return AdminSenderLoginCode(code=code.code, received_at=code.received_at) if code else AdminSenderLoginCode()


@router.post("/{account_id}/password", response_model=AdminSenderAccount)
def submit_password(
    account_id: int,
    payload: AdminSenderPassword,
    service: SenderAccountService = Depends(get_sender_accounts),
):
    return _row(service.submit_password(account_id, payload.password))


@router.put("/{account_id}/enabled", response_model=AdminSenderAccount)
def set_enabled(
    account_id: int,
    payload: AdminSenderEnabled,
    service: SenderAccountService = Depends(get_sender_accounts),
):
    return _row(service.set_enabled(account_id, payload.enabled))


@router.delete("/{account_id}", status_code=204)
def remove(account_id: int, service: SenderAccountService = Depends(get_sender_accounts)):
    """Logs the account out of Telegram as well, then forgets it."""
    service.remove(account_id)
