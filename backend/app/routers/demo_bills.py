from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_authenticated_user
from app.models import User
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.schemas.bill_schemas import BillDetailResponse, DemoBillRequest
from app.services.demo_bill_service import DemoBillService

router = APIRouter(prefix="/demo-bills", tags=["demo-bills"])


def get_demo_bill_service(session: Session = Depends(get_session)) -> DemoBillService:
    return DemoBillService(BillRepository(session), UserRepository(session))


@router.post("/", response_model=BillDetailResponse, status_code=201)
def create_demo_bill(
    payload: DemoBillRequest,
    current_user: User = Depends(get_authenticated_user),
    service: DemoBillService = Depends(get_demo_bill_service),
):
    return service.create(current_user, payload.language, payload.payment_details)


@router.post("/{bill_id}/friends", response_model=BillDetailResponse)
def seat_demo_friends(
    bill_id: int,
    payload: DemoBillRequest,
    current_user: User = Depends(get_authenticated_user),
    service: DemoBillService = Depends(get_demo_bill_service),
):
    return service.seat_friends(bill_id, current_user.id, payload.language)


@router.delete("/{bill_id}", status_code=204)
def erase_demo_bill(
    bill_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: DemoBillService = Depends(get_demo_bill_service),
):
    service.erase(bill_id, current_user.id)
