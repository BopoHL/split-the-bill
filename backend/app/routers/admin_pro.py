"""Pro from the admin panel: prices, the free day's scans, promo codes, how
many people have it, and every grant of it — with taking one back."""
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import get_session
from app.models import ProGrant, ProSource, PromoCode
from app.schemas.admin_schemas import (
    AdminProGrant,
    AdminProGrantsPage,
    AdminProSettings,
    AdminProSettingsUpdate,
    AdminProStats,
    AdminPromoCode,
    AdminPromoCodeCreate,
    AdminPromoCodeUpdate,
    AdminRenewalUpdate,
)
from app.services.app_settings import (
    FREE_SCANS_KEY,
    MAX_PRO_OFFER_HOURS,
    MAX_PRO_OFFER_PERCENT,
    MAX_STARS,
    PRO_OFFER_HOURS_KEY,
    PRO_OFFER_PERCENT_KEY,
    PRO_PRICE_KEYS,
    PRO_WAS_PRICE_KEYS,
    get_free_scans_per_day,
    get_pro_offer_terms,
    get_pro_prices,
    get_pro_was_prices,
    set_setting,
)
from app.services.pro import normalize_code
from app.services.pro_admin import ProAdminService
from app.utils.admin_auth import require_admin
from app.utils.local_time import naive_utc

router = APIRouter(prefix="/admin/pro", tags=["admin"], dependencies=[Depends(require_admin)])

PAID = (ProSource.PURCHASE.value, ProSource.SUBSCRIPTION.value)
CODE_SHAPE = re.compile(r"^[A-Z0-9_-]{3,32}$")
# Letters and digits nobody misreads: no 0/O, no 1/I.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _stats(session: Session, now: datetime) -> AdminProStats:
    def people(*conditions) -> int:
        return session.exec(
            select(func.count(func.distinct(ProGrant.user_id))).where(
                ProGrant.starts_at <= now, ProGrant.ends_at > now, *conditions,
            )
        ).one()

    def stars(*conditions) -> int:
        return session.exec(
            select(func.coalesce(func.sum(ProGrant.stars), 0)).where(ProGrant.refunded_at.is_(None), *conditions)
        ).one()

    return AdminProStats(
        active=people(),
        paying=people(ProGrant.source.in_(PAID)),
        trial=people(ProGrant.source == ProSource.TRIAL.value),
        stars_last_30_days=stars(ProGrant.created_at >= now - timedelta(days=30)),
        stars_total=stars(),
    )


def _settings(session: Session) -> AdminProSettings:
    offer_percent, offer_hours = get_pro_offer_terms(session)
    return AdminProSettings(
        prices=get_pro_prices(session),
        was_prices=get_pro_was_prices(session),
        free_scans_per_day=get_free_scans_per_day(session),
        offer_percent=offer_percent,
        offer_hours=offer_hours,
        stats=_stats(session, datetime.utcnow()),
    )


@router.get("", response_model=AdminProSettings)
def read_pro(session: Session = Depends(get_session)):
    return _settings(session)


