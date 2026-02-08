from pydantic import BaseModel

class UserCreate(BaseModel):
    """Schema for creating/updating a user"""
    telegram_id: int
    username: str | None = None
    avatar_url: str | None = None
    init_data: str | None = None  # Full initData for WebApp verification
    widget_data: dict | None = None  # Full data from Login Widget

class UserResponse(BaseModel):
    """Schema for user response"""
    id: int
    telegram_id: int
    username: str | None
    avatar_url: str | None
