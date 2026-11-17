from fastapi import APIRouter, Depends

from app.dependencies import get_authenticated_user
from app.models import User
from app.schemas.auth_schemas import SseTicketRequest, SseTicketResponse
from app.services.sse_ticket_service import TICKET_TTL_SECONDS, resource_key, sse_tickets

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sse-ticket", response_model=SseTicketResponse)
def issue_sse_ticket(
    payload: SseTicketRequest,
    current_user: User = Depends(get_authenticated_user),
):
    """Trade the signed Telegram identity for a URL-safe ticket.

    Needed because EventSource cannot send the X-Telegram-Init-Data header.
    """
    ticket = sse_tickets.issue(
        current_user.id, resource_key(payload.resource_type, payload.resource_id)
    )
    return SseTicketResponse(ticket=ticket, expires_in=TICKET_TTL_SECONDS)
