"""The app's themes. Light and dark are everyone's; the rest come with Pro.

Without Pro a Pro theme gives way to the free one of its own lightness. The
choice itself is kept, so the theme comes back when Pro does.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session

from app.models import User
from app.services.pro import ProService, pro_required

FREE_THEMES = ("light", "dark")
# Each Pro theme and the free one it falls back to.
PRO_THEMES = {"nord": "dark", "nord_frost": "light", "sakura": "light", "midnight": "dark"}
DEFAULT_THEME = "light"


def shown_theme(chosen: str | None, pro: bool) -> str:
    if chosen in FREE_THEMES:
        return chosen
    if chosen in PRO_THEMES:
        return chosen if pro else PRO_THEMES[chosen]
    return DEFAULT_THEME


def theme_of(session: Session, user: User, now: datetime) -> str:
    """The theme someone sees the app in, and so the pictures posted for them."""
    chosen = (user.settings or {}).get("theme")
    return shown_theme(chosen, chosen in PRO_THEMES and ProService(session).is_pro(user.id, now))


def ensure_choosable(session: Session, user_id: int, theme: str, now: datetime) -> None:
    if theme in FREE_THEMES:
        return
    if theme not in PRO_THEMES:
        raise HTTPException(status_code=400, detail="Unknown theme")
    if not ProService(session).is_pro(user_id, now):
        raise pro_required("themes")
