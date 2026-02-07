from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from app.database import get_session
from app.schemas.user_schemas import UserCreate, UserResponse
from app.schemas.bill_schemas import BillResponse
from app.repositories.user_repo import UserRepository
from app.services.user_service import UserService
from app.repositories.bill_repo import BillRepository
from app.services.bill_core_service import BillCoreService

router = APIRouter(prefix="/users", tags=["users"])

def get_user_service(session: Session = Depends(get_session)) -> UserService:
    user_repo = UserRepository(session)
    return UserService(user_repo)

def get_bill_core_service(session: Session = Depends(get_session)) -> BillCoreService:
    bill_repo = BillRepository(session)
    user_repo = UserRepository(session)
    return BillCoreService(bill_repo, user_repo)

@router.post("/", response_model=UserResponse)
def create_or_update_user(
    user_data: UserCreate, 
    user_service: UserService = Depends(get_user_service)
):
    """Create a new user or update existing one based on telegram_id"""
    return user_service.create_or_update_user(user_data)

@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int, 
    user_service: UserService = Depends(get_user_service)
):
    """Get user by ID"""
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/{user_id}/bills", response_model=list[BillResponse])
def get_user_bills(
    user_id: int, 
    page: int = 1,
    limit: int = 10,
    service: BillCoreService = Depends(get_bill_core_service)
):
    """Get all bills for a specific user (as owner or participant)"""
    offset = (page - 1) * limit
    return service.get_user_bills(user_id, offset=offset, limit=limit)
