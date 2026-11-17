import os
from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session
from app.database import get_session
from app.schemas.user_schemas import (
    ProfileBadgeChoice,
    ProfileBadges,
    UserCreate,
    UserResponse,
    UserSettingsUpdate,
    UserWriteAccessUpdate,
)
from app.schemas.bill_schemas import BillCounts, BillResponse
from app.repositories.user_repo import UserRepository
from app.services.user_service import UserService
from app.repositories.bill_repo import BillRepository
from app.services.bill_core_service import BillCoreService
from app.dependencies import ensure_self, get_authenticated_user
from app.models import User
from app.schemas.reminder_schemas import OwedSummary, OwedTotal, ReminderRequestResponse
from app.services.reminder_service import ReminderService
from app.schemas.analytics_schemas import AnalyticsPictures, AnalyticsResponse
from app.services.analytics import AnalyticsService, Period, PeriodKind, free_view
from app.services.pro import ProService, require_pro
from app.services.themes import ensure_choosable
from app.services.badges import BadgeService
from app.services.analytics_pictures import AnalyticsPictureService
from app.services.picture_links import asked
from app.utils.local_time import local_zone
from app.services.places import recent_places
from app.utils.currency import from_tiins

router = APIRouter(prefix="/users", tags=["users"])
public_router = APIRouter(prefix="/public/analytics", tags=["analytics"])

def get_user_service(session: Session = Depends(get_session)) -> UserService:
    user_repo = UserRepository(session)
    return UserService(user_repo)


def get_bill_core_service(session: Session = Depends(get_session)) -> BillCoreService:
    bill_repo = BillRepository(session)
    user_repo = UserRepository(session)
    return BillCoreService(bill_repo, user_repo)


def get_reminder_service(session: Session = Depends(get_session)) -> ReminderService:
    return ReminderService(session)


@router.post("/", response_model=UserResponse)
def create_or_update_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service)
):
    """Create a new user or update existing one based on telegram_id"""
    return user_service.create_or_update_user(user_data)

@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    user_service: UserService = Depends(get_user_service),
):
    """Get your own profile."""
    ensure_self(current_user, user_id)
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/{user_id}/settings", response_model=UserResponse)
def update_user_settings(
    user_id: int,
    payload: UserSettingsUpdate,
    current_user: User = Depends(get_authenticated_user),
    user_service: UserService = Depends(get_user_service),
    session: Session = Depends(get_session),
):
    """Merge the given preferences into the user's stored settings. Themes
    other than light and dark are Pro's."""
    ensure_self(current_user, user_id)
    if payload.theme is not None:
        ensure_choosable(session, user_id, payload.theme, datetime.utcnow())
    return user_service.update_settings(user_id, payload)


