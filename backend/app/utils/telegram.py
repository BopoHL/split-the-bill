import json
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TELEGRAM_API = "https://api.telegram.org"

# One kept-alive connection pool for every call: opening TCP and TLS anew took
# longer than Telegram took to answer. Sized for the bot's workers plus the
# calls some of them make side by side. A connection that fails to open is
# tried once more; a request that may have reached Telegram never is — sent
# twice, a message would arrive twice.
_http = requests.Session()
_http.mount(
    "https://",
    HTTPAdapter(pool_maxsize=16, max_retries=Retry(total=None, connect=1, read=0, redirect=0, status=0, other=0)),
)
# Telegram accepts a connection in a fraction of a second; one it has not
# accepted by now is not coming, and waiting for it holds the caller up.
CONNECT_TIMEOUT = 3.05


def _timeout(read: float) -> tuple[float, float]:
    return min(CONNECT_TIMEOUT, read), read

# The Mini App's short name, as registered with BotFather. Without it a t.me
# link opens the chat with the bot rather than the app.
MINI_APP_SHORT_NAME = "app"


def bot_username() -> str:
    return os.getenv("TG_BOT_USERNAME", "SplitTheBillsBot").lstrip("@")


def mini_app_link(startapp: str | None = None) -> str:
    """A link that opens the Mini App itself, optionally on a given screen."""
    link = f"https://t.me/{bot_username()}/{MINI_APP_SHORT_NAME}"
    return f"{link}?startapp={startapp}" if startapp else link


def bot_link() -> str:
    """The private chat with the bot."""
    return f"https://t.me/{bot_username()}"


def bot_start_link(start: str) -> str:
    """A link that opens the chat with the bot, whose Start sends `/start <start>`."""
    return f"https://t.me/{bot_username()}?start={start}"


def send_message(
    chat_id: int,
    text: str,
    reply_markup: dict | None = None,
    parse_mode: str | None = "HTML",
    link_preview_options: dict | None = None,
) -> dict:
    """Send a message to a chat via the Bot API. `reply_markup` is passed
    through verbatim (e.g. an inline keyboard with a `web_app` button that
    opens the Mini App). Link previews are off unless `link_preview_options`
    asks for one. Raises RuntimeError on misconfiguration or a Telegram API
    failure so callers can decide whether to swallow it."""
    token = os.getenv("TG_TOKEN")
    if not token:
        raise RuntimeError("TG_TOKEN is not configured")

    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "link_preview_options": link_preview_options or {"is_disabled": True},
    }
    # Omitted entirely for plain text — Telegram rejects a null parse_mode.
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        resp = _http.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json=payload,
            timeout=_timeout(10),
        )
        data = resp.json()
    except Exception as e:  # network / decode errors
        raise RuntimeError(f"Telegram request failed: {e}")

    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data.get('description', 'unknown')}")
    return data["result"]


# What Telegram says when a chat cannot be written to: the user blocked the
# bot, never started it (so the bot may not open the conversation), has no
# chat with it at all, or deleted the account. Retrying any of these is
# pointless, so every sender treats them apart from a transient failure.
_UNREACHABLE_CHAT = (
    "blocked",
    "can't initiate conversation",
    "chat not found",
    "deactivated",
)


def is_unreachable_chat(error: Exception | str) -> bool:
    message = str(error).lower()
    return any(reason in message for reason in _UNREACHABLE_CHAT)


def send_photo(
    chat_id: int,
    photo: str | None = None,
    caption: str | None = None,
    reply_markup: dict | None = None,
    parse_mode: str = "HTML",
    photo_path: str | None = None,
) -> dict:
    """Send a photo with an optional caption and inline keyboard.

    Two ways to name the picture, and exactly one of them is expected:
    `photo` is something Telegram can already resolve on its own — a public URL
    or a file_id it handed out earlier — while `photo_path` is a local file that
    has to be uploaded. Same error contract as `send_message`.
    """
    token = os.getenv("TG_TOKEN")
    if not token:
        raise RuntimeError("TG_TOKEN is not configured")
    if (photo is None) == (photo_path is None):
        raise RuntimeError("Pass either photo or photo_path")

    payload: dict = {"chat_id": chat_id}
    if photo is not None:
        payload["photo"] = photo
    if caption is not None:
        payload["caption"] = caption
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        if photo_path is not None:
            # Multipart, so the fields that are dicts in JSON have to be encoded
            # by hand — requests would otherwise send them as Python reprs.
            form = {
                key: (value if isinstance(value, str) else json.dumps(value))
                for key, value in payload.items()
                if key != "chat_id"
            }
            form["chat_id"] = str(chat_id)
            with open(photo_path, "rb") as handle:
                resp = _http.post(
                    f"{TELEGRAM_API}/bot{token}/sendPhoto",
                    data=form,
                    files={"photo": handle},
                    timeout=_timeout(30),
                )
        else:
            resp = _http.post(
                f"{TELEGRAM_API}/bot{token}/sendPhoto",
                json=payload,
                timeout=_timeout(10),
            )
        data = resp.json()
    except Exception as e:  # network / decode errors
        raise RuntimeError(f"Telegram request failed: {e}")

    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data.get('description', 'unknown')}")
    return data["result"]