@router.put("", response_model=AdminProSettings)
def write_pro(payload: AdminProSettingsUpdate, session: Session = Depends(get_session)):
    """A new price holds for invoices made from now on; one opened before it is
    refused at checkout, and the app asks for a fresh one. A «was» price only
    shows how much is off — it is never charged."""
    # Everything is checked before anything is written, so a refused change
    # leaves the prices as they were.
    prices = {**get_pro_prices(session), **(payload.prices or {})}
    for plan, stars in (payload.prices or {}).items():
        if plan not in PRO_PRICE_KEYS:
            raise HTTPException(status_code=400, detail=f"Unknown plan «{plan}»")
        if not 1 <= stars <= MAX_STARS:
            raise HTTPException(status_code=400, detail=f"A price is 1 to {MAX_STARS} Stars")
    for plan, was in (payload.was_prices or {}).items():
        if plan not in PRO_WAS_PRICE_KEYS:
            raise HTTPException(status_code=400, detail=f"Unknown plan «{plan}»")
        if was is not None and not prices[plan] < was <= MAX_STARS:
            raise HTTPException(status_code=400, detail="A «was» price is above the price and at most 10000 Stars")
    if payload.free_scans_per_day is not None and payload.free_scans_per_day < 0:
        raise HTTPException(status_code=400, detail="Scans a day cannot be negative")
    if payload.offer_percent is not None and not 0 <= payload.offer_percent <= MAX_PRO_OFFER_PERCENT:
        raise HTTPException(status_code=400, detail=f"The offer is 0 to {MAX_PRO_OFFER_PERCENT}% off")
    if payload.offer_hours is not None and not 1 <= payload.offer_hours <= MAX_PRO_OFFER_HOURS:
        raise HTTPException(status_code=400, detail=f"The offer lasts 1 to {MAX_PRO_OFFER_HOURS} hours")

    for plan, stars in (payload.prices or {}).items():
        set_setting(session, PRO_PRICE_KEYS[plan], str(stars))
    for plan, was in (payload.was_prices or {}).items():
        set_setting(session, PRO_WAS_PRICE_KEYS[plan], "" if was is None else str(was))
    if payload.free_scans_per_day is not None:
        set_setting(session, FREE_SCANS_KEY, str(payload.free_scans_per_day))
    if payload.offer_percent is not None:
        set_setting(session, PRO_OFFER_PERCENT_KEY, str(payload.offer_percent))
    if payload.offer_hours is not None:
        set_setting(session, PRO_OFFER_HOURS_KEY, str(payload.offer_hours))
    return _settings(session)


@router.get("/promo-codes", response_model=list[AdminPromoCode])
def list_promo_codes(session: Session = Depends(get_session)):
    return session.exec(select(PromoCode).order_by(PromoCode.created_at.desc())).all()


@router.post("/promo-codes", response_model=AdminPromoCode, status_code=201)
def create_promo_code(payload: AdminPromoCodeCreate, session: Session = Depends(get_session)):
    code = normalize_code(payload.code or "") or "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    if not CODE_SHAPE.match(code):
        raise HTTPException(status_code=400, detail="A code is 3 to 32 letters, digits, - or _")
    if payload.days < 1:
        raise HTTPException(status_code=400, detail="A code gives at least a day")
    if payload.max_uses is not None and payload.max_uses < 1:
        raise HTTPException(status_code=400, detail="A code can be used at least once")
    if session.exec(select(PromoCode).where(PromoCode.code == code)).first():
        raise HTTPException(status_code=409, detail="This code already exists")
    promo = PromoCode(
        code=code,
        days=payload.days,
        max_uses=payload.max_uses,
        expires_at=naive_utc(payload.expires_at) if payload.expires_at else None,
        note=(payload.note or "").strip() or None,
    )
    session.add(promo)
    session.commit()
    session.refresh(promo)
    return promo


@router.patch("/promo-codes/{promo_id}", response_model=AdminPromoCode)
def update_promo_code(promo_id: int, payload: AdminPromoCodeUpdate, session: Session = Depends(get_session)):
    """Switched off, a code gives nothing more; what it gave stays."""
    promo = session.get(PromoCode, promo_id)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo code not found")
    promo.is_active = payload.is_active
    session.add(promo)
    session.commit()
    session.refresh(promo)
    return promo


@router.get("/grants", response_model=AdminProGrantsPage)
def list_grants(
    source: ProSource | None = None,
    running: bool = False,
    user_id: int | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """Every stretch of Pro anyone was given, newest first: bought, renewed,
    from a promo code or a trial."""
    return ProAdminService(session).page(
        datetime.utcnow(),
        source=source.value if source else None,
        running=running,
        user_id=user_id,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.post("/grants/{grant_id}/revoke", response_model=AdminProGrant)
def revoke_grant(grant_id: int, session: Session = Depends(get_session)):
    service, now = ProAdminService(session), datetime.utcnow()
    return service.row(service.revoke(grant_id, now), now)


@router.post("/grants/{grant_id}/refund", response_model=AdminProGrant)
def refund_grant(grant_id: int, session: Session = Depends(get_session)):
    service, now = ProAdminService(session), datetime.utcnow()
    return service.row(service.refund(grant_id, now), now)


@router.put("/subscriptions/{subscription_id}/renewal", response_model=AdminProGrant)
def set_renewal(subscription_id: int, payload: AdminRenewalUpdate, session: Session = Depends(get_session)):
    service, now = ProAdminService(session), datetime.utcnow()
    return service.row(service.set_renewal(subscription_id, payload.canceled, now), now)
