"""What the bot does with an update Telegram delivered.

This only works out what an update is and hands it to whoever owns it:
BotFlowService the conversation, SharedBillService the bills shared into chats,
ProPayments Pro bought with Telegram Stars.
"""
from datetime import datetime

from sqlmodel import Session

from app.repositories.bill_repo import BillRepository
from app.repositories.bot_dialog_repo import BotDialogRepository
from app.repositories.bot_panel_repo import BotPanelRepository
from app.repositories.file_repo import FileAssetRepository
from app.repositories.payment_method_repo import PaymentMethodRepository
from app.repositories.receipt_repo import ReceiptRepository
from app.repositories.user_repo import UserRepository
from app.services.bill_core_service import BillCoreService
from app.services.bot_flow_service import BotFlowService
from app.services.bot_panel import BotPanels
from app.services.bot_pro import BotPro
from app.services.payment_method_service import PaymentMethodService
from app.services.pro_payments import ProPayments
from app.services.receipt_service import ReceiptService
from app.services.scan_allowance import ScanAllowance
from app.services.sender_accounts import SenderAccountService
from app.services.share_message import PAID_PREFIX, REFRESH_PREFIX, SEAT_PREFIX
from app.services.shared_bill_service import POST_START_PREFIX, SharedBillService
from app.services.user_service import UserService
from app.services.voice_bill import VoiceBillService


def is_payment(update: dict) -> bool:
    return "pre_checkout_query" in update or bool((update.get("message") or {}).get("successful_payment"))


class BotUpdates:
    def __init__(self, session: Session):
        user_repo = UserRepository(session)
        bill_repo = BillRepository(session)
        self.flow = BotFlowService(
            dialogs=BotDialogRepository(session),
            panels=BotPanels(BotPanelRepository(session)),
            users=UserService(user_repo),
            bills=BillCoreService(bill_repo, user_repo),
            payments=PaymentMethodService(PaymentMethodRepository(session), user_repo),
            receipts=ReceiptService(ReceiptRepository(session), FileAssetRepository(session)),
            scans=ScanAllowance(session),
            pro=BotPro(session),
            voice=VoiceBillService(bill_repo, user_repo),
        )
        self.shared = SharedBillService(session)
        self.senders = SenderAccountService(session)
        self.payments = ProPayments(session)

    def handle(self, update: dict) -> None:
        checkout = update.get("pre_checkout_query")
        if checkout:
            self.payments.answer_checkout(checkout, datetime.utcnow())
            return

        chosen = update.get("chosen_inline_result")
        if chosen:
            self.shared.chosen(chosen.get("result_id") or "", chosen.get("inline_message_id"))
            return

        callback = update.get("callback_query")
        if callback and (callback.get("data") or "").startswith(REFRESH_PREFIX):
            # A refresh button: under a post sent through inline mode, which reaches
            # us with an inline id and no chat, or under a reminder the bot sent.
            message = callback.get("message") or {}
            self.shared.press_refresh(
                callback_id=callback.get("id"),
                inline_message_id=callback.get("inline_message_id"),
                data=callback["data"],
                from_user=callback.get("from") or {},
                now=datetime.utcnow(),
                chat_id=(message.get("chat") or {}).get("id"),
                message_id=message.get("message_id"),
            )
            return
        if callback and (callback.get("data") or "").startswith((SEAT_PREFIX, PAID_PREFIX)):
            # A seat or «I've paid» under a post: in inline mode it comes with an
            # inline id, from a post the bot sent itself with the chat.
            message = callback.get("message") or {}
            self.shared.press_action(
                callback_id=callback.get("id"),
                data=callback["data"],
                from_user=callback.get("from") or {},
                now=datetime.utcnow(),
                inline_message_id=callback.get("inline_message_id"),
                chat_id=(message.get("chat") or {}).get("id"),
                message_id=message.get("message_id"),
            )
            return
        if callback:
            message = callback.get("message") or {}
            chat_id = (message.get("chat") or {}).get("id")
            if chat_id:
                self.flow.handle_callback(
                    chat_id=chat_id,
                    message_id=message.get("message_id"),
                    callback_id=callback.get("id"),
                    data=callback.get("data") or "",
                    from_user=callback.get("from") or {},
                )
            return

        member = update.get("my_chat_member")
        if member:
            self.flow.handle_chat_member(member)
            return

        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if not chat_id:
            return
        if message.get("successful_payment"):
            self.payments.paid(message, datetime.utcnow())
            return

        from_user = message.get("from") or {}
        # A sender account starts the bot when it is logged in, so the bot knows it;
        # it is a tool of the app, not somebody using it.
        if self.senders.is_sender(from_user.get("id")):
            return
        text = (message.get("text") or "").strip()
        if text.startswith("/"):
            word, _, argument = text.partition(" ")
            # "/bills@SplitTheBillsBot" is how Telegram writes it in groups.
            command = word.lstrip("/").split("@")[0].lower()
            # A post's button opens the bot's private chat with this start.
            private = chat_id == from_user.get("id")
            if command == "start" and private and argument.startswith(POST_START_PREFIX):
                if self.shared.welcome_from_post(chat_id, argument.removeprefix(POST_START_PREFIX), from_user):
                    return
            self.flow.handle_command(chat_id, command, from_user, message.get("message_id"), argument)
            return

        # Anything else only means something to a flow that is waiting for it.
        self.flow.handle_message(chat_id, message, from_user)
