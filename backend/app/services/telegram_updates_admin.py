"""The bot's queue as the admin sees it: what waits, what is in hand, what
failed — and what can be done about a failure: run it again once the cause is
fixed, or, for a payment given up on, mark it settled by hand once its Stars
are back or its Pro is given.
"""
from datetime import datetime, timedelta
from enum import Enum

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from app.models import TelegramUpdate
from app.schemas.admin_schemas import AdminBotQueue, AdminBotUpdate, AdminBotUpdatesPage
from app.services.share_message import PAID_PREFIX, REFRESH_PREFIX, SEAT_PREFIX
from app.services.telegram_updates import PAYMENT_LANE

TEXT_SHOWN = 120


class QueueView(str, Enum):
    QUEUE = "queue"
    FAILED = "failed"
    PAYMENTS = "payments"
    ALL = "all"


class UpdateState(str, Enum):
    WAITING = "waiting"
    IN_HAND = "in_hand"
    RETRY_LATER = "retry_later"
    HANDLED = "handled"
    FAILED = "failed"
    SETTLED = "settled"


class UpdateAction(str, Enum):
    RETRY = "retry"
    SETTLE = "settle"


UNFINISHED = TelegramUpdate.done_at.is_(None)
GIVEN_UP = and_(TelegramUpdate.done_at.is_not(None), TelegramUpdate.error.is_not(None))
UNSETTLED_PAYMENT = and_(GIVEN_UP, TelegramUpdate.lane.startswith(PAYMENT_LANE), TelegramUpdate.settled_at.is_(None))


class TelegramUpdatesAdmin:
    def __init__(self, session: Session):
        self.session = session

    def queue(self, now: datetime, slots: int) -> AdminBotQueue:
        return AdminBotQueue(
            slots=slots,
            waiting=self._count(
                UNFINISHED,
                or_(TelegramUpdate.claimed_until.is_(None), TelegramUpdate.claimed_until <= now),
                or_(TelegramUpdate.not_before.is_(None), TelegramUpdate.not_before <= now),
            ),
            in_hand=self._count(UNFINISHED, TelegramUpdate.claimed_until > now),
            retrying=self._count(UNFINISHED, TelegramUpdate.not_before > now),
            oldest_waiting_at=self.session.exec(select(func.min(TelegramUpdate.received_at)).where(UNFINISHED)).one(),
            handled_last_hour=self._count(TelegramUpdate.done_at >= now - timedelta(hours=1), TelegramUpdate.error.is_(None)),
            failed_last_day=self._count(GIVEN_UP, TelegramUpdate.done_at >= now - timedelta(days=1)),
            unsettled_payments=self._count(UNSETTLED_PAYMENT),
        )

    def page(self, now: datetime, view: QueueView, q: str | None, limit: int, offset: int) -> AdminBotUpdatesPage:
        conditions = {
            QueueView.QUEUE: [UNFINISHED],
            QueueView.FAILED: [GIVEN_UP],
            QueueView.PAYMENTS: [UNSETTLED_PAYMENT],
            QueueView.ALL: [],
        }[view]
        if q and q.strip():
            conditions.append(TelegramUpdate.lane.contains(q.strip().lstrip("@")))
        # The queue reads in the order it is handled; the rest newest first.
        order = TelegramUpdate.update_id if view is QueueView.QUEUE else TelegramUpdate.update_id.desc()
        rows = self.session.exec(
            select(TelegramUpdate).where(*conditions).order_by(order).offset(offset).limit(limit)
        ).all()
        return AdminBotUpdatesPage(
            items=[_row(kept, now) for kept in rows], total=self._count(*conditions), limit=limit, offset=offset,
        )

    def retry(self, update_id: int, now: datetime) -> AdminBotUpdate:
        """Back into the queue, as if just delivered. Its last error stays in
        view until it goes through."""
        kept = self._get(update_id)
        if UpdateAction.RETRY not in _actions(kept, now):
            raise HTTPException(status_code=409, detail="Only an update given up on can be run again")
        kept.done_at = None
        kept.attempts = 0
        kept.not_before = None
        kept.claimed_until = None
        kept.claimed_by = None
        return self._save(kept, now)

    def settle(self, update_id: int, now: datetime) -> AdminBotUpdate:
        """A payment given up on, put right by hand: it leaves the list of
        payments without Pro, and is forgotten a week later like the rest."""
        kept = self._get(update_id)
        if UpdateAction.SETTLE not in _actions(kept, now):
            raise HTTPException(status_code=409, detail="Only a payment given up on can be settled")
        kept.settled_at = now
        return self._save(kept, now)

    def _count(self, *conditions) -> int:
        return self.session.exec(select(func.count(TelegramUpdate.update_id)).where(*conditions)).one()

    def _get(self, update_id: int) -> TelegramUpdate:
        kept = self.session.get(TelegramUpdate, update_id)
        if kept is None:
            raise HTTPException(status_code=404, detail="Update not found")
        return kept

    def _save(self, kept: TelegramUpdate, now: datetime) -> AdminBotUpdate:
        self.session.add(kept)
        self.session.commit()
        self.session.refresh(kept)
        return _row(kept, now)


