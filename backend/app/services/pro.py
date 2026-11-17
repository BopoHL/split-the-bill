"""Pro: who has it until when, buying it with Telegram Stars, promo codes.

Pro is kept as grants — stretches of time, each with its reason. Someone is Pro
while a grant covers the moment. A new grant starts where the last one ends, so
whatever is bought, given or redeemed adds to what is left rather than
overlapping it.

A month is sold as a Stars subscription Telegram renews by itself every thirty
days; six months and a year are paid once. Either way the money arrives as a
successful payment on the bot's webhook, and that — not the Mini App saying the
invoice closed — is what grants Pro.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import ProGrant, ProOffer, ProPlan, ProSource, ProSubscription, PromoCode, User
from app.services.app_settings import get_pro_offer_terms, get_pro_prices, get_pro_was_prices
from app.services.product_events import ProductEvent, Surface, capture
from app.utils.local_time import local_zone
from app.utils.bot_copy import t

logger = logging.getLogger(__name__)

PLAN_DAYS = {ProPlan.MONTH: 30, ProPlan.HALF_YEAR: 182, ProPlan.YEAR: 365}
PLAN_MONTHS = {ProPlan.MONTH: 1, ProPlan.HALF_YEAR: 6, ProPlan.YEAR: 12}
# Telegram renews a Stars subscription every thirty days, and only that.
SUBSCRIPTION_PERIOD_SECONDS = 30 * 24 * 60 * 60
PAYLOAD_PREFIX = "pro"
STARS = "XTR"
# The Mini App's start parameter that opens straight on the paywall.
PRO_START = "pro"
# The offer is on what is paid up front. A month is a subscription Telegram renews
# at the price it began with, so a discount on it would last as long as it does.
OFFER_PLANS = (ProPlan.HALF_YEAR, ProPlan.YEAR)
# An invoice opened in the offer's last minutes may still be paid at its price.
OFFER_CHECKOUT_GRACE = timedelta(minutes=15)
PAID_SOURCES = (ProSource.PURCHASE.value, ProSource.SUBSCRIPTION.value)


@dataclass(frozen=True)
class PlanPrice:
    stars: int
    # Shown struck out above it: what it costs without the offer, or the operator's «was».
    was: int | None


def offer_price(stars: int, percent: int) -> int:
    return max(1, round(stars * (100 - percent) / 100))


@dataclass(frozen=True)
class ProStatus:
    active: bool
    until: datetime | None
    # The grant covering now is a free trial.
    trial: bool
    # A month ahead belongs to a subscription Telegram is still to renew.
    subscription: bool


class PromoError(Exception):
    """A code that gives nothing; the message is the code the app shows."""


def invoice_payload(plan: ProPlan, user_id: int) -> str:
    return f"{PAYLOAD_PREFIX}:{plan.value}:{user_id}"


def read_payload(payload: str) -> tuple[ProPlan, int] | None:
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != PAYLOAD_PREFIX or not parts[2].isdigit():
        return None
    try:
        return ProPlan(parts[1]), int(parts[2])
    except ValueError:
        return None


class ProService:
    def __init__(self, session: Session):
        self.session = session

    # ── Who is Pro ───────────────────────────────────────────────────────────

    def status(self, user_id: int, now: datetime) -> ProStatus:
        grants = self._ahead(user_id, now)
        current = next((grant for grant in grants if grant.starts_at <= now), None)
        return ProStatus(
            active=current is not None,
            until=max((grant.ends_at for grant in grants), default=None) if current else None,
            trial=current is not None and current.source == ProSource.TRIAL,
            # Paid ahead by a subscription, even behind a trial or a promo
            # still running: buying the month again would charge twice.
            subscription=self._renewing(grants),
        )

    def _renewing(self, grants: list[ProGrant]) -> bool:
        """Some of these is a month of a subscription Telegram is still to
        renew; one whose renewal was stopped ends with its month."""
        months = [grant for grant in grants if grant.source == ProSource.SUBSCRIPTION]
        stopped = set(self.session.exec(
            select(ProSubscription.id).where(
                ProSubscription.id.in_({month.subscription_id for month in months}),
                ProSubscription.renewal_canceled_at.is_not(None),
            )
        ).all()) if months else set()
        return any(month.subscription_id not in stopped for month in months)

    def is_pro(self, user_id: int, now: datetime) -> bool:
        return self.status(user_id, now).active

    def pro_among(self, user_ids: set[int], now: datetime) -> set[int]:
        """Which of these people are Pro right now, in one query."""
        if not user_ids:
            return set()
        rows = self.session.exec(
            select(ProGrant.user_id).where(
                ProGrant.user_id.in_(user_ids), ProGrant.starts_at <= now, ProGrant.ends_at > now,
            )
        ).all()
        return set(rows)

    def _ahead(self, user_id: int, now: datetime) -> list[ProGrant]:
        return list(self.session.exec(
            select(ProGrant).where(ProGrant.user_id == user_id, ProGrant.ends_at > now).order_by(ProGrant.starts_at)
        ).all())

    def _until(self, user_id: int, now: datetime) -> datetime:
        """Where a new grant starts: when the last one ends, or now."""
        latest = self.session.exec(select(func.max(ProGrant.ends_at)).where(ProGrant.user_id == user_id)).one()
        return max(now, latest) if latest else now

    def _grant(self, user_id: int, days: int, source: ProSource, now: datetime, **fields) -> ProGrant:
        # Two grants at once — a promo in the app, a renewal on the worker —
        # would both start where the last one ends and overlap; one at a time.
        self.session.exec(select(User).where(User.id == user_id).with_for_update()).one()
        starts_at = self._until(user_id, now)
        grant = ProGrant(
            user_id=user_id, source=source.value, starts_at=starts_at, ends_at=starts_at + timedelta(days=days), **fields,
        )
        self.session.add(grant)
        self.session.commit()
        self.session.refresh(grant)
        return grant

    def take_back(self, grant: ProGrant, now: datetime) -> None:
        """End a grant now. What was queued after it moves up by the time it no
        longer takes, so the person loses this grant and nothing paid for else."""
        if grant.ends_at > now:
            freed = grant.ends_at - max(grant.starts_at, now)
            queued = self.session.exec(
                select(ProGrant).where(
                    ProGrant.user_id == grant.user_id, ProGrant.id != grant.id, ProGrant.starts_at >= grant.ends_at,
                )
            ).all()
            for later in queued:
                later.starts_at -= freed
                later.ends_at -= freed
                self.session.add(later)
            grant.starts_at = min(grant.starts_at, now)
            grant.ends_at = now
        grant.revoked_at = now
        self.session.add(grant)
        self.session.commit()

    # ── Buying ───────────────────────────────────────────────────────────────

    def prices(self) -> dict[ProPlan, int]:
        return {ProPlan(plan): stars for plan, stars in get_pro_prices(self.session).items()}

    def price_list(self, user_id: int, now: datetime) -> dict[ProPlan, PlanPrice]:
        """What each plan costs this person now: their offer's price while it
        runs, else everyone's."""
        offer = self.offer(user_id, now)
        was_prices = get_pro_was_prices(self.session)
        listed = {}
        for plan, stars in self.prices().items():
            if offer and plan in OFFER_PLANS:
                listed[plan] = PlanPrice(offer_price(stars, offer.percent), stars)
            else:
                was = was_prices[plan.value]
                listed[plan] = PlanPrice(stars, was if was is not None and was > stars else None)
        return listed

    def invoice(self, user: User, plan: ProPlan, language: str, now: datetime) -> dict:
        """What Telegram's createInvoiceLink needs for the plan, in Stars."""
        stars = self.price_list(user.id, now)[plan].stars
        invoice = {
            "title": t(language, f"pro_invoice_title_{plan.value}"),
            "description": t(language, "pro_invoice_subscription" if plan == ProPlan.MONTH else "pro_invoice_description"),
            "payload": invoice_payload(plan, user.id),
            "currency": STARS,
            "prices": [{"label": t(language, f"pro_invoice_title_{plan.value}"), "amount": stars}],
        }
        if plan == ProPlan.MONTH:
            invoice["subscription_period"] = SUBSCRIPTION_PERIOD_SECONDS
        return invoice

    def checkout_problem(
        self, payload: str, from_telegram_id: int, currency: str, total: int, now: datetime,
    ) -> str | None:
        """Why Telegram should not take this payment — the copy key to say so —
        or None to let it through. Asked in the seconds before the money moves.
        A second subscription is not turned down here but once paid, as whether
        renewals pass through here too is not something to bet them on."""
        read = read_payload(payload)
        if read is None or currency != STARS:
            return "pro_checkout_failed"
        plan, user_id = read
        user = self.session.get(User, user_id)
        if not user or user.telegram_id != from_telegram_id:
            return "pro_checkout_failed"
        fair = {self.price_list(user_id, moment)[plan].stars for moment in (now, now - OFFER_CHECKOUT_GRACE)}
        if total not in fair:
            return "pro_price_changed"
        return None

    # ── The one-off offer ────────────────────────────────────────────────────

    def offer(self, user_id: int, now: datetime) -> ProOffer | None:
        """The person's offer while it still runs: it is on the first purchase,
        so a second one at its price is over."""
        offer = self.session.exec(select(ProOffer).where(ProOffer.user_id == user_id)).first()
        return offer if offer and offer.ends_at > now and not self._ever_paid(user_id) else None

    def start_offer(self, user_id: int, now: datetime) -> ProOffer | None:
        """The offer, made the first time it is asked for: once a person, only
        to someone who has never paid, and only while the operator offers one."""
        if self.session.exec(select(ProOffer.id).where(ProOffer.user_id == user_id)).first() is not None:
            return self.offer(user_id, now)
        percent, hours = get_pro_offer_terms(self.session)
        if percent == 0 or self._ever_paid(user_id):
            return None
        offer = ProOffer(user_id=user_id, percent=percent, ends_at=now + timedelta(hours=hours))
        self.session.add(offer)
        try:
            self.session.commit()
        except IntegrityError:
            # Asked for twice at once: the other request made it.
            self.session.rollback()
            return self.offer(user_id, now)
        capture(user_id, ProductEvent.PRO_OFFER_STARTED, Surface.SERVER, percent=percent, hours=hours)
        return offer

    def _ever_paid(self, user_id: int) -> bool:
        return self.session.exec(
            select(ProGrant.id).where(ProGrant.user_id == user_id, ProGrant.source.in_(PAID_SOURCES))
        ).first() is not None

    def payment_recorded(self, charge_id: str | None) -> bool:
        return charge_id is not None and self.session.exec(
            select(ProGrant.id).where(ProGrant.charge_id == charge_id)
        ).first() is not None

    def record_payment(self, from_telegram_id: int, payment: dict, now: datetime) -> ProGrant | None:
        """Grant what a successful payment paid for. Telegram may report the
        same payment twice; it is recorded once."""
        read = read_payload(payment.get("invoice_payload") or "")
        charge_id = payment.get("telegram_payment_charge_id")
        if read is None or not charge_id or payment.get("currency") != STARS:
            logger.warning("A payment the bot did not ask for: %s", payment.get("invoice_payload"))
            return None
        plan, user_id = read
        user = self.session.get(User, user_id)
        if not user or user.telegram_id != from_telegram_id:
            logger.warning("Payment %s for user %s came from someone else", charge_id, user_id)
            return None
        known = self.session.exec(select(ProGrant).where(ProGrant.charge_id == charge_id)).first()
        if known:
            return known
        recurring = plan == ProPlan.MONTH
        subscription = self._subscription_of(user_id, charge_id, payment) if recurring else None
        return self._grant(
            user_id,
            PLAN_DAYS[plan],
            ProSource.SUBSCRIPTION if recurring else ProSource.PURCHASE,
            now,
            plan=plan.value,
            stars=payment.get("total_amount"),
            charge_id=charge_id,
            subscription_id=subscription.id if subscription else None,
        )

    def _subscription_of(self, user_id: int, charge_id: str, payment: dict) -> ProSubscription:
        """The subscription a month was paid for: a new one on its first
        payment; on a renewal the person's latest that still renews, since
        Telegram renews no other."""
        renewal = payment.get("is_recurring") and not payment.get("is_first_recurring")
        latest = self.session.exec(
            select(ProSubscription)
            .where(ProSubscription.user_id == user_id)
            .order_by(ProSubscription.renewal_canceled_at.is_not(None), ProSubscription.id.desc())
        ).first()
        if renewal and latest:
            return latest
        if renewal:
            logger.warning("Renewal %s of a subscription the app never saw start", charge_id)
        subscription = ProSubscription(user_id=user_id, charge_id=charge_id)
        self.session.add(subscription)
        self.session.flush()
        return subscription

    def is_second_subscription(self, grant: ProGrant, now: datetime) -> bool:
        """This month started a subscription while another one still renews —
        paid through a month link made before that one began, as links never
        expire."""
        if grant.source != ProSource.SUBSCRIPTION or grant.subscription_id is None:
            return False
        if self.session.get(ProSubscription, grant.subscription_id).charge_id != grant.charge_id:
            return False
        others = [ahead for ahead in self._ahead(grant.user_id, now) if ahead.subscription_id != grant.subscription_id]
        return self._renewing(others)

    # ── Promo codes ──────────────────────────────────────────────────────────

    def redeem(self, user_id: int, code: str, now: datetime) -> ProGrant:
        promo = self.session.exec(select(PromoCode).where(PromoCode.code == normalize_code(code))).first()
        if not promo or not promo.is_active:
            raise PromoError("PROMO_UNKNOWN")
        if promo.expires_at and promo.expires_at <= now:
            raise PromoError("PROMO_EXPIRED")
        taken = self.session.exec(
            select(ProGrant).where(ProGrant.user_id == user_id, ProGrant.promo_code_id == promo.id)
        ).first()
        if taken:
            raise PromoError("PROMO_ALREADY_USED")
        # Counted in the database itself, so two people redeeming the last use
        # at the same moment cannot both have it.
        counted = self.session.execute(
            update(PromoCode)
            .where(PromoCode.id == promo.id, or_(PromoCode.max_uses.is_(None), PromoCode.uses < PromoCode.max_uses))
            .values(uses=PromoCode.uses + 1)
        )
        if counted.rowcount == 0:
            self.session.rollback()
            raise PromoError("PROMO_USED_UP")
        try:
            return self._grant(user_id, promo.days, ProSource.PROMO, now, promo_code_id=promo.id)
        except IntegrityError:
            # The same person redeeming it twice at once: the second one loses.
            self.session.rollback()
            raise PromoError("PROMO_ALREADY_USED")


def local_date(moment: datetime) -> str:
    """A naive UTC moment as the date it is where the app's people are."""
    return moment.replace(tzinfo=timezone.utc).astimezone(local_zone()).strftime("%d.%m.%Y")


def normalize_code(code: str) -> str:
    return "".join(code.split()).upper()


def pro_required(feature: str) -> HTTPException:
    """What stops someone without Pro; the app opens the paywall on it, on the
    feature it names."""
    return HTTPException(status_code=402, detail={"code": "PRO_REQUIRED", "feature": feature})


def require_pro(session: Session, user: User, feature: str, now: datetime) -> None:
    if not ProService(session).is_pro(user.id, now):
        raise pro_required(feature)
