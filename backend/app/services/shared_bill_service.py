"""Bills shared into chats: writing the post, and keeping it current.

A shared bill is a message sent through the bot in inline mode, so the bot may
edit it — once it knows which message it became. Telegram says so in two ways:
in chosen_inline_result when the share goes out (only if inline feedback is on
for the bot), and in the callback of any of the message's buttons. Either one
ties the message to the share it came from; from then on every change to the
bill is written into it, until the bill closes.

The post's buttons also act, for whoever taps them: take a free seat, or say
«I've paid». The keyboard is the same for everyone in the chat, so the tap is
what says who; the answer goes to that person alone, and the post itself is
redrawn for everybody.
"""
import logging
import os
from html import escape
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import Bill, BillStatus, BillUser, Invite, InviteChannel, SharedBillMessage, User
from app.repositories.bill_repo import BillRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.user_repo import UserRepository
from app.schemas.bill_schemas import BillParticipantPaymentUpdate
from app.services.bill_participant_service import BillParticipantService
from app.services.bill_summary import seat_name, summary_for
from app.services.invite_service import InviteService, invite_start_param
from app.services.product_events import ProductEvent, Surface, capture
from app.services.profile_photos import profile_photos
from app.services.sender_accounts import SenderAccountService
from app.services.themes import DEFAULT_THEME, theme_of
from app.services.share_message import PAID_PREFIX, REFRESH_PREFIX, SEAT_PREFIX, PostKind, ShareMessage, compose
from app.services.user_service import UserService, bot_may_write
from app.utils.bill_card import open_bill_button
from app.utils.bot_copy import resolve_language, t
from app.utils.currency import format_amount
from app.utils.telegram import (
    answer_callback_query,
    bot_start_link,
    edit_chat_message_text,
    edit_inline_message_text,
    is_missing_message,
    is_unchanged_message,
    mini_app_link,
    save_prepared_text_message,
    send_message,
)

logger = logging.getLogger(__name__)

# What chosen_inline_result echoes back: which share a message came from.
RESULT_PREFIX = "share:"
# /start from a post's button: the post's invite code follows.
POST_START_PREFIX = "post_"
# A button everybody at the table can press; one edit per few seconds is plenty.
REFRESH_COOLDOWN = timedelta(seconds=5)
# Chats move on; a month-old share is not worth editing any more.
TRACKING_WINDOW = timedelta(days=30)


class Refresh(str, Enum):
    EDITED = "edited"
    UNCHANGED = "unchanged"
    GONE = "gone"


def language_of(user: User) -> str:
    return resolve_language((user.settings or {}).get("language"))


@dataclass(frozen=True)
class PreparedPost:
    """A post the bot prepared for an account to send, and the picture above it."""

    id: str
    preview_url: str | None