@router.get("/{user_id}/badges", response_model=ProfileBadges)
def get_badges(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """The badges the user may show by their name, and the one they show."""
    ensure_self(current_user, user_id)
    return BadgeService(session).overview(current_user, datetime.utcnow())


@router.put("/{user_id}/badge", response_model=ProfileBadges)
def choose_badge(
    user_id: int,
    payload: ProfileBadgeChoice,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """Show this badge by the user's name — one they have — or none, or the default."""
    ensure_self(current_user, user_id)
    return BadgeService(session).choose(current_user, payload.badge, datetime.utcnow())


@router.patch("/{user_id}/write-access", response_model=UserResponse)
def update_user_write_access(
    user_id: int,
    payload: UserWriteAccessUpdate,
    current_user: User = Depends(get_authenticated_user),
    user_service: UserService = Depends(get_user_service),
):
    """Sync Telegram's current permission for bot messages."""
    ensure_self(current_user, user_id)
    return user_service.update_write_access(user_id, payload)


@router.get("/{user_id}/bills", response_model=list[BillResponse])
def get_user_bills(
    user_id: int,
    offset: int = Query(default=0, ge=0, description="How many of the newest to skip — the count already shown, so a bill deleted since moves nothing past the client"),
    limit: int = Query(default=10, ge=1, le=100),
    status: Optional[Literal["active", "closed"]] = Query(
        default=None,
        description="Filter by status: 'active' (open/paid), 'closed', or omit for all",
    ),
    q: Optional[str] = Query(default=None, max_length=100, description="Title, owner or anyone at the table"),
    role: Optional[Literal["owner", "participant"]] = Query(default=None, description="Bills the user owns, or only joined"),
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Get bills for a user (as owner or participant), newest first.

    Use `status=active` for the home screen and `status=closed` for the
    paginated archive, which `q` searches and `role` narrows.
    """
    ensure_self(current_user, user_id)
    return service.get_user_bills(
        user_id, offset=offset, limit=limit, status_filter=status, query=q, role=role
    )


@router.get("/{user_id}/bills/counts", response_model=BillCounts)
def count_user_bills(
    user_id: int,
    status: Optional[Literal["active", "closed"]] = None,
    q: Optional[str] = Query(default=None, max_length=100),
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """How many bills the list would hold — in all, owned, and only joined."""
    ensure_self(current_user, user_id)
    return service.count_user_bills(user_id, status_filter=status, query=q)


@router.get("/{user_id}/analytics", response_model=AnalyticsResponse)
def get_analytics(
    user_id: int,
    period: PeriodKind = PeriodKind.MONTH,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """The user's bills seen from above, for a month, a year or all time. A
    month or year not named is the current one, where the bills are."""
    ensure_self(current_user, user_id)
    chosen = Period.named(period, year, month, datetime.now(local_zone()).date())
    now = datetime.utcnow()
    data = AnalyticsService(session).for_user(current_user, chosen, now)
    return data if ProService(session).is_pro(current_user.id, now) else free_view(data)


def _public_base(request: Request) -> str:
    """Where Telegram reaches this server from outside."""
    return os.getenv("PUBLIC_BASE_URL") or str(request.base_url)


@router.get("/{user_id}/analytics/pictures", response_model=AnalyticsPictures)
def get_analytics_pictures(
    user_id: int,
    request: Request,
    period: PeriodKind = PeriodKind.MONTH,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """With Pro: addresses of the period's report receipt and, for a year, its
    stories, for the app to show and for Telegram to fetch."""
    ensure_self(current_user, user_id)
    require_pro(session, current_user, "analytics", datetime.utcnow())
    chosen = Period.named(period, year, month, datetime.now(local_zone()).date())
    return AnalyticsPictureService(session).addresses(current_user, chosen, _public_base(request), datetime.now(timezone.utc))


@router.post("/{user_id}/analytics/prepare-share")
def prepare_analytics_share(
    user_id: int,
    request: Request,
    period: PeriodKind = PeriodKind.MONTH,
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """With Pro: register the period's receipt with Telegram as a photo to send
    and return its prepared_message_id for WebApp.shareMessage (Bot API 8.0)."""
    ensure_self(current_user, user_id)
    require_pro(session, current_user, "analytics", datetime.utcnow())
    chosen = Period.named(period, year, month, datetime.now(local_zone()).date())
    prepared_id = AnalyticsPictureService(session).prepare_share(
        current_user, chosen, _public_base(request), datetime.now(timezone.utc)
    )
    return {"prepared_message_id": prepared_id}


@public_router.get("/{user_id}/{picture}.jpg")
def get_analytics_picture(
    user_id: int,
    picture: str,
    expires: int,
    sig: str,
    period: PeriodKind = PeriodKind.MONTH,
    year: Optional[int] = None,
    month: Optional[int] = None,
    theme: str = "light",
    download: bool = False,
    session: Session = Depends(get_session),
):
    """A picture of someone's analytics, for whoever holds its signed address:
    Telegram, fetching a story or a shared photo, has no Mini App session."""
    address = asked(user_id, picture, period, year, month, theme, expires)
    now = datetime.now(timezone.utc)
    if not address.holds(sig, now):
        raise HTTPException(status_code=403, detail="This link has expired")
    headers = {"Cache-Control": "private, max-age=300"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="split-bill-{picture}.jpg"'
    return Response(AnalyticsPictureService(session).draw(address, now), media_type="image/jpeg", headers=headers)


@router.get("/{user_id}/places", response_model=list[str])
def get_places(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """The places the user's bills were at, the latest first — offered when
    they name the place of another one."""
    ensure_self(current_user, user_id)
    return recent_places(session, user_id)


@router.get("/{user_id}/owed", response_model=OwedSummary)
def get_owed(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: ReminderService = Depends(get_reminder_service),
):
    """What others owe the user on their open bills, per currency."""
    ensure_self(current_user, user_id)
    owed = service.owed(user_id, datetime.utcnow())
    return OwedSummary(
        totals=[
            OwedTotal(currency=currency, amount=from_tiins(amount))
            for currency, amount in sorted(owed.totals.items(), key=lambda total: -total[1])
        ],
        people=owed.people,
        bills=owed.bills,
        remindable=owed.remindable,
        next_reminder_at=owed.next_at,
        why_nobody=owed.why_nobody,
    )


@router.post("/{user_id}/owed/reminders", response_model=ReminderRequestResponse)
def remind_everyone_who_owes(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: ReminderService = Depends(get_reminder_service),
):
    """With Pro: a reminder to everyone who owes the user on any open bill."""
    ensure_self(current_user, user_id)
    requested = service.request_owed(user_id, datetime.utcnow())
    return ReminderRequestResponse.of(len(requested.queued), requested.skipped)
