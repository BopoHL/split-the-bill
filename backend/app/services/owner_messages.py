"""What the bot tells a bill's owner on its own — the invite to forward, who
has paid — sent only where it may write to them, and counted either way."""
import logging
from collections.abc import Callable

from app.models import Bill, User
from app.services.product_events import ProductEvent, Surface, capture
from app.services.shared_bill_service import language_of
from app.services.user_service import UserService, bot_may_write
from app.utils.telegram import is_unreachable_chat, send_message

logger = logging.getLogger(__name__)

# The text and the keyboard of a message, written in the owner's language.
Message = tuple[str, dict]


def tell_owner(
    users: UserService,
    bill: Bill,
    owner: User | None,
    event: ProductEvent,
    write: Callable[[str], Message],
) -> bool:
    """Sends the owner what `write` puts in their language and counts under
    `event` how it went. True when the message got through."""
    reason = _send(users, bill, owner, write)
    capture(
        bill.owner_id,
        event,
        Surface.SERVER,
        bill_id=bill.id,
        ok=reason is None,
        **({"reason": reason} if reason else {}),
    )
    return reason is None


def _send(users: UserService, bill: Bill, owner: User | None, write: Callable[[str], Message]) -> str | None:
    """Why the message did not get through, or None when it did."""
    if owner is None or not owner.telegram_id or not bot_may_write(owner):
        return "no_chat"
    text, markup = write(language_of(owner))
    try:
        send_message(owner.telegram_id, text, markup)
    except RuntimeError as error:
        if not is_unreachable_chat(error):
            logger.warning("Message to the owner of bill %s not sent: %s", bill.id, error)
            return "error"
        users.note_write_access(owner, False)
        return "unreachable"
    return None
