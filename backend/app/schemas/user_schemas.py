import re

from pydantic import BaseModel, field_validator

# What an analytics label may be: a start kind or a link's channel.
LABEL = re.compile(r"[a-z0-9_-]{1,64}")


class UserCreate(BaseModel):
    """Schema for creating/updating a user"""
    telegram_id: int
    username: str | None = None
    name: str | None = None
    surname: str | None = None
    avatar_url: str | None = None
    invite_code: str | None = None  # Who brought them, when the account is new
    init_data: str | None = None  # Full initData for WebApp verification
    allows_write_to_pm: bool | None = None
    # How this open came in — the kind of start and a `src_` link's channel —
    # kept on the person as their first touch when this call makes the account.
    start: str | None = None
    source: str | None = None

    @field_validator("start", "source")
    @classmethod
    def _label_or_nothing(cls, value: str | None) -> str | None:
        """A label for analytics; anything else is dropped rather than refused,
        so it can never keep someone from signing in."""
        return value if value and LABEL.fullmatch(value) else None


class UserResponse(BaseModel):
    """Schema for user response"""
    id: int
    telegram_id: int
    username: str | None
    name: str | None
    surname: str | None
    avatar_url: str | None
    settings: dict = {}


class UserSettingsUpdate(BaseModel):
    """Partial update of user preferences; unset fields are left unchanged."""
    theme: str | None = None
    language: str | None = None
    currency: str | None = None
    # Set once the user has seen the first-run onboarding. Stored inside the
    # existing JSON `settings` column, so no migration is needed.
    onboarding_completed: bool | None = None
    # Set once someone who joined another person's bill has seen the guest tour.
    guest_tour_completed: bool | None = None


class UserWriteAccessUpdate(BaseModel):
    """Telegram's current permission for the bot to write to this user."""
    allows_write_to_pm: bool


class ProfileBadge(BaseModel):
    """A badge someone may show by their name: «pro», or an analytics title with
    the number behind it."""
    key: str
    value: int | None = None
    subject: str | None = None


class ProfileBadges(BaseModel):
    # What they picked: «none», a badge's key, or nothing yet (Pro shows by itself).
    chosen: str | None
    shown: str | None
    available: list[ProfileBadge]


class ProfileBadgeChoice(BaseModel):
    # Null goes back to the default.
    badge: str | None = None
