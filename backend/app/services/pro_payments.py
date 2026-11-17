"""The bot's side of buying Pro: Telegram asks whether to take a payment, then
reports that it went through — for the first month of a subscription and for
every renewal after it alike. A second subscription, started while one still
renews, is given back: its Stars refunded and its renewal stopped."""
import logging
from datetime import datetime

from sqlmodel import Session, select

from app.models import User
from app.services.pro import ProService, local_date
from app.services.pro_admin import ProAdminService
from app.services.product_events import ProductEvent, Surface, capture
from app.services.shared_bill_service import language_of
from app.utils.bot_copy import DEFAULT_LANGUAGE, t
from app.utils.telegram import answer_pre_checkout_query, send_message

logger = logging.getLogger(__name__)


class ProPayments:
    def __init__(self, session: Session):
        self.session = session
        self.pro = ProService(session)

    def _language(self, telegram_id: int | None) -> str:
        user = self.session.exec(select(User).where(User.telegram_id == telegram_id)).first() if telegram_id else None
        return language_of(user) if user else DEFAULT_LANGUAGE

    def answer_checkout(self, query: dict, now: datetime) -> None:
        payer = (query.get("from") or {}).get("id")
        problem = self.pro.checkout_problem(
            query.get("invoice_payload") or "", payer, query.get("currency") or "", query.get("total_amount") or 0, now,
        )
        answer_pre_checkout_query(query["id"], t(self._language(payer), problem) if problem else None)

    def paid(self, message: dict, now: datetime) -> None:
        payer = (message.get("from") or {}).get("id")
        payment = message.get("successful_payment") or {}
        reported_before = self.pro.payment_recorded(payment.get("telegram_payment_charge_id"))
        grant = self.pro.record_payment(payer, payment, now)
        if grant is None or grant.refunded_at:
            # Not for Pro, or given back already and reported again.
            return
        if not reported_before:
            capture(
                grant.user_id, ProductEvent.PRO_PURCHASED, Surface.SERVER,
                plan=grant.plan, stars=grant.stars, source=grant.source,
                renewal=bool(payment.get("is_recurring") and not payment.get("is_first_recurring")),
            )
        chat_id = (message.get("chat") or {}).get("id")
        language = self._language(payer)
        if self.pro.is_second_subscription(grant, now):
            # Not caught: a refund that failed comes again with the payment.
            ProAdminService(self.session).refund(grant.id, now)
            self._tell(chat_id, t(language, "pro_second_subscription"))
            return
        until = self.pro.status(grant.user_id, now).until or grant.ends_at
        self._tell(chat_id, t(language, "pro_thanks").format(date=local_date(until)))

    def _tell(self, chat_id: int | None, text: str) -> None:
        try:
            send_message(chat_id, text)
        except RuntimeError as error:
            logger.warning("Could not tell chat %s about a payment: %s", chat_id, error)
