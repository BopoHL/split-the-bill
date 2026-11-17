from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models import ReceiptTaskStatus

class ReceiptTaskResponse(BaseModel):
    id: int
    user_id: Optional[int]
    filename: Optional[str] = None
    status: str
    bill_id: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
