import json
import os

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.models import User
from app.repositories.user_repo import UserRepository
from app.utils.auth import init_data_fields, verify_telegram_webapp_data

UNSIGNED_INIT_DATA_ENV = "ALLOW_UNSIGNED_INIT_DATA"


def unsigned_init_data_allowed() -> bool:
    """Whether unsigned init data is accepted.

    Off by default: the signature is what makes the caller's identity
    trustworthy. Local development with the browser mock opts in explicitly
    instead of relying on ENV not saying "production".
    """
    return os.getenv(UNSIGNED_INIT_DATA_ENV, "").strip().lower() in {"1", "true", "yes"}


def telegram_id_from_init_data(init_data: str | None) -> int:
    if not init_data:
        raise HTTPException(status_code=401, detail="Telegram authentication required")

    if not unsigned_init_data_allowed():
        token = os.getenv("TG_TOKEN")
        if not token:
            raise HTTPException(
                status_code=503, detail="Telegram authentication is not configured"
            )
        if not verify_telegram_webapp_data(init_data, token):
            raise HTTPException(status_code=401, detail="Invalid Telegram authentication")

    # Read from the same fields the signature was checked over: a second «user»
    # in front of the signed one was taken for the caller.
    fields = init_data_fields(init_data)
    try:
        return int(json.loads((fields or {})["user"])["id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid Telegram authentication")


def get_authenticated_user(
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the caller from signed Telegram WebApp data."""
    telegram_id = telegram_id_from_init_data(init_data)
    user = UserRepository(session).get_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(status_code=401, detail="Telegram user is not registered")
    return user


def get_optional_authenticated_user(
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    session: Session = Depends(get_session),
) -> User | None:
    """The caller when they are signed in, None when they are not.

    For routes that genuinely serve anonymous users but must not let a caller
    speak for somebody else.
    """
    if not init_data:
        return None
    return get_authenticated_user(init_data, session)


def ensure_self(caller: User, claimed_user_id: int | None) -> int:
    """Guard requests that still carry the actor's id in the payload.

    The id in the request is a claim; the signed header is the fact. They must
    agree, otherwise the caller is acting as somebody else.
    """
    if claimed_user_id is not None and claimed_user_id != caller.id:
        raise HTTPException(status_code=403, detail="Caller identity mismatch")
    return caller.id


def require_bill_owner(
    bill_id: int,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
) -> User:
    from app.repositories.bill_repo import BillRepository
    from app.services.validator import BillValidator

    validator = BillValidator(BillRepository(session))
    validator.ensure_owner(validator.get_bill_or_404(bill_id), current_user.id)
    return current_user


def require_bill_member(
    bill_id: int,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
) -> User:
    from app.repositories.bill_repo import BillRepository
    from app.services.validator import BillValidator

    repo = BillRepository(session)
    bill = BillValidator(repo).get_bill_or_404(bill_id)
    is_member = bill.owner_id == current_user.id or repo.get_participant_by_bill_and_user(
        bill_id, current_user.id
    )
    if not is_member:
        raise HTTPException(status_code=403, detail="Not authorized to view this bill")
    return current_user