def send_rich_message(chat_id: int, html: str, reply_markup: dict | None = None) -> dict:
    """Send a rich message (Bot API 10.1+): headings, lists, tables and pictures
    between paragraphs. Telegram downloads each picture from its address while
    sending, so this waits longer than a plain message. Same error contract as
    `send_message`."""
    payload: dict = {"chat_id": chat_id, "rich_message": {"html": html}}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _call("sendRichMessage", payload, timeout=30)


def largest_photo_file_id(result: dict) -> str | None:
    """Telegram answers sendPhoto with every size it generated, smallest first.
    The last one is the original, and its file_id is what later sends reuse."""
    sizes = result.get("photo") or []
    return sizes[-1].get("file_id") if sizes else None


def save_prepared_text_message(
    telegram_user_id: int,
    *,
    result_id: str,
    title: str,
    description: str,
    text_html: str,
    link_preview_options: dict,
    reply_markup: dict,
    private_chats_only: bool = False,
) -> str:
    """Store a text message the user can share from the Mini App, with a link
    preview Telegram draws above it. `result_id` comes back in
    chosen_inline_result, which is how the bot learns the message it became.
    `private_chats_only` keeps a message meant for one person out of groups
    and channels."""
    result = {
        "type": "article",
        "id": result_id[:64],
        "title": title[:256] or "Split The Bill",
        "description": description[:256],
        "input_message_content": {
            "message_text": text_html,
            "parse_mode": "HTML",
            "link_preview_options": link_preview_options,
        },
        "reply_markup": reply_markup,
    }
    if private_chats_only:
        return _save_prepared(
            telegram_user_id, result, allow_group_chats=False, allow_channel_chats=False, allow_bot_chats=False
        )
    return _save_prepared(telegram_user_id, result, allow_bot_chats=False)


def save_prepared_photo_message(
    telegram_user_id: int,
    *,
    result_id: str,
    photo_url: str,
    caption: str,
    reply_markup: dict,
) -> str:
    """Store a photo the user can share from the Mini App. Telegram's servers
    fetch it from `photo_url`, which has to be a JPEG; it stands in as its own
    thumbnail."""
    result = {
        "type": "photo",
        "id": result_id[:64],
        "photo_url": photo_url,
        "thumbnail_url": photo_url,
        "caption": caption[:1024],
        "reply_markup": reply_markup,
    }
    return _save_prepared(telegram_user_id, result, allow_bot_chats=False)


def _save_prepared(telegram_user_id: int, result: dict, **allowed: bool) -> str:
    payload = {
        "user_id": telegram_user_id,
        "result": result,
        "allow_user_chats": allowed.get("allow_user_chats", True),
        "allow_group_chats": allowed.get("allow_group_chats", True),
        "allow_channel_chats": allowed.get("allow_channel_chats", True),
        "allow_bot_chats": allowed.get("allow_bot_chats", False),
    }
    return _call("savePreparedInlineMessage", payload)["id"]


def edit_inline_message_text(
    inline_message_id: str,
    text_html: str,
    link_preview_options: dict,
    reply_markup: dict,
) -> None:
    """Rewrite a message sent through the bot in inline mode. The keyboard has
    to be sent again every time: an edit without one takes the buttons away."""
    _call(
        "editMessageText",
        {
            "inline_message_id": inline_message_id,
            "text": text_html,
            "parse_mode": "HTML",
            "link_preview_options": link_preview_options,
            "reply_markup": reply_markup,
        },
    )


def edit_chat_message_text(
    chat_id: int,
    message_id: int,
    text_html: str,
    link_preview_options: dict,
    reply_markup: dict,
) -> None:
    """Rewrite a message the bot sent into a chat itself; the keyboard goes
    again with it, as with an inline message."""
    _call(
        "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text_html,
            "parse_mode": "HTML",
            "link_preview_options": link_preview_options,
            "reply_markup": reply_markup,
        },
    )


def is_unchanged_message(error: Exception | str) -> bool:
    """Telegram refuses an edit that would change nothing — which is fine."""
    return "message is not modified" in str(error).lower()


def is_refused(error: Exception | str) -> bool:
    """Telegram answered and said no — unlike an answer that never came, after
    which the message may well have gone out."""
    return str(error).startswith("Telegram error")


# An edit that can never succeed: the message was deleted, or the id is not
# one Telegram knows.
_MISSING_MESSAGE = ("message_id_invalid", "message to edit not found", "message can't be edited")


