"""Sends queued announcements to everyone the bot can still write to.

Delivery rows are materialised up front and each one is marked as it goes out,
so the job is resumable: a restart in the middle picks up where it stopped
instead of messaging the first few thousand people again.
"""
import logging
import os
import time
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlmodel import Session, select

from app.models import Broadcast, BroadcastDelivery, BroadcastFormat, BroadcastStatus, DeliveryStatus, User
from app.services.product_events import ProductEvent, Surface, capture
from app.utils.telegram import (
    is_unreachable_chat,
    largest_photo_file_id,
    send_message,
    send_photo,
    send_rich_message,
)

logger = logging.getLogger(__name__)

# Telegram allows ~30 messages/second to different chats; leave headroom.
MESSAGES_PER_SECOND = 25
# How many go out per tick — the loop returns to the scheduler between batches.
BATCH_SIZE = 200
ACTIVE_WINDOW_DAYS = 30


def _audience_query(session: Session, broadcast: Broadcast):
    query = select(User).where(User.telegram_id.is_not(None))
    if broadcast.audience == "active_30d":
        cutoff = datetime.utcnow() - timedelta(days=ACTIVE_WINDOW_DAYS)
        query = query.where(User.updated_at >= cutoff)
    elif broadcast.audience == "selected":
        # Recipients were resolved when the broadcast was created.
        query = query.where(User.id.in_(broadcast.target_user_ids or [-1]))
    return query


def _materialise(session: Session, broadcast: Broadcast) -> None:
    """Freeze the recipient list before sending anything.

    Doing it once means the audience can't drift mid-send, and the unique index
    on (broadcast, user) makes a repeat run a no-op rather than a double send.
    """
    existing = {
        row.user_id
        for row in session.exec(
            select(BroadcastDelivery).where(BroadcastDelivery.broadcast_id == broadcast.id)
        ).all()
    }

    created = 0
    for user in session.exec(_audience_query(session, broadcast)).all():
        if user.id in existing:
            continue
        # A hand-picked recipient is sent to even if they blocked the bot before:
        # the operator asked for this person specifically, and Telegram will say
        # if it still can't be delivered.
        if broadcast.audience != "selected" and (user.settings or {}).get("bot_blocked"):
            continue
        session.add(BroadcastDelivery(broadcast_id=broadcast.id, user_id=user.id))
        created += 1

    broadcast.total_count = len(existing) + created
    broadcast.status = BroadcastStatus.SENDING
    session.add(broadcast)
    session.commit()


def button_markup(text: str | None, url: str | None) -> dict | None:
    if not (text and url):
        return None
    return {"inline_keyboard": [[{"text": text, "url": url}]]}


def send_broadcast_message(
    chat_id: int,
    text: str,
    *,
    message_format: str,
    markup: dict | None,
    parse_mode: str | None = "HTML",
    photo: str | None = None,
    photo_path: str | None = None,
) -> dict:
    """One broadcast message to one chat, exactly as every recipient gets it —
    the panel's test send goes through here too. `photo` is a file_id Telegram
    already holds, `photo_path` a picture still to upload; a rich message has
    its pictures inside the text and takes neither."""
    if message_format == BroadcastFormat.RICH:
        return send_rich_message(chat_id, text, reply_markup=markup)
    if photo or photo_path:
        return send_photo(
            chat_id,
            photo=photo,
            photo_path=photo_path,
            caption=text,
            reply_markup=markup,
            parse_mode=parse_mode or "HTML",
        )
    return send_message(chat_id, text, reply_markup=markup, parse_mode=parse_mode)


def _text_for(broadcast: Broadcast, user: User) -> str:
    body = broadcast.body or {}
    lang = (user.settings or {}).get("language", "ru")
    return body.get(lang) or body.get("ru") or body.get("en") or broadcast.title


