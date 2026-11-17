"""Tells an owner who has paid them.

The owner is the one waiting on the money, and the app only shows it to them
when they open it. The bot says it as it happens — who paid, and how many have
so far — which is what brings them back to a bill until it is settled. A seat
the owner marked paid themselves is no news to them, and is never sent.
"""
from datetime import datetime, timedelta
from functools import partial
from html import escape

from sqlmodel import Session, select

from app.models import Bill, BillUser, User
from app.repositories.user_repo import UserRepository
from app.services.bill_summary import seat_name
from app.services.owner_messages import Message, tell_owner
from app.services.product_events import ProductEvent
from app.services.user_service import UserService
from app.utils.bill_card import open_bill_button
from app.utils.bot_copy import t

# A payment older than this is stale news; the window only bounds a backlog.
NEWS_WINDOW = timedelta(hours=24)


def run(session: Session, now: datetime | None = None) -> int:
    """One tick. Returns how many owners were told."""
    now = now or datetime.utcnow()
    rows = session.exec(
        select(Bill, BillUser)
        .join(BillUser, BillUser.bill_id == Bill.id)
        .where(
            BillUser.is_paid.is_(True),
            BillUser.owner_told_at.is_(None),
            BillUser.paid_at >= now - NEWS_WINDOW,
            BillUser.user_id != Bill.owner_id,
            Bill.deleted_at.is_(None),
            Bill.is_demo.is_(False),
        )
        .order_by(BillUser.paid_at)
    ).all()
    news: dict[int, tuple[Bill, list[BillUser]]] = {}
    for bill, seat in rows:
        news.setdefault(bill.id, (bill, []))[1].append(seat)

    users = UserService(UserRepository(session))
    told = 0
    for bill, paid in news.values():
        # Told once, whatever becomes of the message.
        for seat in paid:
            seat.owner_told_at = now
            session.add(seat)
        session.commit()
        owner = session.get(User, bill.owner_id)
        if tell_owner(users, bill, owner, ProductEvent.PAYMENT_NOTICE_RESULT, partial(_notice, session, bill, paid)):
            told += 1
    return told


def _notice(session: Session, bill: Bill, paid: list[BillUser], language: str) -> Message:
    return _text(session, bill, paid, language), {"inline_keyboard": [[open_bill_button(bill.public_token, language)]]}


def _text(session: Session, bill: Bill, paid: list[BillUser], language: str) -> str:
    seats = session.exec(select(BillUser).where(BillUser.bill_id == bill.id)).all()
    payers = [seat for seat in seats if seat.user_id != bill.owner_id and seat.allocated_amount > 0]
    settled = sum(1 for seat in payers if seat.is_paid)
    names = ", ".join(
        escape(seat_name(seat) or t(language, "share_guest").format(n=seat.seat_index)) for seat in paid
    )
    title = escape(bill.title or t(language, "bill_untitled"))
    tally = (
        t(language, "payment_notice_all")
        if settled == len(payers)
        else t(language, "payment_notice_count").format(paid=settled, total=len(payers))
    )
    return f"{t(language, 'payment_notice').format(title=title, names=names)}\n{tally}"
