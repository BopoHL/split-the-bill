from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.database import get_session
from app.repositories.payment_method_repo import PaymentMethodRepository
from app.repositories.user_repo import UserRepository
from app.services.payment_method_service import PaymentMethodService
from app.dependencies import ensure_self, get_authenticated_user
from app.models import User
from app.schemas.payment_method_schemas import (
    PaymentMethodCreate,
    PaymentMethodResponse,
)

router = APIRouter(
    prefix="/users/{user_id}/payment-methods",
    tags=["payment-methods"],
    dependencies=[Depends(get_authenticated_user)],
)


def get_payment_method_service(
    session: Session = Depends(get_session),
) -> PaymentMethodService:
    return PaymentMethodService(
        PaymentMethodRepository(session), UserRepository(session)
    )


@router.get("/", response_model=list[PaymentMethodResponse])
def list_payment_methods(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: PaymentMethodService = Depends(get_payment_method_service),
):
    ensure_self(current_user, user_id)
    return service.list_for_user(user_id)


@router.post("/", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
def create_payment_method(
    user_id: int,
    data: PaymentMethodCreate,
    current_user: User = Depends(get_authenticated_user),
    service: PaymentMethodService = Depends(get_payment_method_service),
):
    ensure_self(current_user, user_id)
    return service.create(user_id, data)


@router.delete("/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_payment_method(
    user_id: int,
    method_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: PaymentMethodService = Depends(get_payment_method_service),
):
    ensure_self(current_user, user_id)
    service.delete(user_id, method_id)
