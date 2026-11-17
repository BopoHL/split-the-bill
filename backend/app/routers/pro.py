"""Pro from the person's side: whether they have it, buying it with Stars,
redeeming a promo code."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.dependencies import ensure_self, get_authenticated_user
from app.models import ProPlan, User
from app.schemas.pro_schemas import ProInvoice, ProInvoiceRequest, ProOfferTerms, ProOverview, ProPlanOffer, PromoRedeem
from app.services.app_settings import get_free_scans_per_day
from app.services.pro import PLAN_MONTHS, PromoError, ProService
from app.services.reminder_service import FREE_REMINDERS_PER_MONTH, free_reminders_left
from app.services.scan_allowance import ScanAllowance
from app.services.shared_bill_service import language_of
from app.utils.telegram import create_invoice_link

router = APIRouter(prefix="/users", tags=["pro"])

# Codes that gave nothing, per person: past a few an hour, no more tries — a
# short code was otherwise found by going down a word list.
# shortcut: in-process, enough for the one uvicorn process; a second replica needs it in the database.
_PROMO_MISSES: dict[int, list[float]] = {}
PROMO_MISSES_PER_HOUR = 5


def overview(session: Session, user: User, now: datetime) -> ProOverview:
    pro = ProService(session)
    status = pro.status(user.id, now)
    offer = pro.offer(user.id, now)
    return ProOverview(
        active=status.active,
        until=status.until,
        trial=status.trial,
        subscription=status.subscription,
        plans=[
            ProPlanOffer(
                plan=plan.value,
                stars=price.stars,
                was_stars=price.was,
                months=PLAN_MONTHS[plan],
                recurring=plan == ProPlan.MONTH,
            )
            for plan, price in pro.price_list(user.id, now).items()
        ],
        free_scans_per_day=get_free_scans_per_day(session),
        scans_left_today=ScanAllowance(session).left_today(user.id, now),
        free_reminders_per_month=FREE_REMINDERS_PER_MONTH,
        reminders_left_this_month=free_reminders_left(session, user.id, now),
        offer=ProOfferTerms(percent=offer.percent, ends_at=offer.ends_at) if offer else None,
    )


@router.get("/{user_id}/pro", response_model=ProOverview)
def get_pro(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    ensure_self(current_user, user_id)
    return overview(session, current_user, datetime.utcnow())


@router.post("/{user_id}/pro/offer", response_model=ProOverview)
def start_pro_offer(
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """Asked when the paywall opens: makes the person's one-off offer if they
    may have one and it is not made yet, and answers with Pro as it now stands."""
    ensure_self(current_user, user_id)
    now = datetime.utcnow()
    ProService(session).start_offer(current_user.id, now)
    return overview(session, current_user, now)


@router.post("/{user_id}/pro/invoice", response_model=ProInvoice)
def create_pro_invoice(
    user_id: int,
    payload: ProInvoiceRequest,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """A Stars invoice for the plan, for WebApp.openInvoice. Pro comes with the
    payment Telegram reports to the bot, not with this link."""
    ensure_self(current_user, user_id)
    try:
        plan = ProPlan(payload.plan)
    except ValueError:
        raise HTTPException(status_code=400, detail="Unknown plan")
    pro = ProService(session)
    now = datetime.utcnow()
    if plan == ProPlan.MONTH and pro.status(current_user.id, now).subscription:
        # Telegram would start a second subscription next to the running one.
        raise HTTPException(status_code=409, detail="SUBSCRIPTION_ACTIVE")
    invoice = pro.invoice(current_user, plan, language_of(current_user), now)
    try:
        return ProInvoice(link=create_invoice_link(invoice))
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/{user_id}/pro/redeem", response_model=ProOverview)
def redeem_promo(
    user_id: int,
    payload: PromoRedeem,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    ensure_self(current_user, user_id)
    now = datetime.utcnow()
    clock = now.timestamp()
    misses = [t for t in _PROMO_MISSES.pop(current_user.id, []) if clock - t < 3600]
    if len(misses) >= PROMO_MISSES_PER_HOUR:
        _PROMO_MISSES[current_user.id] = misses
        raise HTTPException(status_code=429, detail={"code": "PROMO_TOO_MANY"})
    try:
        ProService(session).redeem(current_user.id, payload.code, now)
    except PromoError as error:
        _PROMO_MISSES[current_user.id] = [*misses, clock]
        raise HTTPException(status_code=400, detail={"code": str(error)})
    return overview(session, current_user, now)
