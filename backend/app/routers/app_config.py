from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.schemas.app_config_schemas import AppConfigResponse
from app.services.app_settings import get_support_username

router = APIRouter(prefix="/app-config", tags=["app-config"])


@router.get("", response_model=AppConfigResponse)
def read_app_config(session: Session = Depends(get_session)):
    """Public on purpose: a support handle is no secret, and the app may need it
    before anyone is signed in."""
    return AppConfigResponse(support_username=get_support_username(session))