class _Refused(Exception):
    """A tap that cannot be done, and the copy key that says why."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


class SharedBillService:
    def __init__(self, session: Session):
        self.session = session
        self.bills = BillRepository(session)
        users = UserRepository(session)
        self.user_repo = users
        self.users = UserService(users)
        self.invite_codes = InviteRepository(session)
        self.invites = InviteService(self.invite_codes, self.bills, users)
        self.participants = BillParticipantService(self.bills, users)

    def compose_for(self, bill: Bill, invite_code: str, language: str, kind: PostKind, theme: str) -> ShareMessage:
        summary = summary_for(self.session, bill)
        # Looked up while the post is written rather than when Telegram comes
        # for the picture: the faces are then ready for it, and a face that
        # could not be fetched now versions the picture again once it can be.
        faces = frozenset(profile_photos.for_people(seat.telegram_id for seat in summary.seats if seat.telegram_id))
        reminded_seat = None
        open_url = mini_app_link(invite_start_param(invite_code))
        if kind is PostKind.REMINDER:
            # The person is already on their seat: the bill opens as it is.
            reminded_seat = self.invite_codes.get_by_code(invite_code).seat_participant_id
            open_url = mini_app_link(f"bill_{bill.public_token}")
        return compose(
            summary,
            language,
            open_url=open_url,
            invite_code=invite_code,
            public_token=bill.public_token,
            base_url=os.getenv("PUBLIC_BASE_URL"),
            kind=kind,
            faces=faces,
            theme=theme,
            seat_id=reminded_seat,
        )

    def prepare(self, bill: Bill, sharer: User, language: str, seat: BillUser | None = None) -> str:
        """Register the post with Telegram for WebApp.shareMessage and return
        its prepared id. The invite is minted here, so whoever follows the link
        is credited to the person who shared it. An invite to one `seat` is the
        same post, but its link sits the person right there, so it goes to
        private chats only."""
        invite = self.invites.create(
            bill.id,
            sharer.id,
            InviteChannel.SEAT if seat else InviteChannel.PREPARED,
            seat_participant_id=seat.id if seat else None,
        )
        theme = theme_of(self.session, sharer, datetime.utcnow())
        message = self.compose_for(bill, invite.code, language, PostKind.SEAT if seat else PostKind.GROUP, theme)
        self.session.add(SharedBillMessage(
            bill_id=bill.id,
            invite_code=invite.code,
            language=language,
            theme=theme,
            fingerprint=message.fingerprint,
        ))
        self.session.commit()
        return save_prepared_text_message(
            sharer.telegram_id,
            result_id=f"{RESULT_PREFIX}{invite.code}",
            title=message.title,
            description=message.description,
            text_html=message.html,
            link_preview_options=message.link_preview,
            reply_markup=message.reply_markup,
            private_chats_only=seat is not None,
        )

    def owner_theme(self, bill: Bill) -> str:
        """What the posts the bot sends for a bill are drawn in: the theme of
        its owner, who they come from."""
        owner = self.user_repo.get_by_id(bill.owner_id)
        return theme_of(self.session, owner, datetime.utcnow()) if owner else DEFAULT_THEME

    def remind_by_bot(self, bill: Bill, invite_code: str, recipient: User) -> dict:
        """The reminder as a message from the bot itself. Raises RuntimeError
        like any bot send — is_unreachable_chat tells a blocked bot apart."""
        language, theme = language_of(recipient), self.owner_theme(bill)
        message = self.compose_for(bill, invite_code, language, PostKind.REMINDER, theme)
        return send_message(
            recipient.telegram_id, message.html, message.reply_markup, link_preview_options=message.link_preview
        )

    def prepare_reminder(self, bill: Bill, invite_code: str, recipient: User, sender_telegram_id: int) -> PreparedPost:
        """The reminder prepared for a sender account to send as the bot's post.
        Tracked like a shared post, so its buttons find it and it is kept current."""
        language, theme = language_of(recipient), self.owner_theme(bill)
        message = self.compose_for(bill, invite_code, language, PostKind.REMINDER, theme)
        # One reminder may be prepared for several accounts before one sends it.
        tracked = self.session.exec(
            select(SharedBillMessage).where(SharedBillMessage.invite_code == invite_code)
        ).first()
        if tracked is None:
            self.session.add(SharedBillMessage(
                bill_id=bill.id,
                invite_code=invite_code,
                language=language,
                theme=theme,
                fingerprint=message.fingerprint,
            ))
            self.session.commit()
        prepared_id = save_prepared_text_message(
            sender_telegram_id,
            result_id=f"{RESULT_PREFIX}{invite_code}",
            title=message.title,
            description=message.description,
            text_html=message.html,
            link_preview_options=message.link_preview,
            reply_markup=message.reply_markup,
            private_chats_only=True,
        )
        return PreparedPost(id=prepared_id, preview_url=message.preview_url)

    def post_to_chat(self, bill: Bill, sharer: User, language: str, chat_id: int) -> dict:
        """The same post, sent into the bot chat for the sharer to forward on."""
        invite = self.invites.create(bill.id, sharer.id, InviteChannel.BOT)
        return self.send(bill, invite.code, language, chat_id, PostKind.FORWARD, theme_of(self.session, sharer, datetime.utcnow()))

    def send(self, bill: Bill, invite_code: str, language: str, chat_id: int, kind: PostKind, theme: str) -> dict:
        """The post as a message from the bot. Only shared posts are tracked,
        so this one offers no refresh."""
        message = self.compose_for(bill, invite_code, language, kind, theme)
        return send_message(chat_id, message.html, message.reply_markup, link_preview_options=message.link_preview)

    def remember(self, invite_code: str, inline_message_id: str) -> SharedBillMessage | None:
        """Tie a message Telegram named to the share it came from; None when the
        code is not one of our shares."""
        known = self._by_inline_id(inline_message_id)
        if known:
            return known
        shares = self.session.exec(
            select(SharedBillMessage).where(SharedBillMessage.invite_code == invite_code)
        ).all()
        if not shares:
            return None
        record = next((share for share in shares if share.inline_message_id is None), None)
        if record is None:
            # The same share turned into another message, e.g. sent twice.
            record = SharedBillMessage(
                bill_id=shares[0].bill_id,
                invite_code=invite_code,
                language=shares[0].language,
                theme=shares[0].theme,
            )
        record.inline_message_id = inline_message_id
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def refresh(self, record: SharedBillMessage, now: datetime) -> Refresh:
        bill = self.bills.get_by_id(record.bill_id)
        if bill is None or bill.deleted_at is not None:
            return self._forget(record)

        message = self.compose_for(
            bill, record.invite_code, record.language, self._kind_of(record.invite_code), record.theme
        )
        if message.fingerprint == record.fingerprint:
            return Refresh.UNCHANGED
        try:
            edit_inline_message_text(
                record.inline_message_id,
                message.html,
                message.link_preview,
                message.reply_markup,
            )
        except RuntimeError as error:
            if is_missing_message(error):
                return self._forget(record)
            if not is_unchanged_message(error):
                raise

        record.fingerprint = message.fingerprint
        record.refreshed_at = now
        record.is_final = message.is_final
        self.session.add(record)
        self.session.commit()
        return Refresh.EDITED

    def press_refresh(
        self,
        callback_id: str,
        inline_message_id: str | None,
        data: str,
        from_user: dict,
        now: datetime,
        *,
        chat_id: int | None = None,
        message_id: int | None = None,
    ) -> None:
        code = data.removeprefix(REFRESH_PREFIX)
        if not inline_message_id and chat_id and message_id:
            self._refresh_chat_reminder(callback_id, code, from_user, chat_id, message_id)
            return
        language = resolve_language(from_user.get("language_code"))
        record = self.remember(code, inline_message_id) if inline_message_id else None
        if record is None or record.is_gone:
            answer_callback_query(callback_id, t(language, "share_unavailable"))
            return

        language = record.language
        user = self.user_repo.get_by_telegram_id(from_user.get("id"))
        if record.refreshed_at and now - record.refreshed_at < REFRESH_COOLDOWN:
            self._refreshed(user, record.bill_id, "cooldown")
            answer_callback_query(callback_id, t(language, "share_up_to_date"))
            return
        try:
            outcome = self.refresh(record, now)
        except RuntimeError:
            logger.exception("Refreshing shared bill message %s failed", record.id)
            self._refreshed(user, record.bill_id, "error")
            answer_callback_query(callback_id)
            return
        self._refreshed(user, record.bill_id, outcome.value)
        answer_callback_query(callback_id, t(language, {
            Refresh.EDITED: "share_refreshed",
            Refresh.UNCHANGED: "share_up_to_date",
            Refresh.GONE: "share_unavailable",
        }[outcome]))

    def _refresh_chat_reminder(self, callback_id: str, code: str, from_user: dict, chat_id: int, message_id: int) -> None:
        """A reminder the bot sent into someone's chat. It is not tracked, so a
        refresh writes it out again from the bill as it is now."""
        user = self.user_repo.get_by_telegram_id(from_user.get("id"))
        language = language_of(user) if user else resolve_language(from_user.get("language_code"))
        invite = self.invite_codes.get_by_code(code)
        bill = self.bills.get_by_id(invite.bill_id) if invite else None
        if bill is None or bill.deleted_at is not None or self._kind_of(code) is not PostKind.REMINDER:
            answer_callback_query(callback_id, t(language, "share_unavailable"))
            return
        message = self.compose_for(bill, code, language, PostKind.REMINDER, self.owner_theme(bill))
        try:
            edit_chat_message_text(chat_id, message_id, message.html, message.link_preview, message.reply_markup)
        except RuntimeError as error:
            if is_unchanged_message(error):
                self._refreshed(user, bill.id, Refresh.UNCHANGED.value)
                answer_callback_query(callback_id, t(language, "share_up_to_date"))
                return
            if not is_missing_message(error):
                logger.warning("Reminder %s not refreshed: %s", code, error)
            self._refreshed(user, bill.id, Refresh.GONE.value)
            answer_callback_query(callback_id, t(language, "share_unavailable"))
            return
        self._refreshed(user, bill.id, Refresh.EDITED.value)
        answer_callback_query(callback_id, t(language, "share_refreshed"))

    @staticmethod
    def _refreshed(user: User | None, bill_id: int, outcome: str) -> None:
        """Counted for the people the app knows. Anyone in a chat can press it,
        and a press is no reason to make someone an account."""
        if user is not None:
            capture(user.id, ProductEvent.POST_REFRESHED, Surface.BOT, bill_id=bill_id, outcome=outcome)

    def press_action(
        self,
        callback_id: str,
        data: str,
        from_user: dict,
        now: datetime,
        *,
        inline_message_id: str | None = None,
        chat_id: int | None = None,
        message_id: int | None = None,
    ) -> None:
        """A seat or «I've paid» tapped under a post: done for whoever tapped,
        answered to them alone, and the post redrawn for everybody."""
        user = self.users.get_or_create_from_bot(
            telegram_id=from_user.get("id"),
            name=from_user.get("first_name"),
            username=from_user.get("username"),
            start="post",
        )
        language = resolve_language((user.settings or {}).get("language") or from_user.get("language_code"))
        seat_tap = data.startswith(SEAT_PREFIX)
        code, _, seat_id = data.removeprefix(SEAT_PREFIX if seat_tap else PAID_PREFIX).partition(":")
        invite = self.invite_codes.get_by_code(code)
        bill = self.bills.get_by_id(invite.bill_id) if invite else None
        if bill is None or bill.deleted_at is not None or (seat_tap and not seat_id.isdigit()):
            answer_callback_query(callback_id, t(language, "share_unavailable"), show_alert=True)
            return
        action = "seat" if seat_tap else "paid"
        try:
            done = (
                self._take_seat(bill, invite, user, int(seat_id), language)
                if seat_tap
                else self._mark_paid(bill, invite, user, language)
            )
        except _Refused as refusal:
            self._refused(user, bill, action, refusal.key, callback_id, language)
            return
        except HTTPException as error:
            self.session.rollback()
            key = "share_seat_gone" if error.detail == "SEAT_TAKEN" else "share_action_failed"
            self._refused(user, bill, action, key, callback_id, language)
            return
        # The bot cannot write to them yet: the answer opens its chat, whose
        # Start lets it — and its reminders cost no sender account. Not for a
        # sender account itself: the bot never answers those.
        reachable = bot_may_write(user) or SenderAccountService(self.session).is_sender(user.telegram_id)
        opens = None if reachable else bot_start_link(f"{POST_START_PREFIX}{code}")
        answer_callback_query(callback_id, done, url=opens)
        self._redraw(bill, code, language, now, inline_message_id, chat_id, message_id)

    @staticmethod
    def _refused(user: User, bill: Bill, action: str, key: str, callback_id: str, language: str) -> None:
        capture(
            user.id,
            ProductEvent.POST_ACTION_REFUSED,
            Surface.BOT,
            bill_id=bill.id,
            action=action,
            reason=key.removeprefix("share_"),
        )
        answer_callback_query(callback_id, t(language, key), show_alert=True)

    def welcome_from_post(self, chat_id: int, code: str, from_user: dict) -> bool:
        """Someone came to the bot from a post's button and started it: say
        where they stand on that bill — all they came for. False when there is
        nothing to say, and /start goes on as ever."""
        user = self.users.get_or_create_from_bot(
            telegram_id=from_user.get("id"),
            name=from_user.get("first_name"),
            username=from_user.get("username"),
            start="post",
        )
        invite = self.invite_codes.get_by_code(code)
        bill = self.bills.get_by_id(invite.bill_id) if invite else None
        seat = self.bills.get_participant_by_bill_and_user(bill.id, user.id) if bill and bill.deleted_at is None else None
        if seat is None:
            return False
        capture(user.id, ProductEvent.BOT_COMMAND, Surface.BOT, command="start", start="post")
        self.users.note_write_access(user, True)
        language = resolve_language((user.settings or {}).get("language") or from_user.get("language_code"))
        title = escape(bill.title or t(language, "bill_untitled"))
        text = t(language, "post_welcome_paid" if seat.is_paid else "post_welcome_seat").format(title=title)
        send_message(chat_id, text, {"inline_keyboard": [[open_bill_button(bill.public_token, language)]]})
        return True

    def _take_seat(self, bill: Bill, invite: Invite, user: User, seat_id: int, language: str) -> str:
        if bill.status != BillStatus.OPEN:
            raise _Refused("share_closed")
        seat = self.bills.get_participant_by_id(seat_id)
        if seat is None or seat.bill_id != bill.id:
            raise _Refused("share_unavailable")
        mine = self.bills.get_participant_by_bill_and_user(bill.id, user.id)
        if mine and mine.id == seat.id:
            return t(language, "share_seat_yours")
        if mine:
            # Moving leaves dishes behind; that is a choice for the app, where
            # it is asked for, not for a button anyone in the chat can press.
            raise _Refused("share_seat_elsewhere")
        if seat.user_id is not None:
            raise _Refused("share_seat_gone")
        title = self._title(seat, language)
        self._claim(bill, invite, seat, user)
        return t(language, "share_seat_ok").format(name=title)

    def _mark_paid(self, bill: Bill, invite: Invite, user: User, language: str) -> str:
        if bill.status == BillStatus.CLOSED:
            raise _Refused("share_closed")
        if bill.owner_id == user.id:
            raise _Refused("share_paid_owner")
        seat = self.bills.get_participant_by_bill_and_user(bill.id, user.id)
        # The seat as the post named it, before it takes the person's name.
        claimed: str | None = None
        if seat is None and invite.channel == InviteChannel.REMINDER:
            # A reminder went to someone on their seat; without one now, the
            # owner has taken them off the bill since.
            raise _Refused("share_paid_left_bill")
        if seat is None and invite.seat_participant_id:
            # A personal invite already says whose seat it is: «I've paid» from
            # the person it was sent to sits them there on the way.
            seat = self.bills.get_participant_by_id(invite.seat_participant_id)
            if seat is None or seat.user_id is not None:
                raise _Refused("share_seat_gone")
            claimed = self._title(seat, language)
            self._claim(bill, invite, seat, user)
            self.session.refresh(seat)
        if seat is None:
            raise _Refused("share_paid_seat_first")
        if seat.is_paid:
            return t(language, "share_paid_already")
        if seat.allocated_amount <= 0:
            if claimed:
                return t(language, "share_seat_ok_nothing_owed").format(name=claimed)
            raise _Refused("share_paid_nothing")
        amount = format_amount(seat.allocated_amount, bill.currency, language)
        self.participants.update_payment_status(
            bill.id, seat.id, BillParticipantPaymentUpdate(is_paid=True, user_id=user.id)
        )
        capture(
            user.id,
            ProductEvent.PAYMENT_MARKED,
            Surface.BOT,
            bill_id=bill.id,
            paid=True,
            by="self",
            channel=invite.channel.value,
            **{"from": "post"},
        )
        return t(language, "share_paid_ok").format(amount=amount)

    def _claim(self, bill: Bill, invite: Invite, seat: BillUser, user: User) -> None:
        self.participants.claim_seat(bill.id, seat.id, user.id, invite.inviter_user_id)
        capture(
            user.id,
            ProductEvent.PARTICIPANT_JOINED,
            Surface.BOT,
            via="post",
            channel=invite.channel.value,
            bill_id=bill.id,
        )

    def _redraw(
        self,
        bill: Bill,
        code: str,
        language: str,
        now: datetime,
        inline_message_id: str | None,
        chat_id: int | None,
        message_id: int | None,
    ) -> None:
        """Show the tap's outcome in the post right away rather than on the next
        tick. The tap itself is already done; a failed redraw only waits for it."""
        try:
            if inline_message_id:
                record = self.remember(code, inline_message_id)
                if record and not record.is_gone:
                    self.refresh(record, now)
            elif chat_id and message_id:
                # Only a post the bot sent to someone on their own seat acts.
                message = self.compose_for(bill, code, language, self._chat_kind_of(code), self.owner_theme(bill))
                edit_chat_message_text(chat_id, message_id, message.html, message.link_preview, message.reply_markup)
        except RuntimeError as error:
            if not is_unchanged_message(error):
                logger.warning("Post of bill %s not redrawn after a tap: %s", bill.id, error)

    def _kind_of(self, invite_code: str) -> PostKind:
        invite = self.invite_codes.get_by_code(invite_code)
        if invite and invite.channel == InviteChannel.REMINDER:
            return PostKind.REMINDER
        return PostKind.SEAT if invite and invite.seat_participant_id else PostKind.GROUP

    def _chat_kind_of(self, invite_code: str) -> PostKind:
        """What a post the bot sent into somebody's own chat is."""
        return PostKind.REMINDER if self._kind_of(invite_code) is PostKind.REMINDER else PostKind.DIRECT

    @staticmethod
    def _title(seat: BillUser, language: str) -> str:
        return seat_name(seat) or t(language, "share_guest").format(n=seat.seat_index)

    def chosen(self, result_id: str, inline_message_id: str | None) -> None:
        if inline_message_id and result_id.startswith(RESULT_PREFIX):
            self.remember(result_id.removeprefix(RESULT_PREFIX), inline_message_id)

    def refresh_due(self, now: datetime, limit: int, bill_ids: set[int] | None = None) -> int:
        """Bring the live shares up to date, a bounded number of edits at a time
        so a busy tick stays inside Telegram's flood limits.

        Given bill_ids, only those bills' posts; the set is left holding the
        bills whose posts this tick did not get to."""
        query = select(SharedBillMessage).where(
            SharedBillMessage.inline_message_id.is_not(None),
            SharedBillMessage.is_gone.is_(False),
            SharedBillMessage.is_final.is_(False),
            SharedBillMessage.created_at >= now - TRACKING_WINDOW,
        )
        if bill_ids is not None:
            query = query.where(SharedBillMessage.bill_id.in_(bill_ids))
        records = self.session.exec(
            query.order_by(SharedBillMessage.refreshed_at.is_not(None), SharedBillMessage.refreshed_at)
        ).all()
        edited = 0
        done = 0
        for record in records:
            if edited >= limit:
                break
            try:
                if self.refresh(record, now) == Refresh.EDITED:
                    edited += 1
            except RuntimeError as error:
                # Most likely a flood limit; the next tick picks it up again.
                logger.warning("Shared bill message %s not refreshed: %s", record.id, error)
                break
            done += 1
        if bill_ids is not None:
            bill_ids.clear()
            bill_ids.update(record.bill_id for record in records[done:])
        return edited

    def _by_inline_id(self, inline_message_id: str) -> SharedBillMessage | None:
        return self.session.exec(
            select(SharedBillMessage).where(SharedBillMessage.inline_message_id == inline_message_id)
        ).first()

    def _forget(self, record: SharedBillMessage) -> Refresh:
        record.is_gone = True
        self.session.add(record)
        self.session.commit()
        return Refresh.GONE
