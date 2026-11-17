"""Telling people their Pro is about to end, once for each stretch of it.

The trial's week gets a day's notice, anything bought three days'. A
subscription renews by itself and is not mentioned — unless its renewal was
stopped, and then its last month ends like anything bought. Someone with
another grant lined up after the one ending hears nothing until that one ends
too.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from app.models import ProGrant, ProSource, ProSubscription, User
from app.services.pro import PRO_START, local_date
from app.services.shared_bill_service import language_of
from app.utils.bot_copy import t
from app.utils.quiet_hours import in_quiet_hours
from app.utils.telegram import mini_app_link, send_message

logger = logging.getLogger(__name__)

TRIAL_NOTICE = timedelta(days=1)
PAID_NOTICE = timedelta(days=3)
BATCH = 50


def run(session: Session, now: datetime) -> int:
    if in_quiet_hours(now):
        # Not worth waking anyone for: the notice comes days ahead and keeps till morning.
        return 0
    last = (
        select(ProGrant.user_id, func.max(ProGrant.ends_at).label("ends_at"))
        .group_by(ProGrant.user_id)
        .subquery()
    )
    # Each kind asked for only inside its own notice: a trial due in two days
    # must not fill the batch and keep out a purchase due in three.
    due = or_(
        and_(ProGrant.source == ProSource.TRIAL.value, ProGrant.ends_at <= now + TRIAL_NOTICE),
        and_(ProGrant.source != ProSource.TRIAL.value, ProGrant.ends_at <= now + PAID_NOTICE),
    )
    ending = session.exec(
        select(ProGrant)
        .join(last, and_(ProGrant.user_id == last.c.user_id, ProGrant.ends_at == last.c.ends_at))
        .outerjoin(ProSubscription, ProSubscription.id == ProGrant.subscription_id)
        .where(
            ProGrant.ending_noted_at.is_(None),
            or_(ProGrant.source != ProSource.SUBSCRIPTION.value, ProSubscription.renewal_canceled_at.is_not(None)),
            ProGrant.ends_at > now,
            due,
        )
        .order_by(ProGrant.ends_at)
        .limit(BATCH)
    ).all()

    told = 0
    for grant in ending:
        trial = grant.source == ProSource.TRIAL.value
        user = session.get(User, grant.user_id)
        language = language_of(user)
        text = t(language, "pro_trial_ending" if trial else "pro_ending").format(date=local_date(grant.ends_at))
        button = {"text": t(language, "btn_pro" if trial else "btn_pro_renew"), "url": mini_app_link(PRO_START)}
        try:
            send_message(user.telegram_id, text, {"inline_keyboard": [[button]]})
            told += 1
        except RuntimeError as error:
            # Someone who never started the bot cannot be written to; asking
            # again every minute would not change that.
            logger.info("Could not tell %s that Pro is ending: %s", user.id, error)
        grant.ending_noted_at = now
        session.add(grant)
    session.commit()
    return told
