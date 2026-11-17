"""Telegram's updates, from the webhook to the bot's worker.

The webhook stores an update and answers at once, so a slow Telegram holds up
only the bot, never the API. The worker then takes updates lane by lane: the
first unfinished update of a lane, and only while no other update of that lane
is in hand, so one chat's messages or the taps on one post are handled one at
a time in the order Telegram sent them, while different lanes run side by side.

A worker holds what it took for a short while (a lease) and keeps renewing
it as long as it is on it; if it dies, another takes the update again soon
after. Only the worker holding an update says how it went. An update that fails is given up
at once, as it was when the webhook handled it itself — a bug must not repeat
its half-done work — except a payment: its Stars are gone, so it is tried
again, waiting longer each time.
"""
import logging
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import TelegramUpdate
from app.services.bot_updates import BotUpdates
from app.services.share_message import PAID_PREFIX, REFRESH_PREFIX, SEAT_PREFIX
from app.services.shared_bill_service import RESULT_PREFIX

logger = logging.getLogger(__name__)

LEASE = timedelta(seconds=30)
# Replicas take updates one after another, so two cannot take the same lane at
# once. An advisory lock key apart from the scheduler's 815_0xx.
CLAIM_LOCK = 815_100
# A payment that keeps failing is tried again for about forty minutes.
PAYMENT_ATTEMPTS = 10
FIRST_RETRY = timedelta(seconds=5)
LONGEST_RETRY = timedelta(minutes=20)
# Anything else repeats only when the worker on it died; one that keeps taking
# the worker down with it is given up.
INTERRUPTIONS = 3
ERROR_LENGTH = 2000
PAYMENT_LANE = "payment:"


def lane_of(update: dict) -> str:
    """Which updates must keep their order with this one. A payment has a lane
    of its own, so that one being tried again holds up no conversation."""
    callback = update.get("callback_query")
    if callback:
        code = _post_code(callback.get("data") or "")
        if code:
            return f"post:{code}"
        chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
        return f"chat:{chat_id}" if chat_id else f"inline:{callback.get('inline_message_id')}"
    chosen = update.get("chosen_inline_result")
    if chosen:
        result_id = chosen.get("result_id") or ""
        if result_id.startswith(RESULT_PREFIX):
            return f"post:{result_id.removeprefix(RESULT_PREFIX)}"
        return f"user:{(chosen.get('from') or {}).get('id')}"
    member = update.get("my_chat_member")
    if member:
        return f"chat:{(member.get('chat') or {}).get('id')}"
    message = update.get("message") or {}
    if message.get("successful_payment"):
        return f"{PAYMENT_LANE}{(message.get('from') or {}).get('id')}"
    chat_id = (message.get("chat") or {}).get("id")
    return f"chat:{chat_id}" if chat_id else f"update:{update.get('update_id')}"


def _post_code(data: str) -> str | None:
    """The invite code a post's button carries: every copy of a post shares it."""
    for prefix in (REFRESH_PREFIX, SEAT_PREFIX, PAID_PREFIX):
        if data.startswith(prefix):
            return data.removeprefix(prefix).split(":")[0] or None
    return None


def _is_paid(payload: dict) -> bool:
    return bool((payload.get("message") or {}).get("successful_payment"))


