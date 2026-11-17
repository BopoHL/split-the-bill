"""Linking bills to encrypted payment methods (STB-190).

A bill references a ``payment_methods`` row by id instead of storing the card
number in the clear. These helpers convert between the plaintext value the API
speaks and the stored, AES-GCM-encrypted method.
"""
from sqlmodel import Session, select

from app.models import PaymentMethod
from app.repositories.payment_method_repo import PaymentMethodRepository
from app.utils import crypto


def value_for_method(session: Session, method_id: int | None) -> str | None:
    """Decrypted payment value for a linked method, or None if absent/broken."""
    if not method_id:
        return None
    method = PaymentMethodRepository(session).get_by_id(method_id)
    if not method:
        return None
    try:
        return crypto.decrypt(method.enc_value)
    except Exception:
        return None


def values_for_methods(session: Session, method_ids: list[int]) -> dict[int, str]:
    """Decrypted values for a batch of methods, keyed by id.

    The bills list is deliberately assembled in one query; looking each card up
    per row would have quietly put the N+1 back.
    """
    wanted = {mid for mid in method_ids if mid}
    if not wanted:
        return {}

    methods = session.exec(
        select(PaymentMethod).where(PaymentMethod.id.in_(wanted))
    ).all()

    resolved: dict[int, str] = {}
    for method in methods:
        try:
            resolved[method.id] = crypto.decrypt(method.enc_value)
        except Exception:
            continue
    return resolved


def resolve_or_create_method_id(
    session: Session, owner_id: int, value: str | None
) -> int | None:
    """Map a plaintext payment value to one of the owner's stored methods,
    creating (and encrypting) a new one if none matches. Empty/None → None.

    Matching against the owner's existing methods keeps us from piling up a
    duplicate row every time the same card is reused (the picker may already
    have saved it)."""
    value = (value or "").strip()
    if not value:
        return None
    existing = find_saved_method(session, owner_id, value)
    if existing is not None:
        return existing.id
    repo = PaymentMethodRepository(session)
    created = repo.create(PaymentMethod(user_id=owner_id, enc_value=crypto.encrypt(value)))
    return created.id


def find_saved_method(session: Session, owner_id: int, value: str) -> PaymentMethod | None:
    """The owner's card in the picker with exactly these details, if any. The
    values are encrypted with a fresh nonce each, so they are compared
    decrypted."""
    for method in PaymentMethodRepository(session).list_by_user(owner_id):
        try:
            if crypto.decrypt(method.enc_value) == value:
                return method
        except Exception:
            pass
    return None
