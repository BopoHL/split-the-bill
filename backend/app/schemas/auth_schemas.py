from typing import Literal

from pydantic import BaseModel

SseResourceType = Literal["bill", "receipt_task"]


class SseTicketRequest(BaseModel):
    resource_type: SseResourceType
    resource_id: int


class SseTicketResponse(BaseModel):
    ticket: str
    expires_in: int
