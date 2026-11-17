"""Pro and reminders in the bot's chat.

The offer lists what Pro gives and a button per plan that opens Telegram's own
payment for it; the payment then arrives on the webhook like one made in the
app. A bill's card, opened by its owner, says who has not paid yet and lets
them be reminded — everyone at once or one by one — the way the app does,
through the same queue. Without Pro, reminding offers Pro instead.

What this draws goes into the chat's panel; drawing it there is the flow's job.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape

from fastapi import HTTPException
from sqlmodel import Session

from app.models import Bill, BillStatus, BillUser, ProPlan, User
from app.repositories.bill_repo import BillRepository
from app.services.bill_summary import seat_name
from app.services.bot_panel import View
from app.services.pro import PLAN_MONTHS, PRO_START, ProService, local_date
from app.services.product_events import ProductEvent, Surface, capture
from app.services.reminder_policy import next_reminder_at
from app.services.reminder_service import ReminderService, Skip
from app.utils.bot_copy import t
from app.utils.currency import format_amount
from app.utils.keyboard import in_pairs
from app.utils.local_time import local_zone
from app.utils.telegram import answer_callback_query, create_invoice_link, mini_app_link

logger = logging.getLogger(__name__)

PRO_CALLBACK = "pro:offer"
# Reminding tapped without Pro: the offer, saying why it came.
PRO_REMINDERS_CALLBACK = "pro:reminders"
# remind:<token> reminds everyone who owes; remind:<token>:<seat> one of them.
REMIND_PREFIX = "remind:"
# More than this many people owing, and the rest are reminded all together.
SEAT_BUTTONS = 8


@dataclass
class OwnerCard:
    """What a bill's card adds for its owner: who has not paid, and the
    buttons to remind them."""

    text: str | None = None
    rows: list[list[dict]] = field(default_factory=list)


class BotPro:
    def __init__(self, session: Session):
        self.session = session
        self.pro = ProService(session)
        self.reminders = ReminderService(session)
        self.bills = BillRepository(session)

    def handles(self, data: str) -> bool:
        return data in (PRO_CALLBACK, PRO_REMINDERS_CALLBACK) or data.startswith(REMIND_PREFIX)

    def press(self, callback_id: str, data: str, user: User, language: str, now: datetime) -> View | None:
        """Answers the tap; the offer, when that is what the tap opens."""
        if data.startswith(REMIND_PREFIX):
            return self._remind(callback_id, data.removeprefix(REMIND_PREFIX), user, language, now)
        answer_callback_query(callback_id)
        return self.offer(user, language, now, locked=data == PRO_REMINDERS_CALLBACK)

    # ── The offer ────────────────────────────────────────────────────────────

    def offer(self, user: User, language: str, now: datetime, locked: bool = False) -> View:
        """What Pro gives — or until when they have it — and a button per plan.
        `locked`: they came from something Pro opens, so say so first."""
        status = self.pro.status(user.id, now)
        plans = [plan for plan in ProPlan if not (plan is ProPlan.MONTH and status.subscription)]
        prices = self.pro.price_list(user.id, now)

        blocks = [t(language, "pro_reminders_locked")] if locked else []
        if status.active:
            key = "pro_active_subscription" if status.subscription else "pro_active"
            blocks.append(t(language, key).format(date=local_date(status.until)))
        else:
            blocks.append(t(language, "pro_offer"))
            capture(user.id, ProductEvent.PAYWALL_OPENED, Surface.BOT, reason="reminders" if locked else "general")
        lines = [f"<b>{t(language, 'pro_plans_title')}</b>"]
        lines += [_plan_line(plan, prices[plan].stars, prices[plan].was, language) for plan in plans]
        blocks += ["\n".join(lines), t(language, "pro_pay_hint")]

        rows = []
        for plan, link in self._invoice_links(user, plans, language, now).items():
            if link:
                label = t(language, "btn_pro_plan").format(plan=t(language, f"pro_plan_{plan.value}"), stars=prices[plan].stars)
                rows.append([{"text": label, "url": link}])
        rows.append([{"text": t(language, "btn_pro_in_app"), "url": mini_app_link(PRO_START)}])
        return View("\n\n".join(blocks), rows, screen="pro")

    def _invoice_links(self, user: User, plans: list[ProPlan], language: str, now: datetime) -> dict[ProPlan, str | None]:
        """A payment link per plan. Each is a call to Telegram, so they are asked
        for side by side rather than one after another."""
        invoices = {plan: self.pro.invoice(user, plan, language, now) for plan in plans}
        with ThreadPoolExecutor(max_workers=len(invoices)) as pool:
            return dict(zip(invoices, pool.map(_invoice_link, invoices.values())))

    # ── The owner's card ─────────────────────────────────────────────────────

    def owner_card(self, bill: Bill, user: User, language: str, now: datetime) -> OwnerCard:
        if bill.owner_id != user.id or bill.status != BillStatus.OPEN:
            return OwnerCard()
        owing = self.reminders.owing(bill, self.bills.get_participants_by_bill_id(bill.id))
        if not owing:
            return OwnerCard()

        unpaid = "\n".join([f"<b>{t(language, 'card_unpaid')}</b>"] + [
            f"⏳ {escape(_name(seat, language))} — {format_amount(seat.allocated_amount, bill.currency, language)}"
            for seat in owing
        ])
        # A guest's seat has nobody behind it to write to.
        remindable = [seat for seat in owing if seat.user_id is not None]
        if not remindable:
            return OwnerCard(text=unpaid)
        if not self.pro.is_pro(user.id, now):
            locked = [[{"text": t(language, "btn_remind_all_locked"), "callback_data": PRO_REMINDERS_CALLBACK}]]
            return OwnerCard(text=unpaid, rows=locked)

        rows = [[{"text": t(language, "btn_remind_all"), "callback_data": f"{REMIND_PREFIX}{bill.public_token}"}]]
        if len(remindable) > 1:
            rows += in_pairs([
                {
                    "text": t(language, "btn_remind_one").format(name=_name(seat, language)),
                    "callback_data": f"{REMIND_PREFIX}{bill.public_token}:{seat.id}",
                }
                for seat in remindable[:SEAT_BUTTONS]
            ])
        return OwnerCard(text=unpaid, rows=rows)

    def _remind(self, callback_id: str, target: str, user: User, language: str, now: datetime) -> View | None:
        token, _, seat_id = target.partition(":")
        bill = self.bills.get_by_token(token)
        if bill is None or bill.deleted_at is not None or bill.owner_id != user.id or (seat_id and not seat_id.isdigit()):
            answer_callback_query(callback_id, t(language, "errors_bill_not_found"), show_alert=True)
            return None
        if not self.pro.is_pro(user.id, now):
            # A card drawn while they had Pro.
            answer_callback_query(callback_id)
            return self.offer(user, language, now, locked=True)
        try:
            requested = self.reminders.request_for_bill(bill.id, user.id, int(seat_id) if seat_id else None, now)
        except HTTPException as error:
            self.session.rollback()
            key = "share_closed" if error.status_code == 409 else "share_action_failed"
            answer_callback_query(callback_id, t(language, key), show_alert=True)
            return None
        capture(
            user.id,
            ProductEvent.REMINDERS_SENT,
            Surface.BOT,
            bill_id=bill.id,
            scope="seat" if seat_id else "bill",
            queued=len(requested.queued),
            **{"from": "bot"},
        )

        if len(requested.queued) == 1:
            seat = self.bills.get_participant_by_id(requested.queued[0].participant_id)
            answer_callback_query(callback_id, t(language, "remind_queued_one").format(name=_name(seat, language)))
        elif requested.queued:
            answer_callback_query(callback_id, t(language, "remind_queued_many").format(n=len(requested.queued)))
        else:
            answer_callback_query(callback_id, self._why_nobody(bill, requested.skipped, language, now), show_alert=True)
        return None

    def _why_nobody(self, bill: Bill, skipped: dict[int, Skip], language: str, now: datetime) -> str:
        waiting = [seat_id for seat_id, reason in skipped.items() if reason is Skip.COOLDOWN]
        if not waiting:
            return t(language, "remind_nobody")
        latest = self.reminders.latest_by_seat([bill.id])
        soonest = min(next_reminder_at(latest.get(seat_id), now) or now for seat_id in waiting)
        return t(language, "remind_wait").format(time=_local_time(soonest))


def _invoice_link(invoice: dict) -> str | None:
    try:
        return create_invoice_link(invoice)
    except RuntimeError as error:
        logger.warning("No invoice link for %s: %s", invoice["payload"], error)
        return None


def _plan_line(plan: ProPlan, stars: int, was: int | None, language: str) -> str:
    price = f"<s>{was}</s> {stars} ⭐" if was and was > stars else f"{stars} ⭐"
    if plan is ProPlan.MONTH:
        extra = t(language, "pro_plan_renews")
    else:
        extra = t(language, "pro_plan_per_month").format(stars=round(stars / PLAN_MONTHS[plan]))
    return f"{t(language, f'pro_plan_{plan.value}')} — {price} · {extra}"


def _name(seat: BillUser, language: str) -> str:
    return seat_name(seat) or t(language, "share_guest").format(n=seat.seat_index)


def _local_time(moment: datetime) -> str:
    return moment.replace(tzinfo=timezone.utc).astimezone(local_zone()).strftime("%H:%M")
