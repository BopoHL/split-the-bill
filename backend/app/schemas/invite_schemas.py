from pydantic import BaseModel

from app.models import InviteChannel


class InviteCreate(BaseModel):
    channel: InviteChannel = InviteChannel.LINK
    seat_participant_id: int | None = None


class InviteResponse(BaseModel):
    code: str
    channel: InviteChannel
    deep_link: str


class InviteResolved(BaseModel):
    """What the client needs to route an incoming invite."""
    code: str
    channel: InviteChannel
    bill_id: int
    public_token: str
    seat_participant_id: int | None
    inviter_user_id: int
    inviter_name: str | None
