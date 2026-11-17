from fastapi import HTTPException

from app.models import PaymentMethod
from app.repositories.payment_method_repo import PaymentMethodRepository
from app.repositories.user_repo import UserRepository
from app.schemas.payment_method_schemas import (
    PaymentMethodCreate,
    PaymentMethodResponse,
)
from app.services.payment_link import find_saved_method
from app.utils import crypto


class PaymentMethodService:
    def __init__(self, repo: PaymentMethodRepository, user_repo: UserRepository):
        self.repo = repo
        self.user_repo = user_repo

    def _ensure_user(self, user_id: int) -> None:
        if not self.user_repo.get_by_id(user_id):
            raise HTTPException(status_code=404, detail="User not found")

    def list_for_user(self, user_id: int) -> list[PaymentMethodResponse]:
        self._ensure_user(user_id)
        return [self._to_response(m) for m in self.repo.list_by_user(user_id)]

    def create(self, user_id: int, data: PaymentMethodCreate) -> PaymentMethodResponse:
        self._ensure_user(user_id)
        value = (data.value or "").strip()
        if not value:
            raise HTTPException(status_code=400, detail="Payment value is required")
        # Saving a card that is already saved hands back the one there is —
        # putting a card on a bill saves it too, and the two can cross.
        existing = find_saved_method(self.repo.session, user_id, value)
        if existing is not None:
            return self._to_response(existing)
        method = PaymentMethod(
            user_id=user_id,
            label=(data.label or None),
            enc_value=crypto.encrypt(value),
        )
        return self._to_response(self.repo.create(method))

    def delete(self, user_id: int, method_id: int) -> None:
        """Take a card out of the picker.

        Bills point at this row, so erasing it either trips the foreign key or
        strips the card off bills that were already paid with it. Hiding keeps
        both the history and the user's expectation.
        """
        method = self.repo.get_by_id(method_id)
        if not method or method.user_id != user_id or method.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Payment method not found")
        self.repo.hide(method)

    @staticmethod
    def _to_response(method: PaymentMethod) -> PaymentMethodResponse:
        return PaymentMethodResponse(
            id=method.id,
            label=method.label,
            value=crypto.decrypt(method.enc_value),
        )
