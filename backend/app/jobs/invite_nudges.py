"""Hands the invite to an owner whose bill nobody has joined.

A bill shared with the table is one people come back to: its owner to see who
paid, its guests to pay. A bill nobody was invited to is forgotten by the next
morning, so a couple of hours in, the bot gives its owner the invite to forward
— once, and not in the middle of the night.
"""
from datetime import datetime, timedelta
from functools import partial
from html import escape

from sqlalchemy import exists
from sqlmodel import Session, select

from app.models import Bill, BillStatus, BillUser, User
from app.repositories.user_repo import UserRepository
from app.services.owner_messages import Message, tell_owner
from app.services.product_events import ProductEvent
from app.services.user_service import UserService
from app.utils.bill_card import invite_button, open_bill_button
from app.utils.bot_copy import t
from app.utils.quiet_hours import in_quiet_hours

NUDGE_AFTER = timedelta(hours=2)
# Past this the dinner is long over, and an invite would only be noise.
NUDGE_WINDOW = timedelta(hours=24)


def run(session: Session, now: datetime | None = None) -> int:
    """One tick. Returns how many owners were handed the invite."""
    now = now or datetime.utcnow()
    if in_quiet_hours(now):
        return 0
    seat = BillUser.bill_id == Bill.id
    # Only bills laid for other people with none of their seats taken yet come
    # back: those with guests are never stamped, and would be read every
    # minute for a whole day.
    bills = session.exec(
        select(Bill).where(
            Bill.status == BillStatus.OPEN,
            Bill.deleted_at.is_(None),
            Bill.is_demo.is_(False),
            Bill.invite_nudged_at.is_(None),
            Bill.created_at <= now - NUDGE_AFTER,
            Bill.created_at > now - NUDGE_WINDOW,
            exists().where(seat, BillUser.user_id.is_(None)),
            ~exists().where(seat, BillUser.user_id.is_not(None), BillUser.user_id != Bill.owner_id),
        )
    ).all()
    users = UserService(UserRepository(session))
    nudged = 0
    for bill in bills:
        # Said once, whatever becomes of the message.
        bill.invite_nudged_at = now
        session.add(bill)
        session.commit()
        owner = session.get(User, bill.owner_id)
        if tell_owner(users, bill, owner, ProductEvent.INVITE_NUDGE_RESULT, partial(_nudge, bill)):
            nudged += 1
    return nudged


def _nudge(bill: Bill, language: str) -> Message:
    title = escape(bill.title or t(language, "bill_untitled"))
    markup = {"inline_keyboard": [
        [invite_button(bill.public_token, language)],
        [open_bill_button(bill.public_token, language)],
    ]}
    return t(language, "invite_nudge").format(title=title), markup
