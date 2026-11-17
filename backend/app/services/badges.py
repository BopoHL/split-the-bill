"""The badge by someone's name, seen by everyone at their bills.

They pick it from what they have: a title analytics gave them for all their
bills — «Coffee lover», «Night owl» — or Pro while they have it. Until they
pick, Pro shows by itself; they may also pick none. A title once earned stays
theirs; Pro shows only while it lasts.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import User
from app.schemas.analytics_schemas import Badge
from app.schemas.user_schemas import ProfileBadge, ProfileBadges
from app.services.analytics import AnalyticsService, Period, PeriodKind
from app.services.pro import ProService

PRO_BADGE = "pro"
NO_BADGE = "none"
SETTING = "badge"


def shown_badge(chosen: str | None, pro: bool) -> str | None:
    if chosen == NO_BADGE:
        return None
    if chosen is None or chosen == PRO_BADGE:
        return PRO_BADGE if pro else None
    return chosen


class BadgeService:
    def __init__(self, session: Session):
        self.session = session

    def overview(self, user: User, now: datetime) -> ProfileBadges:
        """The badges the person may show, and the one they show."""
        return self._overview(user, now, self._earned(user, now))

    def choose(self, user: User, badge: str | None, now: datetime) -> ProfileBadges:
        """Keep the pick: none, Pro while there is Pro, or an earned title; no
        pick at all brings back the default."""
        earned = self._earned(user, now)
        pro = ProService(self.session).is_pro(user.id, now)
        available = {key for key, *_ in self._available(earned, pro, (user.settings or {}).get(SETTING))}
        if badge not in (None, NO_BADGE) and badge not in available:
            raise HTTPException(status_code=400, detail="BADGE_NOT_EARNED")
        settings = {key: value for key, value in (user.settings or {}).items() if key != SETTING}
        if badge is not None:
            settings[SETTING] = badge
        user.settings = settings
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return self._overview(user, now, earned)

    def _earned(self, user: User, now: datetime) -> list[Badge]:
        """The titles all of the person's bills give them."""
        return AnalyticsService(self.session).for_user(user, Period(PeriodKind.ALL), now).badges

    @staticmethod
    def _available(earned: list[Badge], pro: bool, chosen: str | None) -> list[tuple[str, int | None, str | None]]:
        """Pro while it lasts, the titles the bills give now, and the title the
        person shows even if the numbers have since moved on from it."""
        available = ([(PRO_BADGE, None, None)] if pro else []) + [(badge.key, badge.value, badge.subject) for badge in earned]
        if chosen not in (None, NO_BADGE, PRO_BADGE) and chosen not in {key for key, *_ in available}:
            available.append((chosen, None, None))
        return available

    def _overview(self, user: User, now: datetime, earned: list[Badge]) -> ProfileBadges:
        pro = ProService(self.session).is_pro(user.id, now)
        chosen = (user.settings or {}).get(SETTING)
        return ProfileBadges(
            chosen=chosen,
            shown=shown_badge(chosen, pro),
            available=[
                ProfileBadge(key=key, value=value, subject=subject)
                for key, value, subject in self._available(earned, pro, chosen)
            ],
        )

    def shown_for(self, user_ids: set[int], now: datetime) -> dict[int, str | None]:
        """The badge each of these people shows, in two queries."""
        if not user_ids:
            return {}
        pro = ProService(self.session).pro_among(user_ids, now)
        users = self.session.exec(select(User).where(User.id.in_(user_ids))).all()
        return {user.id: shown_badge((user.settings or {}).get(SETTING), user.id in pro) for user in users}
