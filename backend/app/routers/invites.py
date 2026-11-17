from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.dependencies import get_authenticated_user
from app.models import User
from app.repositories.bill_repo import BillRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.user_repo import UserRepository
from app.schemas.invite_schemas import InviteResolved
from app.services.invite_service import InviteService

router = APIRouter(prefix="/invites", tags=["invites"])


def get_invite_service(session: Session = Depends(get_session)) -> InviteService:
    return InviteService(
        InviteRepository(session), BillRepository(session), UserRepository(session)
    )


@router.get("/{code}", response_model=InviteResolved)
def resolve_invite(
    code: str,
    current_user: User = Depends(get_authenticated_user),
    service: InviteService = Depends(get_invite_service),
):
    """Where an invite leads, and who is behind it."""
    return service.resolve(code)