class TelegramUpdateQueue:
    def __init__(self, session: Session):
        self.session = session

    def accept(self, update: dict, now: datetime) -> bool:
        """Keep an update for the worker. False when there is nothing new to
        handle: no id, or one already kept — Telegram delivers again whatever
        it is not sure we got."""
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            logger.warning("Ignoring an update without an id: %s", list(update))
            return False
        if self.session.get(TelegramUpdate, update_id):
            return False
        self.session.add(TelegramUpdate(update_id=update_id, lane=lane_of(update), payload=update, received_at=now))
        try:
            self.session.commit()
        except IntegrityError:
            # The same update, delivered twice at once.
            self.session.rollback()
            return False
        return True

    def claim(
        self, now: datetime, limit: int, *, holder: str, busy_lanes: frozenset[str] = frozenset(),
    ) -> dict[int, str]:
        """Take up to `limit` updates to handle, each with its lane: the first
        unfinished one of a lane no one is on, unless it waits to be tried
        again — in Telegram's order. `busy_lanes` are
        the ones this worker is still on, should its lease have run out."""
        self._one_claim_at_a_time()
        first_of_lane = (
            select(func.min(TelegramUpdate.update_id).label("update_id"))
            .where(TelegramUpdate.done_at.is_(None))
            .group_by(TelegramUpdate.lane)
            .subquery()
        )
        # An update of the lane is in hand — maybe not the first: Telegram may
        # deliver an earlier one only after a later one was already taken.
        held_lanes = select(TelegramUpdate.lane).where(
            TelegramUpdate.done_at.is_(None), TelegramUpdate.claimed_until > now,
        )
        candidates = self.session.exec(
            select(TelegramUpdate.update_id, TelegramUpdate.lane)
            .join(first_of_lane, first_of_lane.c.update_id == TelegramUpdate.update_id)
            .where(
                or_(TelegramUpdate.not_before.is_(None), TelegramUpdate.not_before <= now),
                TelegramUpdate.lane.not_in(held_lanes),
                TelegramUpdate.lane.not_in(sorted(busy_lanes)),
            )
            .order_by(TelegramUpdate.update_id)
            .limit(limit)
        ).all()

        claimed = {}
        for update_id, lane in candidates:
            # Unless a worker finished it meanwhile: finishing takes no lock.
            taken = self.session.execute(
                sa.update(TelegramUpdate)
                .where(TelegramUpdate.update_id == update_id, TelegramUpdate.done_at.is_(None))
                .values(claimed_until=now + LEASE, claimed_by=holder, attempts=TelegramUpdate.attempts + 1)
            )
            if taken.rowcount:
                claimed[update_id] = lane
        self.session.commit()
        return claimed

    def _one_claim_at_a_time(self) -> None:
        """Held to the end of the claim's transaction. SQLite, in the tests,
        has a single writer anyway."""
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CLAIM_LOCK})

    def hold(self, update_ids: list[int], now: datetime, *, holder: str) -> None:
        """Renew the lease on what this worker is still on."""
        self.session.execute(
            sa.update(TelegramUpdate)
            .where(
                TelegramUpdate.update_id.in_(update_ids),
                TelegramUpdate.claimed_by == holder,
                TelegramUpdate.done_at.is_(None),
            )
            .values(claimed_until=now + LEASE)
        )
        self.session.commit()

    def handle(self, update_id: int, *, holder: str) -> None:
        """Handle an update this worker has claimed, and say how it went."""
        kept = self.session.get(TelegramUpdate, update_id)
        if kept.done_at or kept.claimed_by != holder:
            logger.warning("Telegram update %s was taken over before it was handled", update_id)
            return
        payload = kept.payload
        if kept.attempts > (PAYMENT_ATTEMPTS if _is_paid(payload) else INTERRUPTIONS):
            logger.error("Giving up on Telegram update %s: its worker stopped every time", update_id)
            self._record(update_id, holder, done=True, error="Its worker stopped every time it was taken")
            return
        try:
            BotUpdates(self.session).handle(payload)
        except Exception as error:  # noqa: BLE001 — whatever went wrong is recorded below
            self.session.rollback()
            self._failed(update_id, holder, payload, error)
            return
        self._record(update_id, holder, done=True, error=None)

    def _failed(self, update_id: int, holder: str, payload: dict, error: Exception) -> None:
        attempts = self.session.get(TelegramUpdate, update_id).attempts
        if not _is_paid(payload) or attempts >= PAYMENT_ATTEMPTS:
            logger.error("Giving up on Telegram update %s", update_id, exc_info=error)
            self._record(update_id, holder, done=True, error=repr(error))
            return
        wait = min(FIRST_RETRY * 2 ** (attempts - 1), LONGEST_RETRY)
        logger.warning("A payment in update %s failed; trying again in %s", update_id, wait, exc_info=error)
        self._record(update_id, holder, done=False, error=repr(error), not_before=datetime.utcnow() + wait)

    def _record(
        self, update_id: int, holder: str, *, done: bool, error: str | None, not_before: datetime | None = None,
    ) -> None:
        """How it went — unless another worker took it over meanwhile, which
        then has the say."""
        recorded = self.session.execute(
            sa.update(TelegramUpdate)
            .where(
                TelegramUpdate.update_id == update_id,
                TelegramUpdate.claimed_by == holder,
                TelegramUpdate.done_at.is_(None),
            )
            .values(
                done_at=datetime.utcnow() if done else None,
                not_before=not_before,
                claimed_until=None,
                claimed_by=None,
                error=error[:ERROR_LENGTH] if error else None,
            )
        )
        self.session.commit()
        if not recorded.rowcount:
            logger.warning("Telegram update %s was taken over while it was handled", update_id)
