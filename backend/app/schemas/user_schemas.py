from pydantic import BaseModel

class UserCreate(BaseModel):
    """Schema for creating/updating a user"""
    telegram_id: int
    username: str | None = None
    avatar_url: str | None = None

class UserResponse(BaseModel):
    """Schema for user response"""
    id: int
    telegram_id: int
    username: str | None
    avatar_url: str | None