def run(session: Session, sleep=time.sleep, now: datetime | None = None) -> int:
    """One tick. Returns how many messages went out."""
    now = now or datetime.utcnow()
    broadcast = session.exec(
        select(Broadcast).where(
            Broadcast.status.in_([BroadcastStatus.QUEUED, BroadcastStatus.SENDING]),
            # A broadcast waiting for its slot is invisible to this query, so it
            # holds up nothing — later ones go out on time and it joins the queue
            # once due. `scheduled_at` is naive UTC, like `now`.
            or_(Broadcast.scheduled_at.is_(None), Broadcast.scheduled_at <= now),
        ).order_by(Broadcast.id)
    ).first()
    if not broadcast:
        return 0

    if broadcast.status == BroadcastStatus.QUEUED:
        _materialise(session, broadcast)

    pending = session.exec(
        select(BroadcastDelivery)
        .where(
            BroadcastDelivery.broadcast_id == broadcast.id,
            BroadcastDelivery.status == DeliveryStatus.PENDING,
        )
        .limit(BATCH_SIZE)
    ).all()

    if not pending:
        broadcast.status = BroadcastStatus.DONE
        session.add(broadcast)
        session.commit()
        return 0

    markup = button_markup(broadcast.button_text, broadcast.button_url)

    try:
        sent = _deliver(session, broadcast, pending, markup, sleep)
    except Exception:
        # Statuses set so far are the record of who already got the message;
        # losing them would send it to those people twice.
        session.commit()
        raise

    # A short batch means the list is exhausted; finish here rather than burning
    # an idle tick before the next broadcast can start.
    if len(pending) < BATCH_SIZE:
        broadcast.status = BroadcastStatus.DONE

    session.add(broadcast)
    session.commit()
    return sent


def _passing(exc: RuntimeError) -> bool:
    """Not Telegram turning this message down: the request never got an answer,
    the token is missing, or Telegram asked to slow down."""
    message = str(exc)
    return not message.startswith("Telegram error:") or "Too Many Requests" in message


def _deliver(
    session: Session,
    broadcast: Broadcast,
    pending: list[BroadcastDelivery],
    markup: dict | None,
    sleep,
) -> int:
    sent = 0
    for delivery in pending:
        user = session.get(User, delivery.user_id)
        if not user or not user.telegram_id:
            delivery.status = DeliveryStatus.FAILED
            delivery.error = "no telegram id"
            session.add(delivery)
            _count(broadcast, delivery)
            continue

        uploading = bool(broadcast.photo_path) and not broadcast.photo_file_id
        try:
            result = send_broadcast_message(
                user.telegram_id,
                _text_for(broadcast, user),
                message_format=broadcast.format,
                markup=markup,
                parse_mode=broadcast.parse_mode,
                photo=broadcast.photo_file_id if broadcast.photo_path else None,
                photo_path=broadcast.photo_path if uploading else None,
            )
            if uploading:
                broadcast.photo_file_id = largest_photo_file_id(result)
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = datetime.utcnow()
            broadcast.sent_count += 1
            sent += 1
            if (user.settings or {}).get("bot_blocked"):
                # They came back. Nothing else ever clears this, and while it is
                # set the person is invisible to every feature that asks whether
                # the bot can reach them.
                user.settings = {**user.settings, "bot_blocked": False}
                session.add(user)
        except RuntimeError as exc:
            # Only Telegram's own refusals count as a delivery failure. A bug in
            # this job would otherwise be recorded as ten thousand individual
            # rejections and never noticed.
            if is_unreachable_chat(exc):
                delivery.status = DeliveryStatus.BLOCKED
                # Remember it on the user so later broadcasts skip them entirely.
                user.settings = {**(user.settings or {}), "bot_blocked": True}
                session.add(user)
            elif _passing(exc):
                # A network blip or a flood wait says nothing about this person:
                # the delivery stays pending and the next tick tries again.
                raise
            else:
                delivery.status = DeliveryStatus.FAILED
            delivery.error = str(exc)[:500]
            broadcast.failed_count += 1

        session.add(delivery)
        # Kept as it goes: a deploy kills the container mid-batch, and a status
        # lost then is a message sent to the same person twice.
        session.commit()
        _count(broadcast, delivery)
        sleep(1 / MESSAGES_PER_SECOND)

    return sent


def _count(broadcast: Broadcast, delivery: BroadcastDelivery) -> None:
    """How the broadcast ended for its recipient, so whoever came back after it shows."""
    status = DeliveryStatus(delivery.status)
    capture(
        delivery.user_id,
        ProductEvent.BROADCAST_RESULT,
        Surface.SERVER,
        broadcast_id=broadcast.id,
        ok=status is DeliveryStatus.SENT,
        status=status.value,
    )