def is_missing_message(error: Exception | str) -> bool:
    message = str(error).lower()
    return any(reason in message for reason in _MISSING_MESSAGE)


def _call(method: str, payload: dict, timeout: float = 10) -> dict:
    """Thin Bot API call for the plain-JSON methods. Same error contract as
    `send_message`: misconfiguration and API failures raise RuntimeError."""
    token = os.getenv("TG_TOKEN")
    if not token:
        raise RuntimeError("TG_TOKEN is not configured")

    try:
        resp = _http.post(f"{TELEGRAM_API}/bot{token}/{method}", json=payload, timeout=_timeout(timeout))
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Telegram request failed: {e}")

    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data.get('description', 'unknown')}")
    return data["result"]


def answer_callback_query(
    callback_query_id: str, text: str | None = None, show_alert: bool = False, url: str | None = None,
) -> None:
    """Stop the spinner on a tapped inline button. Telegram keeps it turning
    for a minute otherwise, which reads as a hung bot. `text` is seen by the
    person who tapped only — a passing note, or with `show_alert` a box they
    close themselves. `url`, a `bot_start_link`, opens the chat with the bot."""
    payload: dict = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    if url:
        payload["url"] = url
    _call("answerCallbackQuery", payload)


def create_invoice_link(invoice: dict) -> str:
    """A link the Mini App opens with WebApp.openInvoice. In Telegram Stars
    there is no payment provider: its token stays empty."""
    return _call("createInvoiceLink", {"provider_token": "", **invoice})


def refund_star_payment(telegram_user_id: int, charge_id: str) -> None:
    _call("refundStarPayment", {"user_id": telegram_user_id, "telegram_payment_charge_id": charge_id})


def edit_star_subscription(telegram_user_id: int, first_charge_id: str, canceled: bool) -> None:
    """Stop Telegram renewing a subscription, which stays paid to the end of its
    month — or let it renew again."""
    _call(
        "editUserStarSubscription",
        {"user_id": telegram_user_id, "telegram_payment_charge_id": first_charge_id, "is_canceled": canceled},
    )


def answer_pre_checkout_query(query_id: str, error_message: str | None = None) -> None:
    """Let a payment through, or stop it with a reason the payer reads. Telegram
    waits ten seconds for this before giving up on the payment."""
    payload: dict = {"pre_checkout_query_id": query_id, "ok": error_message is None}
    if error_message:
        payload["error_message"] = error_message
    _call("answerPreCheckoutQuery", payload)


def delete_message(chat_id: int, message_id: int) -> None:
    """Take a message out of the chat. In a private chat a bot may delete its
    own messages and the person's, for 48 hours after they were sent."""
    _call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def clear_inline_keyboard(chat_id: int, message_id: int) -> None:
    """Retire the buttons under a message we've moved on from. Without this the
    old step stays tappable and users can answer the same question twice."""
    _call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id})


def download_file(file_id: str, timeout: float = 20.0) -> bytes:
    """Fetch the bytes behind a file_id.

    Telegram hands out an id first and the storage path second, so this is two
    calls: getFile to resolve the path, then a plain download from the file
    endpoint. Same error contract as the rest of this module.
    """
    token = os.getenv("TG_TOKEN")
    if not token:
        raise RuntimeError("TG_TOKEN is not configured")

    file_path = _call("getFile", {"file_id": file_id}, timeout=timeout).get("file_path")
    if not file_path:
        raise RuntimeError("Telegram returned no file_path")

    try:
        resp = _http.get(f"{TELEGRAM_API}/file/bot{token}/{file_path}", timeout=_timeout(timeout))
    except Exception as e:
        raise RuntimeError(f"Telegram download failed: {e}")

    if resp.status_code != 200:
        raise RuntimeError(f"Telegram download failed with {resp.status_code}")
    return resp.content


def profile_photo(telegram_user_id: int, min_side: int, timeout: float) -> bytes | None:
    """The person's current profile photo, in the smallest size at least
    `min_side` wide, or None when they have none a bot may see."""
    photos = _call(
        "getUserProfilePhotos", {"user_id": telegram_user_id, "limit": 1}, timeout=timeout
    ).get("photos") or []
    if not photos or not photos[0]:
        return None
    sizes = sorted(photos[0], key=lambda size: size.get("width", 0))
    chosen = next((size for size in sizes if size.get("width", 0) >= min_side), sizes[-1])
    return download_file(chosen["file_id"], timeout=timeout)


def set_my_commands(commands: list[dict], language_code: str | None = None) -> None:
    """Publish the slash-command list Telegram shows in the chat.

    Idempotent — it replaces the list for the given language, so re-running it
    on every start is free. Pass no language to set the fallback list.
    """
    payload: dict = {"commands": commands}
    if language_code:
        payload["language_code"] = language_code
    _call("setMyCommands", payload)
