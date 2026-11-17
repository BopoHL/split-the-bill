"""A bill rendered for a chat: the card, and the buttons that go under it.

Several places need the same card — the list of past bills, the message that
goes out once a receipt has been read — so it belongs to none of them.
"""
from html import escape

from app.utils.bot_copy import t
from app.utils.currency import format_amount as format_tiins, to_tiins
from app.utils.telegram import mini_app_link

# Asks the bot to post the invite into this chat, ready to be forwarded.
INVITE_PREFIX = "invite:"

# Long receipts are common and a wall of forty lines is unreadable in a chat.
# The rest is one tap away in the app.
MAX_ITEMS = 10


def format_amount(amount: float, currency: str, language: str | None = None) -> str:
    """Amounts reach a card as major units — the responses they are read from
    have already been converted — so they go back through the same conversion
    the rest of the app measures in."""
    return format_tiins(to_tiins(amount), currency, language)


def participant_name(participant, fallback: str) -> str:
    return (
        participant.name
        or participant.guest_name
        or (f"@{participant.username}" if participant.username else None)
        or fallback
    )


def render_bill_card(bill, language: str) -> str:
    title = escape(bill.title or t(language, "bill_untitled"))
    lines = [f"🧾 <b>{title}</b>", ""]

    items = bill.items or []
    if items:
        lines.append(f"<b>{t(language, 'card_items')}</b>")
        for item in items[:MAX_ITEMS]:
            count = f" × {item.count}" if item.count > 1 else ""
            amount = format_amount(item.item_sum, bill.currency, language)
            lines.append(f"• {escape(item.name)}{count} — {amount}")
        if len(items) > MAX_ITEMS:
            lines.append(t(language, "card_more_items").format(n=len(items) - MAX_ITEMS))
    else:
        lines.append(t(language, "card_no_items"))

    lines += ["", f"<b>{t(language, 'card_total')}:</b> {format_amount(bill.total_sum, bill.currency, language)}"]

    people = [p for p in (bill.participants or []) if p.user_id or p.guest_name]
    if people:
        names = ", ".join(
            escape(participant_name(p, t(language, "bill_untitled"))) for p in people
        )
        lines.append(f"<b>{t(language, 'card_participants')}:</b> {names}")

    return "\n".join(lines)


def open_bill_button(token: str, language: str) -> dict:
    """Opens the bill in the Mini App, straight on its page."""
    return {"text": t(language, "btn_open_bill"), "url": mini_app_link(f"bill_{token}")}


def invite_button(token: str, language: str) -> dict:
    """Asks the bot to post the invite here, for the user to forward on.

    switch_inline_query was tried and dropped: it depends on inline mode being
    enabled on the bot and on the client having noticed, it cannot explain
    itself when either is missing, and the buttons already sitting in old
    messages keep the behaviour they were sent with. A posted message works on
    every client, and forwarding keeps the photo, the caption and the button
    intact.
    """
    return {
        "text": t(language, "btn_invite"),
        "callback_data": f"{INVITE_PREFIX}{token}",
    }
