from pydantic import BaseModel
from datetime import datetime

class BillCreate(BaseModel):
    """Schema for creating a bill"""
    owner_id: int
    total_sum: float
    title: str | None = None
    payment_details: str | None = None
    include_owner: bool = False

class BillResponse(BaseModel):
    """Schema for bill response"""
    id: int
    owner_id: int
    total_sum: float
    title: str | None
    payment_details: str | None
    is_closed: bool
    split_type: str
    unallocated_sum: float
    created_at: datetime
    participants_count: int

class BillItemCreate(BaseModel):
    """Schema for creating a bill item"""
    name: str
    price: float
    count: int = 1
    assigned_to_user_id: int | None = None

class BillItemResponse(BaseModel):
    """Schema for bill item response"""
    id: int
    bill_id: int
    name: str
    price: float
    count: int
    item_sum: float
    assigned_to_user_id: int | None

class BillParticipantCreate(BaseModel):
    """Schema for adding a participant to a bill"""
    user_id: int | None = None
    guest_name: str | None = None

class BillParticipantResponse(BaseModel):
    """Schema for bill participant response"""
    id: int
    bill_id: int
    user_id: int | None
    guest_name: str | None
    username: str | None = None
    avatar_url: str | None = None
    allocated_amount: float
    is_paid: bool

class BillParticipantAssign(BaseModel):
    """Schema for manual amount assignment to a participant"""
    participant_id: int
    allocated_amount: float

class BillSplitRemainder(BaseModel):
    """Schema for splitting the remainder among selected participants"""
    participant_ids: list[int]

class BillParticipantPaymentUpdate(BaseModel):
    """Schema for updating participant's payment status"""
    is_paid: bool
    user_id: int

class BillParticipantRemove(BaseModel):
    """Schema for removing a participant"""
    user_id: int

class BillDetailResponse(BaseModel):
    """Detailed bill response with items and participants"""
    id: int
    owner_id: int
    total_sum: float
    title: str | None
    payment_details: str | None
    is_closed: bool
    split_type: str
    unallocated_sum: float
    created_at: datetime
    items: list[BillItemResponse]
    participants: list[BillParticipantResponse]

class ReactionCreate(BaseModel):
    """Schema for creating a reaction"""
    user_id: int
    emoji: str
