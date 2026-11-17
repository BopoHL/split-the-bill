"""The bot's in-chat conversation.

Telegram delivers every step of a flow as its own update, so this is written as
a state machine: take one update, work out what it means for the chat's stored
step, draw what comes next. The step lives in `bot_dialogs`; what the person
sees lives in the chat's panel (services/bot_panel.py), so the menu, the lists
and the questions of a flow take up one message rather than a new one each.
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from html import escape

from fastapi import HTTPException

from app.models import BillStatus, BotDialog, BotDialogStep, InviteChannel, User
from app.queue_manager import queue_manager
from app.repositories.bot_dialog_repo import BotDialogRepository
from app.schemas.bill_schemas import BillCreate
from app.schemas.user_schemas import UserSettingsUpdate
from app.services.bill_core_service import BillCoreService
from app.services.bot_panel import BotPanels, View
from app.services.bot_pro import PRO_CALLBACK, BotPro
from app.services.payment_method_service import PaymentMethodService
from app.services.pro import PRO_START
from app.services.product_events import ProductEvent, Surface, capture
from app.services.receipt_service import ReceiptService
from app.services.scan_allowance import ScanAllowance, ScanLimitReached
from app.services.shared_bill_service import POST_START_PREFIX, SharedBillService
from app.services.user_service import UserService
from app.services.voice_bill import VoiceBillService
from app.utils.bill_card import INVITE_PREFIX, format_amount, invite_button, open_bill_button, render_bill_card
from app.utils.bot_copy import (
    CURRENCIES,
    CURRENCY_LABELS,
    DEFAULT_LANGUAGE,
    FIRST_LANGUAGE_PROMPT,
    LANGUAGE_NAMES,
    LANGUAGES,
    resolve_language,
    t,
)
from app.utils.bot_intro import guide_plain, guide_rich, welcome_picture
from app.utils.currency import DEFAULT_CURRENCY, normalize_currency
from app.utils.keyboard import in_pairs
from app.utils.sources import source_of
from app.utils.telegram import (
    answer_callback_query,
    bot_link,
    download_file,
    largest_photo_file_id,
    mini_app_link,
    send_message,
    send_photo,
)

logger = logging.getLogger(__name__)

LANGUAGE_PREFIX = "lang:"
# Onboarding asked for a currency once; its buttons still sit in old chats.
CURRENCY_PREFIX = "cur:"
PAYMENT_PREFIX = "pay:"
NEW_BILL_CALLBACK = "bill:new"
CANCEL_BILL_CALLBACK = "bill:cancel"
NEW_PAYMENT_CALLBACK = "pay:new"
MENU_CALLBACK = "menu:main"
# Opened the command list under menus sent before the panel; the menu carries it now.
COMMANDS_CALLBACK = "menu:commands"
GUIDE_CALLBACK = "menu:guide"
SETTINGS_CALLBACK = "menu:settings"
# Settings reuse the onboarding pickers but not its follow-ups, so the taps
# carry their own prefixes.
SETTINGS_LANGUAGE_CALLBACK = "settings:lang"
SETTINGS_CURRENCY_CALLBACK = "settings:cur"
SETTINGS_LANGUAGE_PREFIX = "setlang:"
SETTINGS_CURRENCY_PREFIX = "setcur:"
# Distinct from NEW_BILL_CALLBACK so a public token can never be read as a command.
CARD_PREFIX = "card:"
BILLS_PREFIX = "bills:"
# Which bill a voice message heard outside a flow is for: a public token, or a new one.
VOICE_PREFIX = "voice:"
VOICE_NEW = "new"
# A voice note past this is a speech, not a dinner.
MAX_VOICE_SECONDS = 120
# Open bills offered for a voice message sent outside a flow: the few made
# lately enough to be the meal it is about. Older ones, it starts a new bill.
VOICE_TARGETS = 3
VOICE_FRESH = timedelta(hours=12)

COMMANDS = ("start", "menu", "new", "bills", "settings", "help", "pro")
START_REF_MAX = 64

# A table of fifty is already past what splitting by hand survives; the cap
# exists so a typo can't seed hundreds of seats.
MAX_HEADCOUNT = 50

# Only Uzbek fiscal receipts carry a Soliq QR, so the shortcut is offered
# where it can actually work.
QR_CURRENCY = "uzs"

# Three across is what a phone fits without wrapping a label onto a second line.
CURRENCY_ROW = 3

BILLS_PAGE_SIZE = 10
# A question left unanswered this long is no longer being asked: a photo sent
# a day later is not the receipt of the bill that was waiting for one.
DIALOG_TTL = timedelta(hours=1)
# The bot's place in a private chat once the person has blocked it.
BLOCKED_STATUSES = ("kicked", "left")

# Ownership check for the app store listing: the store sends this command and
# expects the token back verbatim. Deliberately absent from the published
# command list — it is machinery, not a feature.
STORE_VERIFY_COMMAND = "appss_verify"
STORE_VERIFY_TOKEN = "appss_fc0ee6"


def _start_properties(argument: str) -> dict:
    """What a /start link says about where someone came from: a post's button,
    or `src_<channel>` on a link we hand out — a post, an ad, a broadcast."""
    if not argument:
        return {}
    if argument.startswith(POST_START_PREFIX):
        # A post's button, for someone not on its bill; what follows is the
        # post's invite code, which stays out of analytics.
        return {"start": "post"}
    source = source_of(argument)
    if source:
        return {"start": "source", "source": source}
    return {"start_ref": argument[:START_REF_MAX]}


def _currency_keyboard(prefix: str) -> list[list[dict]]:
    """The last row is never left with one button — a lone key under a full row
    reads like a separate question rather than the tail of the same list."""
    buttons = [{"text": CURRENCY_LABELS[code], "callback_data": f"{prefix}{code}"} for code in CURRENCIES]
    rows = [buttons[index : index + CURRENCY_ROW] for index in range(0, len(buttons), CURRENCY_ROW)]
    if len(rows) > 1 and len(rows[-1]) == 1:
        rows[-1].insert(0, rows[-2].pop())
    return rows


def _button(language: str, key: str, callback: str) -> dict:
    return {"text": t(language, key), "callback_data": callback}


def _app_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def _open_app_row(language: str) -> list[list[dict]]:
    url = _app_url()
    return [[{"text": t(language, "btn_open_app"), "web_app": {"url": url}}]] if url else []


class BotFlowService:
    def __init__(
        self,
        dialogs: BotDialogRepository,
        panels: BotPanels,
        users: UserService,
        bills: BillCoreService,
        payments: PaymentMethodService,
        receipts: ReceiptService,
        scans: ScanAllowance,
        pro: BotPro,
        voice: VoiceBillService,
    ):
        self.dialogs = dialogs
        self.panels = panels
        self.users = users
        self.bills = bills
        self.payments = payments
        self.receipts = receipts
        self.scans = scans
        self.pro = pro
        self.voice = voice

    # -- entry points ------------------------------------------------------

    def handle_command(
        self, chat_id: int, command: str, from_user: dict, message_id: int | None = None, argument: str = "",
    ) -> None:
        if command == STORE_VERIFY_COMMAND:
            send_message(chat_id, STORE_VERIFY_TOKEN)
            return
        if command not in COMMANDS:
            return

        start = _start_properties(argument) if command == "start" else {}
        user = self._user_from(from_user, start.get("start", "bot"), start.get("source"))
        if chat_id != from_user.get("id"):
            capture(user.id, ProductEvent.BOT_COMMAND, Surface.BOT, command=command, chat="group")
            self._point_to_private_chat(chat_id, self._language_for(user))
            return
        self.panels.clear_input(chat_id, message_id)
        # Any command leaves a half-finished flow: its question is no longer on screen.
        self.dialogs.clear(chat_id)
        capture(user.id, ProductEvent.BOT_COMMAND, Surface.BOT, command=command, **start)
        if command == "start":
            self._start(chat_id, user)
            return

        language = self._language_for(user)
        if command == "new":
            self.panels.open(chat_id, self._headcount_view(language))
            self._begin_bill(chat_id, user)
        else:
            self._open(chat_id, user, self._command_view(command, user, language))

    def handle_chat_member(self, change: dict) -> None:
        """In a private chat Telegram tells the bot this only when the person
        blocks it, or lets it write again."""
        if (change.get("chat") or {}).get("type") != "private":
            return
        status = (change.get("new_chat_member") or {}).get("status")
        allowed = status not in BLOCKED_STATUSES
        user = self.users.note_write_access(self._user_from(change.get("from") or {}), allowed)
        capture(user.id, ProductEvent.BOT_ACCESS_CHANGED, Surface.BOT, allowed=allowed)

    def handle_callback(
        self, chat_id: int, message_id: int | None, callback_id: str, data: str, from_user: dict
    ) -> None:
        if chat_id != from_user.get("id"):
            # The panel and its flows live in the private chat; a button that
            # made it into a group has nothing to open there.
            answer_callback_query(callback_id)
            return
        user = self._user_from(from_user)
        language = self._language_for(user)
        if self.pro.handles(data):
            # Answers the tap itself: reminding says how it went.
            offer = self.pro.press(callback_id, data, user, language, datetime.utcnow())
            if offer is not None:
                self._show(chat_id, message_id, user, offer.with_rows(self._back_to_menu(language)))
            return
        answer_callback_query(callback_id)

        if data.startswith(LANGUAGE_PREFIX):
            self._accept_language(chat_id, message_id, user, data.removeprefix(LANGUAGE_PREFIX))
        elif data.startswith(CURRENCY_PREFIX):
            self._accept_currency(chat_id, message_id, user, data.removeprefix(CURRENCY_PREFIX))
        elif data in (MENU_CALLBACK, COMMANDS_CALLBACK, CANCEL_BILL_CALLBACK):
            self._show(chat_id, message_id, user, self._menu_view(language))
        elif data == GUIDE_CALLBACK:
            self._show(chat_id, message_id, user, self._guide_view(language))
        elif data == SETTINGS_CALLBACK:
            self._show(chat_id, message_id, user, self._settings_view(language))
        elif data == SETTINGS_LANGUAGE_CALLBACK:
            self._show(chat_id, message_id, user, self._language_picker(language))
        elif data == SETTINGS_CURRENCY_CALLBACK:
            self._show(chat_id, message_id, user, self._currency_picker(language))
        elif data.startswith(SETTINGS_LANGUAGE_PREFIX):
            self._save_language(chat_id, message_id, user, data.removeprefix(SETTINGS_LANGUAGE_PREFIX))
        elif data.startswith(SETTINGS_CURRENCY_PREFIX):
            self._save_currency(chat_id, message_id, user, language, data.removeprefix(SETTINGS_CURRENCY_PREFIX))
        elif data == NEW_BILL_CALLBACK:
            self.panels.tapped(chat_id, message_id, self._headcount_view(language))
            self._begin_bill(chat_id, user)
        elif data == NEW_PAYMENT_CALLBACK:
            self._ask_new_payment(chat_id, message_id, user, language)
        elif data.startswith(INVITE_PREFIX):
            self._post_invite(chat_id, message_id, user, language, data.removeprefix(INVITE_PREFIX))
        elif data.startswith(CARD_PREFIX):
            self._show(chat_id, message_id, user, self._card_view(user, language, data.removeprefix(CARD_PREFIX)))
        elif data.startswith(BILLS_PREFIX):
            offset = data.removeprefix(BILLS_PREFIX)
            self._show(chat_id, message_id, user, self._bills_view(user, language, int(offset) if offset.isdigit() else 0))
        elif data.startswith(PAYMENT_PREFIX):
            self._accept_saved_payment(chat_id, message_id, user, language, data.removeprefix(PAYMENT_PREFIX))
        elif data.startswith(VOICE_PREFIX):
            self._voice_into(chat_id, message_id, user, language, data.removeprefix(VOICE_PREFIX))
        else:
            logger.info("Unhandled callback %r in chat %s", data, chat_id)

    def handle_message(self, chat_id: int, message: dict, from_user: dict) -> None:
        """A plain message. Only meaningful while a flow in the private chat is
        waiting on one; once the panel has taken the answer in, it goes."""
        if chat_id != from_user.get("id"):
            return
        if message.get("voice"):
            self._accept_voice(chat_id, message, from_user)
            return
        dialog = self.dialogs.get_by_chat(chat_id)
        if dialog is None:
            return
        user = self._user_from(from_user)
        language = self._language_for(user)
        # A receipt is still wanted however long it takes: its bill is made.
        stale = dialog.step != BotDialogStep.BILL_RECEIPT and dialog.updated_at < datetime.utcnow() - DIALOG_TTL
        if stale:
            self.dialogs.clear(chat_id)
            # The question it answers is off the table: take it off the screen too.
            self._open(chat_id, user, self._menu_view(language))
            return

        draft = dict(dialog.draft or {})
        text = (message.get("text") or "").strip()

        kept = True
        if dialog.step == BotDialogStep.BILL_HEADCOUNT:
            view, step = self._accept_headcount(user, language, draft, text)
        elif dialog.step == BotDialogStep.BILL_PAYMENT_NEW:
            view, step = self._accept_new_payment(user, language, draft, text)
        elif dialog.step == BotDialogStep.BILL_RECEIPT:
            view, step, kept = self._accept_receipt(chat_id, user, language, draft, message)
        else:
            return
        if "bill_id" in draft and "bill_id" not in (dialog.draft or {}):
            # The bill exists from here. Kept before the panel is drawn, so a
            # draw that fails does not let the next answer make a second one.
            self._remember(chat_id, user, dialog.step, draft)
        self.panels.answer(chat_id, message["message_id"], view, clear=kept)
        # Moved on only once the next question is on screen.
        if step is None:
            self.dialogs.clear(chat_id)
        else:
            self._remember(chat_id, user, step, draft)

    def _point_to_private_chat(self, chat_id: int, language: str) -> None:
        button = {"text": t(language, "btn_open_bot"), "url": bot_link()}
        send_message(chat_id, t(language, "group_private_only"), {"inline_keyboard": [[button]]})

    # -- start and onboarding ----------------------------------------------

    def _start(self, chat_id: int, user: User) -> None:
        """First-timers pick a language; everyone else lands on the menu, so
        /start stays a way back out of anything."""
        # Started in private: the bot can write to them from now on.
        user = self.users.note_write_access(user, True)
        if (user.settings or {}).get("onboarding_completed"):
            self._open(chat_id, user, self._menu_view(self._language_for(user)))
            return
        rows = [[{"text": LANGUAGE_NAMES[code], "callback_data": f"{LANGUAGE_PREFIX}{code}"}] for code in LANGUAGES]
        self.panels.open(chat_id, View(FIRST_LANGUAGE_PROMPT, rows))

    def _accept_language(self, chat_id: int, message_id: int | None, user: User, code: str) -> None:
        # The default currency goes in with the language — unless one is already
        # on file: somebody who came in through an invite may have set it in the
        # app before ever typing /start.
        already_chosen = (user.settings or {}).get("currency")
        self._finish_onboarding(chat_id, message_id, user, UserSettingsUpdate(
            language=resolve_language(code),
            currency=None if already_chosen else DEFAULT_CURRENCY,
            onboarding_completed=True,
        ))

    def _accept_currency(self, chat_id: int, message_id: int | None, user: User, code: str) -> None:
        self._finish_onboarding(chat_id, message_id, user, UserSettingsUpdate(
            currency=normalize_currency(code) or DEFAULT_CURRENCY, onboarding_completed=True,
        ))

    def _finish_onboarding(self, chat_id: int, message_id: int | None, user: User, answer: UserSettingsUpdate) -> None:
        """The answer is saved and the question goes — the panel, or one sent
        before the panel existed that would otherwise keep sending welcomes.
        Counted once: an old question answered again finishes nothing."""
        newcomer = not (user.settings or {}).get("onboarding_completed")
        language = self._language_for(self.users.update_settings(user.id, answer))
        if newcomer:
            capture(user.id, ProductEvent.ONBOARDING_COMPLETED, Surface.BOT, language=language)
        self.dialogs.clear(chat_id)
        self.panels.remove(chat_id, message_id)
        self._send_welcome(chat_id, language)

    def _send_welcome(self, chat_id: int, language: str) -> None:
        """The picture that explains the app at a glance. It is not the panel:
        it stays at the top of the chat, and its buttons open a panel under it."""
        caption = t(language, "welcome")
        markup = {"inline_keyboard": [
            *_open_app_row(language),
            [_button(language, "btn_guide", GUIDE_CALLBACK), _button(language, "btn_menu", MENU_CALLBACK)],
        ]}
        picture = welcome_picture(language)
        if picture:
            try:
                send_photo(chat_id, picture, caption=caption, reply_markup=markup)
                return
            except RuntimeError as e:
                logger.warning("Welcome picture failed, sending text: %s", e)
        send_message(chat_id, caption, markup)

    # -- the panel's places ------------------------------------------------

    def _open(self, chat_id: int, user: User, view: View) -> None:
        """A fresh panel at the bottom of the chat, on the place `view` is."""
        self.panels.open(chat_id, view)
        self._viewed(user, view)

    def _show(self, chat_id: int, message_id: int | None, user: User, view: View) -> None:
        """Somewhere other than a flow's question: the flow, if any, is left."""
        self._draw(chat_id, message_id, view)
        self._viewed(user, view)

    def _draw(self, chat_id: int, message_id: int | None, view: View) -> None:
        """As `_show`, for the place they are on drawn again with what changed:
        no new visit to count."""
        self.dialogs.clear(chat_id)
        self.panels.tapped(chat_id, message_id, view)

    def _command_view(self, command: str, user: User, language: str) -> View:
        if command == "bills":
            return self._bills_view(user, language, offset=0)
        if command == "settings":
            return self._settings_view(language)
        if command == "help":
            return self._guide_view(language)
        if command == "pro":
            return self.pro.offer(user, language, datetime.utcnow()).with_rows(self._back_to_menu(language))
        return self._menu_view(language)

    @staticmethod
    def _back_to_menu(language: str) -> list[dict]:
        return [_button(language, "btn_back_menu", MENU_CALLBACK)]

    def _menu_view(self, language: str) -> View:
        rows = [
            *_open_app_row(language),
            *in_pairs([
                _button(language, "btn_create_bill", NEW_BILL_CALLBACK),
                _button(language, "btn_my_bills", f"{BILLS_PREFIX}0"),
                _button(language, "btn_settings", SETTINGS_CALLBACK),
                _button(language, "btn_guide", GUIDE_CALLBACK),
            ]),
            [_button(language, "btn_pro_menu", PRO_CALLBACK)],
        ]
        return View(t(language, "menu"), rows, screen="menu")

    def _guide_view(self, language: str) -> View:
        rows = [*_open_app_row(language), self._back_to_menu(language)]
        rich = guide_rich(language)
        if rich is None:
            return View(guide_plain(language), rows, screen="guide")
        return View(rich, rows, rich=True, fallback=guide_plain(language), screen="guide")

    def _settings_view(self, language: str, saved: bool = False) -> View:
        """Shown again after a change rather than closing: someone who came to
        fix the language usually meant to fix the currency too."""
        title = t(language, "settings_title")
        rows = [
            [
                _button(language, "btn_settings_language", SETTINGS_LANGUAGE_CALLBACK),
                _button(language, "btn_settings_currency", SETTINGS_CURRENCY_CALLBACK),
            ],
            self._back_to_menu(language),
        ]
        return View(f"{t(language, 'settings_saved')}\n\n{title}" if saved else title, rows, screen="settings")

    def _language_picker(self, language: str) -> View:
        rows = [
            [{"text": LANGUAGE_NAMES[code], "callback_data": f"{SETTINGS_LANGUAGE_PREFIX}{code}"}]
            for code in LANGUAGES
        ]
        return View(t(language, "ask_language"), [*rows, [_button(language, "btn_back", SETTINGS_CALLBACK)]])

    def _currency_picker(self, language: str) -> View:
        rows = _currency_keyboard(SETTINGS_CURRENCY_PREFIX)
        return View(t(language, "ask_currency"), [*rows, [_button(language, "btn_back", SETTINGS_CALLBACK)]])

    def _save_language(self, chat_id: int, message_id: int | None, user: User, code: str) -> None:
        language = resolve_language(code)
        self.users.update_settings(user.id, UserSettingsUpdate(language=language))
        capture(user.id, ProductEvent.LANGUAGE_CHANGED, Surface.BOT, language=language)
        self._draw(chat_id, message_id, self._settings_view(language, saved=True))

    def _save_currency(self, chat_id: int, message_id: int | None, user: User, language: str, code: str) -> None:
        currency = normalize_currency(code) or CURRENCIES[0]
        self.users.update_settings(user.id, UserSettingsUpdate(currency=currency))
        capture(user.id, ProductEvent.CURRENCY_CHANGED, Surface.BOT, currency=currency)
        self._draw(chat_id, message_id, self._settings_view(language, saved=True))

    def _bills_view(self, user: User, language: str, offset: int) -> View:
        bills = self.bills.get_user_bills(user.id, offset=offset, limit=BILLS_PAGE_SIZE)
        newer = _button(language, "btn_newer", f"{BILLS_PREFIX}{max(offset - BILLS_PAGE_SIZE, 0)}")
        if not bills:
            if offset:
                return View(t(language, "bills_end"), [[newer], self._back_to_menu(language)], screen="bills")
            create = [_button(language, "btn_create_bill", NEW_BILL_CALLBACK)]
            return View(t(language, "bills_empty"), [create, self._back_to_menu(language)], screen="bills")

        lines = [t(language, "bills_header")] + [self._bill_line(bill, language) for bill in bills]
        rows = [
            [{"text": self._bill_button_label(bill, language), "callback_data": f"{CARD_PREFIX}{bill.public_token}"}]
            for bill in bills
        ]
        pages = [newer] if offset else []
        # A short page is the last one, and a button that answers «nothing more» is noise.
        if len(bills) == BILLS_PAGE_SIZE:
            pages.append(_button(language, "btn_more", f"{BILLS_PREFIX}{offset + BILLS_PAGE_SIZE}"))
        if pages:
            rows.append(pages)
        rows.append(self._back_to_menu(language))
        return View("\n".join(lines), rows, screen="bills")

    def _bill_line(self, bill, language: str) -> str:
        title = escape(bill.title or t(language, "bill_untitled"))
        status = t(language, f"status_{bill.status}")
        settled = f" · {bill.payers_paid}/{bill.payers_count}" if bill.payers_count else ""
        return f"• <b>{title}</b> — {self._amount(bill, language)} · {status}{settled}"

    def _bill_button_label(self, bill, language: str) -> str:
        title = bill.title or t(language, "bill_untitled")
        return f"{title} · {self._amount(bill, language)}"[:64]

    @staticmethod
    def _amount(bill, language: str | None = None) -> str:
        return format_amount(bill.total_sum, bill.currency, language)

    def _card_view(self, user: User, language: str, token: str) -> View:
        """One bill opened out: items, total, who is in so far — and for its
        owner, who has not paid and a way to remind them."""
        back = [_button(language, "btn_back_bills", f"{BILLS_PREFIX}0")]
        bill = self.bills.bill_repo.get_by_token(token)
        try:
            if bill is None:
                raise HTTPException(status_code=404)
            detail = self.bills.get_bill_details(bill.id, requester_id=user.id)
        except HTTPException:
            # Gone, or no longer theirs to see since the list was drawn.
            return View(t(language, "errors_bill_not_found"), [back])

        owner = self.pro.owner_card(bill, user, language, datetime.utcnow())
        text = render_bill_card(detail, language)
        return View(
            f"{text}\n\n{owner.text}" if owner.text else text,
            [*owner.rows, [open_bill_button(token, language)], back],
            screen="bill_card",
            screen_properties={"bill_id": bill.id},
        )

    # -- creating a bill ---------------------------------------------------

    def _begin_bill(self, chat_id: int, user: User) -> None:
        """Its first question is on screen."""
        self._remember(chat_id, user, BotDialogStep.BILL_HEADCOUNT, {})
        capture(user.id, ProductEvent.BILL_CREATE_OPENED, Surface.BOT)

    def _headcount_view(self, language: str, invalid: bool = False) -> View:
        return self._question(language, "ask_headcount", "headcount_invalid" if invalid else None)

    def _question(self, language: str, key: str, error_key: str | None, rows: list[list[dict]] | None = None) -> View:
        text = t(language, key)
        if error_key:
            text = f"<b>{t(language, error_key)}</b>\n\n{text}"
        return View(text, [*(rows or []), [_button(language, "btn_cancel", CANCEL_BILL_CALLBACK)]])

    def _accept_headcount(self, user: User, language: str, draft: dict, text: str) -> tuple[View, BotDialogStep]:
        if not text.isdigit() or not 1 <= int(text) <= MAX_HEADCOUNT:
            return self._headcount_view(language, invalid=True), BotDialogStep.BILL_HEADCOUNT

        draft["headcount"] = int(text)
        capture(user.id, ProductEvent.BILL_CREATE_STEP, Surface.BOT, step="payment")
        rows = [
            [{"text": (method.label or method.value)[:64], "callback_data": f"{PAYMENT_PREFIX}{method.id}"}]
            for method in self.payments.list_for_user(user.id)
        ]
        rows.append([_button(language, "btn_payment_new", NEW_PAYMENT_CALLBACK)])
        return self._question(language, "ask_payment_saved", None, rows), BotDialogStep.BILL_PAYMENT

    def _waiting_for_payment(self, chat_id: int) -> BotDialog | None:
        """The payment buttons count only while their question is the one being
        asked: a second tap, or a tap on a keyboard from an older message, must
        not make another bill."""
        dialog = self.dialogs.get_by_chat(chat_id)
        return dialog if dialog is not None and dialog.step == BotDialogStep.BILL_PAYMENT else None

    def _accept_saved_payment(
        self, chat_id: int, message_id: int | None, user: User, language: str, raw_id: str
    ) -> None:
        dialog = self._waiting_for_payment(chat_id)
        if dialog is None:
            return
        method = next((m for m in self.payments.list_for_user(user.id) if str(m.id) == raw_id), None)
        if method is None:
            return

        draft = dict(dialog.draft or {})
        draft["payment_details"] = method.value
        view = self._create_bill(user, language, draft)
        # Kept before the panel is drawn: a tap again after a failed draw finds this bill.
        self._remember(chat_id, user, BotDialogStep.BILL_PAYMENT, draft)
        self.panels.tapped(chat_id, message_id, view)
        self._remember(chat_id, user, BotDialogStep.BILL_RECEIPT, draft)

    def _ask_new_payment(self, chat_id: int, message_id: int | None, user: User, language: str) -> None:
        dialog = self._waiting_for_payment(chat_id)
        if dialog is None:
            return
        self.panels.tapped(chat_id, message_id, self._question(language, "ask_payment_new", None))
        self._remember(chat_id, user, BotDialogStep.BILL_PAYMENT_NEW, dict(dialog.draft or {}))

    def _accept_new_payment(self, user: User, language: str, draft: dict, text: str) -> tuple[View, BotDialogStep]:
        if len(text) < 4:
            return self._question(language, "ask_payment_new", "payment_invalid"), BotDialogStep.BILL_PAYMENT_NEW
        draft["payment_details"] = text
        return self._create_bill(user, language, draft), BotDialogStep.BILL_RECEIPT

    def _create_bill(self, user: User, language: str, draft: dict) -> View:
        """The bill exists from here on: everything it needs has been answered,
        and the receipt — a photo or a QR — needs something to attach to. This
        is the same order the Mini App wizard uses."""
        if draft.get("bill_id"):
            # Made by an earlier try whose answer never reached the screen.
            return self._receipt_view(user, language, draft["public_token"])
        bill = self.bills.create_bill(
            BillCreate(
                owner_id=user.id,
                total_sum=0,
                expected_people=draft.get("headcount"),
                payment_details=draft.get("payment_details"),
                include_owner=True,
            )
        )
        draft["bill_id"] = bill.id
        draft["public_token"] = bill.public_token
        capture(user.id, ProductEvent.BILL_CREATED, Surface.BOT, source="bot", bill_id=bill.id)
        return self._receipt_view(user, language, bill.public_token)

    def _receipt_view(self, user: User, language: str, token: str, error_key: str | None = None) -> View:
        """Without a photo to hand, the bill opens in the app to fill in there."""
        qr = (user.settings or {}).get("currency") == QR_CURRENCY
        text = t(language, "ask_receipt_qr" if qr else "ask_receipt")
        if error_key:
            text = f"<b>{t(language, error_key)}</b>\n\n{text}"
        rows = [[{"text": t(language, "btn_scan_qr"), "url": mini_app_link(f"scan_{token}")}]] if qr else []
        return View(text, [*rows, [open_bill_button(token, language)], self._back_to_menu(language)])

    def _accept_receipt(
        self, chat_id: int, user: User, language: str, draft: dict, message: dict
    ) -> tuple[View, BotDialogStep | None, bool]:
        """The next view and step, and whether the bot kept what was sent —
        only then may the message go from the chat."""
        token = draft.get("public_token")
        file_id = largest_photo_file_id(message)
        if not file_id:
            # A receipt sent as a file is not a photo; it stays for them to resend.
            return self._receipt_view(user, language, token, "receipt_expected"), BotDialogStep.BILL_RECEIPT, "document" not in message
        try:
            self.scans.ensure(user.id, datetime.utcnow())
        except ScanLimitReached as reached:
            capture(user.id, ProductEvent.PAYWALL_OPENED, Surface.BOT, reason="scans")
            # The bill is there without its receipt; the dishes can be added by hand.
            limit = t(language, "pro_scan_limit").format(limit=reached.limit)
            pro = {"text": t(language, "btn_pro"), "url": mini_app_link(PRO_START)}
            text = f"{limit}\n\n{t(language, 'bill_created_manual')}"
            return self._bill_ready_view(language, token, text, pro), None, False

        try:
            raw = download_file(file_id)
        except RuntimeError as e:
            logger.warning("Could not download receipt in chat %s: %s", chat_id, e)
            return self._receipt_view(user, language, token, "receipt_failed"), BotDialogStep.BILL_RECEIPT, False

        task = self.receipts.save_receipt_bytes(raw, user_id=user.id, bill_id=draft.get("bill_id"), notify_chat_id=chat_id)
        queue_manager.submit(task.id)
        capture(user.id, ProductEvent.RECEIPT_SCAN_STARTED, Surface.BOT, mode="photo", target="new_bill")
        return self._bill_ready_view(language, token, t(language, "bill_ready")), None, True

    def _bill_ready_view(self, language: str, token: str, text: str, *extra: dict) -> View:
        rows = [[button] for button in extra]
        rows += [[invite_button(token, language)], [open_bill_button(token, language)], self._back_to_menu(language)]
        return View(text, rows)

    # -- a bill said out loud ----------------------------------------------

    def _accept_voice(self, chat_id: int, message: dict, from_user: dict) -> None:
        """A voice message, whenever it comes: a new bill from what was said —
        or, with a bill of theirs open from the last hours, that one if they
        pick it. Sent while the wizard waits for its receipt, it fills that
        bill. The message stays in the chat: the bot keeps nothing of it."""
        user = self._user_from(from_user)
        language = self._language_for(user)
        message_id = message["message_id"]
        dialog = self.dialogs.get_by_chat(chat_id)
        draft = dict(dialog.draft or {}) if dialog is not None and dialog.step == BotDialogStep.BILL_RECEIPT else {}
        bill_id = draft.get("bill_id")

        if not self.pro.pro.is_pro(user.id, datetime.utcnow()):
            capture(user.id, ProductEvent.PAYWALL_OPENED, Surface.BOT, reason="voice")
            pro = [{"text": t(language, "btn_pro"), "url": mini_app_link(PRO_START)}]
            if bill_id:
                # Still waiting for its receipt: the photo can come instead.
                asked = self._receipt_view(user, language, draft["public_token"], "voice_pro")
                view = View(asked.text, [pro, *asked.rows])
            else:
                view = View(t(language, "voice_pro"), [pro, self._back_to_menu(language)])
            self.panels.answer(chat_id, message_id, view, clear=False)
            return

        voice = message["voice"]
        capture(user.id, ProductEvent.VOICE_INPUT_SENT, Surface.BOT, input="voice", **({"bill_id": bill_id} if bill_id else {}))
        if (voice.get("duration") or 0) > MAX_VOICE_SECONDS:
            capture(user.id, ProductEvent.VOICE_INPUT_RESULT, Surface.BOT, input="voice", ok=False, reason="VOICE_TOO_LONG")
            self.panels.answer(chat_id, message_id, View(t(language, "voice_too_long"), [self._back_to_menu(language)]), clear=False)
            return
        self.panels.answer(chat_id, message_id, View(t(language, "voice_working")), clear=False)
        # shortcut: heard and understood in this update's own thread, 10–20 s of
        # one of the bot's few slots; queue it like receipts if voice traffic grows.
        try:
            heard = self.voice.hear(bill_id, download_file(voice["file_id"]), "voice.ogg")
        except (RuntimeError, HTTPException) as error:
            logger.warning("Could not hear a voice message in chat %s: %s", chat_id, error)
            capture(user.id, ProductEvent.VOICE_INPUT_RESULT, Surface.BOT, input="voice", ok=False, reason="VOICE_FAILED")
            self.panels.redraw(chat_id, View(t(language, "voice_failed"), [self._back_to_menu(language)]))
            return

        if bill_id:
            self.dialogs.clear(chat_id)
            self.panels.redraw(chat_id, self._tell_voice(user, language, bill_id, heard))
            return
        targets = self._voice_targets(user)
        if not targets:
            self.panels.redraw(chat_id, self._tell_voice(user, language, self._voice_bill(user), heard, made=True))
            return
        rows = [[_button(language, "btn_voice_new", f"{VOICE_PREFIX}{VOICE_NEW}")]]
        rows += [
            [{"text": self._bill_button_label(bill, language), "callback_data": f"{VOICE_PREFIX}{bill.public_token}"}]
            for bill in targets
        ]
        rows.append([_button(language, "btn_cancel", CANCEL_BILL_CALLBACK)])
        self.panels.redraw(chat_id, View(t(language, "voice_where").format(heard=escape(heard)), rows))
        self._remember(chat_id, user, BotDialogStep.BILL_VOICE, {"heard": heard})

    def _voice_into(self, chat_id: int, message_id: int | None, user: User, language: str, target: str) -> None:
        """The bill the voice message just heard is for. A tap on an older
        question, or a second tap on this one, finds nothing to apply."""
        dialog = self.dialogs.get_by_chat(chat_id)
        if dialog is None or dialog.step != BotDialogStep.BILL_VOICE:
            return
        heard = (dialog.draft or {}).get("heard") or ""
        self.dialogs.clear(chat_id)
        if target == VOICE_NEW:
            bill_id, made = self._voice_bill(user), True
        else:
            bill = self.bills.bill_repo.get_by_token(target)
            if bill is None or bill.owner_id != user.id:
                self._show(chat_id, message_id, user, View(t(language, "errors_bill_not_found"), [self._back_to_menu(language)]))
                return
            bill_id, made = bill.id, False
        self.panels.tapped(chat_id, message_id, View(t(language, "voice_working")))
        self.panels.redraw(chat_id, self._tell_voice(user, language, bill_id, heard, made))

    def _voice_targets(self, user: User) -> list:
        """Their own open bills from the last hours, newest first, that a voice
        message may be for."""
        since = datetime.now(timezone.utc) - VOICE_FRESH
        bills = self.bills.get_user_bills(user.id, limit=10, status_filter="active", role="owner")
        return [bill for bill in bills if bill.status == BillStatus.OPEN and bill.created_at >= since][:VOICE_TARGETS]

    def _voice_bill(self, user: User) -> int:
        """A new bill for a voice message, on the card they saved last; its
        people are seated as they are named."""
        methods = self.payments.list_for_user(user.id)
        bill = self.bills.create_bill(BillCreate(
            owner_id=user.id,
            total_sum=0,
            include_owner=True,
            payment_details=methods[-1].value if methods else None,
        ))
        capture(user.id, ProductEvent.BILL_CREATED, Surface.BOT, source="voice", bill_id=bill.id)
        return bill.id

    def _tell_voice(self, user: User, language: str, bill_id: int, heard: str, made: bool = False) -> View:
        """What was said, applied to the bill, and how that went. A bill made
        for it that ends up with nothing on it goes again."""
        try:
            told = self.voice.tell(bill_id, heard)
        except HTTPException as refusal:
            code = refusal.detail.get("code") if isinstance(refusal.detail, dict) else None
            capture(
                user.id, ProductEvent.VOICE_INPUT_RESULT, Surface.BOT,
                bill_id=bill_id, input="voice", ok=False, reason=code or "refused",
            )
            if made:
                self.bills.discard_provisional_bill(bill_id, user.id)
            key = {"VOICE_NOTHING": "voice_nothing", "VOICE_EMPTY": "voice_empty"}.get(code, "voice_failed")
            return View(t(language, key).format(heard=escape(heard)), [self._back_to_menu(language)])

        capture(
            user.id, ProductEvent.VOICE_INPUT_RESULT, Surface.BOT,
            bill_id=bill_id, input="voice", ok=True, added=told.added, assigned=told.assigned,
        )
        bill = self.bills.bill_repo.get_by_id(bill_id)
        lines = [t(language, "voice_done").format(
            title=escape(bill.title or t(language, "bill_untitled")), added=told.added, assigned=told.assigned,
        )]
        if told.held:
            lines.append(t(language, "voice_held").format(names=escape(", ".join(told.held))))
        if told.unseated:
            lines.append(t(language, "voice_unseated").format(names=escape(", ".join(told.unseated))))
        return self._bill_ready_view(language, bill.public_token, "\n".join(lines))

    # -- sharing -----------------------------------------------------------

    def _may_share(self, bill, user_id: int) -> bool:
        if bill.owner_id == user_id:
            return True
        return self.bills.bill_repo.get_participant_by_bill_and_user(bill.id, user_id) is not None

    def _post_invite(self, chat_id: int, message_id: int | None, user: User, language: str, token: str) -> None:
        """The invite goes into the chat for the person to forward — the post
        the Mini App shares, which a forward keeps whole. What to do with it is
        said above it: in the panel when the tap came from there, in a line of
        its own otherwise."""
        bill = self.bills.bill_repo.get_by_token(token)
        if bill is None or not self._may_share(bill, user.id):
            self._show(chat_id, message_id, user, View(t(language, "errors_bill_not_found"), [self._back_to_menu(language)]))
            return

        hint = t(language, "invite_forward_hint")
        if self.panels.is_panel(chat_id, message_id):
            self.panels.redraw(chat_id, View(hint, [[open_bill_button(token, language)], self._back_to_menu(language)]))
        else:
            send_message(chat_id, hint)
        SharedBillService(self.bills.bill_repo.session).post_to_chat(bill, user, language, chat_id)
        capture(
            user.id,
            ProductEvent.SHARE_INVITE,
            Surface.BOT,
            method="message",
            channel=InviteChannel.BOT.value,
            bill_id=bill.id,
        )

    # -- shared ------------------------------------------------------------

    def _user_from(self, from_user: dict, start: str = "bot", source: str | None = None) -> User:
        """The sender's account; `start` and `source` are their first touch,
        should this message be what makes it."""
        return self.users.get_or_create_from_bot(
            telegram_id=from_user.get("id"),
            name=from_user.get("first_name"),
            username=from_user.get("username"),
            start=start,
            source=source,
        )

    @staticmethod
    def _viewed(user: User, view: View) -> None:
        if view.screen:
            capture(user.id, ProductEvent.BOT_SCREEN_VIEWED, Surface.BOT, screen=view.screen, **view.screen_properties)

    @staticmethod
    def _language_for(user: User | None) -> str:
        """What the user chose, or the product default before they choose."""
        saved = ((user.settings if user else None) or {}).get("language")
        return resolve_language(saved) if saved else DEFAULT_LANGUAGE

    def _remember(self, chat_id: int, user: User, step: BotDialogStep, draft: dict) -> None:
        dialog = self.dialogs.get_by_chat(chat_id) or BotDialog(chat_id=chat_id)
        dialog.user_id = user.id
        dialog.step = step
        dialog.draft = draft
        # Set here rather than left to the database's clock, which may not keep UTC: DIALOG_TTL reads it.
        dialog.updated_at = datetime.utcnow()
        self.dialogs.save(dialog)
