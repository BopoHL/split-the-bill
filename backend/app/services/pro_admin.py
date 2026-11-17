"""Pro as the admin manages it: every grant — whose, why, for how long — and
taking one back: ending it now, refunding its Stars, or stopping the
subscription it belongs to from renewing.

What may be done with a grant is decided here, once, and sent along with it,
so the panel only offers what the server will do.
"""
from collections.abc import Callable
from datetime import datetime
from enum import Enum

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models import ProGrant, ProPlan, ProSubscription, PromoCode, User
from app.repositories.user_repo import UserRepository
from app.schemas.admin_schemas import AdminProGrant, AdminProGrantsPage, AdminProGrantUser
from app.services.pro import PLAN_DAYS, ProService
from app.services.product_events import ProductEvent, Surface, capture
from app.utils import telegram


class GrantAction(str, Enum):
    REVOKE = "revoke"
    REFUND = "refund"
    STOP_RENEWAL = "stop_renewal"
    ALLOW_RENEWAL = "allow_renewal"


class GrantState(str, Enum):
    ACTIVE = "active"
    UPCOMING = "upcoming"
    ENDED = "ended"
    REVOKED = "revoked"
    REFUNDED = "refunded"


class ProAdminService:
    def __init__(self, session: Session):
        self.session = session

    # ── Looking ──────────────────────────────────────────────────────────────

    def page(
        self,
        now: datetime,
        *,
        source: str | None = None,
        running: bool = False,
        user_id: int | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminProGrantsPage:
        """Grants newest first. `running` keeps the ones still to be had — on
        now or queued — and leaves out what ended or was taken back."""
        conditions = []
        if source:
            conditions.append(ProGrant.source == source)
        if running:
            conditions += [ProGrant.revoked_at.is_(None), ProGrant.ends_at > now]
        if user_id is not None:
            conditions.append(ProGrant.user_id == user_id)
        if q and q.strip():
            conditions.append(UserRepository.search_condition(q))

        total = self.session.exec(
            select(func.count(ProGrant.id)).join(User, User.id == ProGrant.user_id).where(*conditions)
        ).one()
        grants = self.session.exec(
            select(ProGrant)
            .join(User, User.id == ProGrant.user_id)
            .where(*conditions)
            .order_by(ProGrant.created_at.desc(), ProGrant.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return AdminProGrantsPage(items=self._rows(grants, now), total=total, limit=limit, offset=offset)

    def row(self, grant: ProGrant, now: datetime) -> AdminProGrant:
        return self._rows([grant], now)[0]

    def _rows(self, grants: list[ProGrant], now: datetime) -> list[AdminProGrant]:
        users = UserRepository(self.session).get_many({grant.user_id for grant in grants})
        promo_ids = {grant.promo_code_id for grant in grants if grant.promo_code_id}
        promos = {
            promo.id: promo for promo in self.session.exec(select(PromoCode).where(PromoCode.id.in_(promo_ids))).all()
        } if promo_ids else {}
        subscription_ids = {grant.subscription_id for grant in grants if grant.subscription_id}
        subscriptions = {
            subscription.id: subscription
            for subscription in self.session.exec(
                select(ProSubscription).where(ProSubscription.id.in_(subscription_ids))
            ).all()
        } if subscription_ids else {}
        latest = self._latest_grants(subscription_ids)

        rows = []
        for grant in grants:
            user = users[grant.user_id]
            promo = promos.get(grant.promo_code_id)
            subscription = subscriptions.get(grant.subscription_id)
            rows.append(AdminProGrant(
                id=grant.id,
                user=AdminProGrantUser(id=user.id, telegram_id=user.telegram_id, username=user.username, name=user.name),
                source=grant.source,
                plan=grant.plan,
                days=_term_days(grant, promo),
                stars=grant.stars,
                promo_code=promo.code if promo else None,
                starts_at=grant.starts_at,
                ends_at=grant.ends_at,
                created_at=grant.created_at,
                revoked_at=grant.revoked_at,
                refunded_at=grant.refunded_at,
                subscription_id=grant.subscription_id,
                renewal_canceled_at=subscription.renewal_canceled_at if subscription else None,
                state=_state(grant, now).value,
                actions=[action.value for action in _actions(grant, subscription, latest.get(grant.subscription_id), now)],
            ))
        return rows

    def _latest_grants(self, subscription_ids: set[int]) -> dict[int, int]:
        """Each subscription's newest month: the one its renewal is about."""
        if not subscription_ids:
            return {}
        return dict(self.session.exec(
            select(ProGrant.subscription_id, func.max(ProGrant.id))
            .where(ProGrant.subscription_id.in_(subscription_ids))
            .group_by(ProGrant.subscription_id)
        ).all())

    # ── Taking back ──────────────────────────────────────────────────────────

    def revoke(self, grant_id: int, now: datetime) -> ProGrant:
        """Pro from this grant ends now; a subscription stops renewing first,
        or Telegram would charge for the next month and give it back."""
        grant = self._grant(grant_id)
        if GrantAction.REVOKE not in self._actions_of(grant, now):
            raise HTTPException(status_code=409, detail="Nothing is left of this grant to take back")
        self._stop_renewal(grant, now)
        ProService(self.session).take_back(grant, now)
        return grant

    def refund(self, grant_id: int, now: datetime) -> ProGrant:
        """The Stars go back to the payer, and the Pro they paid for ends now."""
        grant = self._grant(grant_id)
        if GrantAction.REFUND not in self._actions_of(grant, now):
            raise HTTPException(status_code=409, detail="Only a payment not refunded yet can be refunded")
        running = GrantAction.REVOKE in self._actions_of(grant, now)
        if running:
            self._stop_renewal(grant, now)
        user = self.session.get(User, grant.user_id)
        try:
            telegram.refund_star_payment(user.telegram_id, grant.charge_id)
        except RuntimeError as error:
            # Refunded before, its answer lost on the way back: the Stars are
            # home, so the Pro they bought must go too, not fail on every retry.
            if "CHARGE_ALREADY_REFUNDED" not in str(error):
                raise HTTPException(status_code=502, detail=str(error)) from error
        grant.refunded_at = now
        if running:
            ProService(self.session).take_back(grant, now)
        else:
            self.session.add(grant)
            self.session.commit()
        capture(grant.user_id, ProductEvent.PRO_REFUNDED, Surface.SERVER, plan=grant.plan, stars=grant.stars, source=grant.source)
        return grant

    def set_renewal(self, subscription_id: int, canceled: bool, now: datetime) -> ProGrant:
        """Stop Telegram renewing a subscription, which stays paid to the end of
        its month — or let it renew again. Answers with its current month."""
        subscription = self.session.get(ProSubscription, subscription_id)
        if subscription is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        month = self.session.get(ProGrant, self._latest_grants({subscription_id}).get(subscription_id))
        wanted = GrantAction.STOP_RENEWAL if canceled else GrantAction.ALLOW_RENEWAL
        if month is None or wanted not in _actions(month, subscription, month.id, now):
            raise HTTPException(status_code=409, detail="This subscription has ended or already renews as asked")
        self._edit_renewal(subscription, canceled, now)
        return month

    def _stop_renewal(self, grant: ProGrant, now: datetime) -> None:
        subscription = self.session.get(ProSubscription, grant.subscription_id) if grant.subscription_id else None
        if subscription and subscription.renewal_canceled_at is None:
            self._edit_renewal(subscription, True, now)

    def _edit_renewal(self, subscription: ProSubscription, canceled: bool, now: datetime) -> None:
        user = self.session.get(User, subscription.user_id)
        _telegram(lambda: telegram.edit_star_subscription(user.telegram_id, subscription.charge_id, canceled))
        # Kept at once: what Telegram has done stays recorded even if a later
        # step of the same action fails.
        subscription.renewal_canceled_at = now if canceled else None
        self.session.add(subscription)
        self.session.commit()

    def _actions_of(self, grant: ProGrant, now: datetime) -> list[GrantAction]:
        subscription = self.session.get(ProSubscription, grant.subscription_id) if grant.subscription_id else None
        latest = self._latest_grants({grant.subscription_id}).get(grant.subscription_id) if subscription else None
        return _actions(grant, subscription, latest, now)

    def _grant(self, grant_id: int) -> ProGrant:
        grant = self.session.get(ProGrant, grant_id)
        if grant is None:
            raise HTTPException(status_code=404, detail="Grant not found")
        return grant


def _state(grant: ProGrant, now: datetime) -> GrantState:
    if grant.refunded_at:
        return GrantState.REFUNDED
    if grant.revoked_at:
        return GrantState.REVOKED
    if grant.ends_at <= now:
        return GrantState.ENDED
    if grant.starts_at > now:
        return GrantState.UPCOMING
    return GrantState.ACTIVE


def _actions(
    grant: ProGrant, subscription: ProSubscription | None, latest_month_id: int | None, now: datetime,
) -> list[GrantAction]:
    running = grant.revoked_at is None and grant.ends_at > now
    actions = []
    if running:
        actions.append(GrantAction.REVOKE)
    if grant.charge_id and grant.refunded_at is None:
        actions.append(GrantAction.REFUND)
    # A subscription's renewal is about its newest month, while that month lasts.
    if subscription and grant.id == latest_month_id and running:
        actions.append(GrantAction.ALLOW_RENEWAL if subscription.renewal_canceled_at else GrantAction.STOP_RENEWAL)
    return actions


def _term_days(grant: ProGrant, promo: PromoCode | None) -> int | None:
    """How long the grant was for, even after it was cut short."""
    if grant.plan:
        return PLAN_DAYS[ProPlan(grant.plan)]
    if promo:
        return promo.days
    if grant.revoked_at is None:
        return (grant.ends_at - grant.starts_at).days
    return None


def _telegram(call: Callable[[], None]) -> None:
    try:
        call()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
