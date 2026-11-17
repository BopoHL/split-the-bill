"""Product analytics only the server sees: what people do in the bot's chat,
and Pro payments, which Telegram reports to the server whether the app is still
open or the purchase was made in the bot.

Events go to the app's PostHog project under the distinct id the app identifies
with — the user's id — so the app's events and these add up to one person.
Without POSTHOG_KEY nothing is sent."""
import logging
import os
from enum import Enum
from functools import cache

from posthog import Posthog

logger = logging.getLogger(__name__)

DEFAULT_HOST = "https://eu.i.posthog.com"


class ProductEvent(str, Enum):
    BOT_COMMAND = "bot_command"
    BOT_SCREEN_VIEWED = "bot_screen_viewed"
    # The person blocked the bot in their private chat, or let it write again.
    BOT_ACCESS_CHANGED = "bot_access_changed"
    ONBOARDING_COMPLETED = "onboarding_completed"
    LANGUAGE_CHANGED = "language_changed"
    CURRENCY_CHANGED = "currency_changed"
    BILL_CREATE_OPENED = "bill_create_opened"
    BILL_CREATE_STEP = "bill_create_step"
    BILL_CREATED = "bill_created"
    SHARE_INVITE = "share_invite"
    # A seat or «I've paid» under a bill's post in a chat.
    PARTICIPANT_JOINED = "participant_joined"
    PAYMENT_MARKED = "payment_marked"
    POST_ACTION_REFUSED = "post_action_refused"
    # «Refresh» under a post: edited, unchanged, gone, cooldown or error.
    POST_REFRESHED = "post_refreshed"
    REMINDERS_SENT = "reminders_sent"
    # How a reminder ended, for the person it was meant for: delivered, or why not.
    REMINDER_RESULT = "reminder_result"
    RECEIPT_SCAN_STARTED = "receipt_scan_started"
    RECEIPT_SCAN_RESULT = "receipt_scan_result"
    # A bill said out loud: sent to be understood, and how that ended.
    VOICE_INPUT_SENT = "voice_input_sent"
    VOICE_INPUT_RESULT = "voice_input_result"
    PAYWALL_OPENED = "paywall_opened"
    # Done by the server for someone, on a schedule.
    BILL_CLOSED = "bill_closed"
    BROADCAST_RESULT = "broadcast_result"
    # The bot handed the invite to an owner nobody had joined, or told them who paid.
    INVITE_NUDGE_RESULT = "invite_nudge_result"
    PAYMENT_NOTICE_RESULT = "payment_notice_result"
    PRO_OFFER_STARTED = "pro_offer_started"
    PRO_PURCHASED = "pro_purchased"
    PRO_REFUNDED = "pro_refunded"


class Surface(str, Enum):
    """Where it happened; the Mini App marks its own events as mini_app."""
    BOT = "bot"
    # Not tied to a screen: a payment arrives the same way from the app and the bot.
    SERVER = "server"


@cache
def _client() -> Posthog | None:
    key = os.getenv("POSTHOG_KEY")
    if not key:
        return None
    return Posthog(key, host=os.getenv("POSTHOG_HOST") or DEFAULT_HOST)


def set_person(user_id: int, **properties) -> None:
    """Person properties the server knows best, such as an operator marking
    someone as one of the team. Like capture, a failure is only logged."""
    client = _client()
    if client is None:
        return
    try:
        client.set(distinct_id=str(user_id), properties=properties)
    except Exception as error:
        logger.warning("Could not set person properties: %s", error)


def set_person_once(user_id: int, **properties) -> None:
    """Person properties that hold from the first time they are set, such as
    how someone first came in. Like capture, a failure is only logged."""
    client = _client()
    if client is None:
        return
    try:
        client.set_once(distinct_id=str(user_id), properties=properties)
    except Exception as error:
        logger.warning("Could not set person properties once: %s", error)


def capture(user_id: int, event: ProductEvent, surface: Surface, **properties) -> None:
    """Queued and sent in the background; a failure is only logged, never in
    the way of what is being counted."""
    client = _client()
    if client is None:
        return
    try:
        client.capture(
            event.value,
            distinct_id=str(user_id),
            properties={"surface": surface.value, **properties},
        )
    except Exception as error:
        logger.warning("Could not capture %s: %s", event.value, error)