def _row(kept: TelegramUpdate, now: datetime) -> AdminBotUpdate:
    kind, who, what = describe(kept.payload)
    return AdminBotUpdate(
        update_id=kept.update_id,
        lane=kept.lane,
        kind=kind,
        who=who,
        what=what,
        received_at=kept.received_at,
        attempts=kept.attempts,
        state=_state(kept, now).value,
        not_before=kept.not_before,
        claimed_until=kept.claimed_until,
        done_at=kept.done_at,
        settled_at=kept.settled_at,
        error=kept.error,
        payload=kept.payload,
        actions=[action.value for action in _actions(kept, now)],
    )


def _state(kept: TelegramUpdate, now: datetime) -> UpdateState:
    if kept.done_at is not None:
        if kept.error is None:
            return UpdateState.HANDLED
        return UpdateState.SETTLED if kept.settled_at else UpdateState.FAILED
    if kept.claimed_until and kept.claimed_until > now:
        return UpdateState.IN_HAND
    if kept.not_before and kept.not_before > now:
        return UpdateState.RETRY_LATER
    return UpdateState.WAITING


def _actions(kept: TelegramUpdate, now: datetime) -> list[UpdateAction]:
    if _state(kept, now) is not UpdateState.FAILED:
        return []
    if kept.lane.startswith(PAYMENT_LANE):
        return [UpdateAction.RETRY, UpdateAction.SETTLE]
    return [UpdateAction.RETRY]


def describe(payload: dict) -> tuple[str, str | None, str | None]:
    """What an update is, from whom, and its gist — for a person to read."""
    callback = payload.get("callback_query")
    if callback:
        data = callback.get("data") or ""
        on_post = data.startswith((REFRESH_PREFIX, SEAT_PREFIX, PAID_PREFIX))
        return ("post_button" if on_post else "button"), _who(callback.get("from")), data
    chosen = payload.get("chosen_inline_result")
    if chosen:
        return "shared_post", _who(chosen.get("from")), chosen.get("result_id")
    member = payload.get("my_chat_member")
    if member:
        return "membership", _who(member.get("from")), (member.get("new_chat_member") or {}).get("status")
    message = payload.get("message")
    if message:
        who = _who(message.get("from"))
        paid = message.get("successful_payment")
        if paid:
            return "payment", who, f"{paid.get('total_amount')} {paid.get('currency')} · {paid.get('invoice_payload')}"
        text = message.get("text") or message.get("caption")
        if message.get("photo"):
            return "photo", who, _short(text)
        if text and text.startswith("/"):
            return "command", who, _short(text)
        return "message", who, _short(text)
    return "other", None, ", ".join(key for key in payload if key != "update_id") or None


def _who(person: dict | None) -> str | None:
    if not person:
        return None
    if person.get("username"):
        return f"@{person['username']}"
    name = person.get("first_name") or ""
    return f"{name} ({person.get('id')})".strip()


def _short(text: str | None) -> str | None:
    if not text:
        return None
    return text if len(text) <= TEXT_SHOWN else f"{text[:TEXT_SHOWN]}…"
