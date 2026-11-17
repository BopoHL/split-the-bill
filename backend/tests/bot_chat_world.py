"""Chats with the bot, as Telegram would keep them.

Every message lands here under an id from one sequence, the person's and the
bot's alike, as in a private chat; edits rewrite it, deletions take it out.
Tests read the chat the way a person would see it, so «the menu stayed one
message» is something they can check. A group is any chat id below zero.
"""
from dataclasses import dataclass, field
from itertools import count

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

import app.services.bot_flow_service as flow
import app.services.bot_panel as panel
import app.services.bot_pro as bot_pro
import app.services.shared_bill_service as shared
from app.models import TelegramUpdate
from tests.telegram_world import next_update_id

CHAT_ID = 42
GROUP_ID = -100500


@dataclass
class Message:
    id: int
    chat_id: int
    kind: str
    text: str
    markup: dict | None
    photo: str | None = None
    deleted: bool = False

    def buttons(self) -> list[dict]:
        return [button for row in (self.markup or {}).get("inline_keyboard", []) for button in row]

    def labels(self) -> list[str]:
        return [button["text"] for button in self.buttons()]

    def callbacks(self) -> list[str]:
        return [button["callback_data"] for button in self.buttons() if "callback_data" in button]


@dataclass
class BotChat:
    client: TestClient
    session: Session
    messages: dict[int, Message] = field(default_factory=dict)
    deleted_input: list[int] = field(default_factory=list)
    answers: list[tuple[str | None, bool]] = field(default_factory=list)
    refuse_rich: bool = False
    undeletable: set[int] = field(default_factory=set)
    refuse_photo: bool = False
    _ids: count = field(default_factory=lambda: count(100))

    # -- what the person does ----------------------------------------------

    def say(
        self, text: str | None = None, photo: list | None = None, language_code: str = "ru", chat_id: int = CHAT_ID,
        voice: dict | None = None,
    ) -> int:
        message_id = next(self._ids)
        message = {
            "message_id": message_id,
            "chat": {"id": chat_id, "type": "private" if chat_id > 0 else "supergroup"},
            "from": {"id": CHAT_ID, "language_code": language_code, "first_name": "Lea"},
        }
        if text is not None:
            message["text"] = text
        if photo is not None:
            message["photo"] = photo
        if voice is not None:
            message["voice"] = voice
        self._deliver({"message": message})
        return message_id

    def typed(self) -> int:
        """The id a message of the person's takes, for tests that skip the webhook."""
        return next(self._ids)

    def tap(self, data: str, on: Message | int | None = None, chat_id: int = CHAT_ID) -> None:
        if isinstance(on, int):
            source = on
        else:
            # Nothing on screen yet: the button sits under some message from before.
            source = (on or self.last()).id if on or self.visible() else 1
        self._deliver({"callback_query": {
            "id": "cb",
            "data": data,
            "from": {"id": CHAT_ID, "language_code": "ru", "first_name": "Lea"},
            "message": {"message_id": source, "chat": {"id": chat_id, "type": "private" if chat_id > 0 else "supergroup"}},
        }})

    def _deliver(self, update: dict) -> None:
        """The worker records a failure instead of raising it; a test should see it."""
        update_id = next_update_id()
        self.client.post("/telegram/webhook", json={"update_id": update_id, **update})
        kept = self.session.get(TelegramUpdate, update_id)
        self.session.refresh(kept)
        assert kept.error is None, kept.error

    # -- what the person sees ----------------------------------------------

    def visible(self, chat_id: int = CHAT_ID) -> list[Message]:
        return [m for m in self.messages.values() if m.chat_id == chat_id and not m.deleted]

    def last(self, chat_id: int = CHAT_ID) -> Message:
        return self.visible(chat_id)[-1]

    # -- Telegram ----------------------------------------------------------

    def _add(self, chat_id: int, kind: str, text: str, markup: dict | None, photo: str | None = None) -> dict:
        web_app = any("web_app" in button for row in (markup or {}).get("inline_keyboard", []) for button in row)
        if chat_id < 0 and web_app:
            raise RuntimeError("Telegram error: Bad Request: BUTTON_TYPE_INVALID")
        message = Message(next(self._ids), chat_id, kind, text, markup, photo)
        self.messages[message.id] = message
        return {"message_id": message.id}

    def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        return self._add(chat_id, "text", text, reply_markup)

    def send_photo(self, chat_id, photo=None, caption=None, reply_markup=None, **kwargs):
        if self.refuse_photo:
            raise RuntimeError("Telegram error: Bad Request: wrong file identifier/HTTP URL specified")
        return self._add(chat_id, "photo", caption or "", reply_markup, photo or kwargs.get("photo_path"))

    def send_rich_message(self, chat_id, html, reply_markup=None):
        if self.refuse_rich:
            raise RuntimeError("Telegram error: Bad Request: can't parse rich message")
        return self._add(chat_id, "rich", html, reply_markup)

    def edit_chat_message_text(self, chat_id, message_id, text_html, link_preview_options, reply_markup):
        message = self.messages.get(message_id)
        if message is None or message.deleted:
            raise RuntimeError("Telegram error: Bad Request: message to edit not found")
        if message.kind != "text":
            raise RuntimeError("Telegram error: Bad Request: there is no text in the message to edit")
        if (message.text, message.markup) == (text_html, reply_markup):
            raise RuntimeError("Telegram error: Bad Request: message is not modified")
        message.text, message.markup = text_html, reply_markup

    def delete_message(self, chat_id, message_id):
        if message_id in self.undeletable:
            raise RuntimeError("Telegram error: Bad Request: message can't be deleted")
        message = self.messages.get(message_id)
        if message is None:
            self.deleted_input.append(message_id)
        else:
            message.deleted = True

    def clear_inline_keyboard(self, chat_id, message_id):
        self.messages[message_id].markup = None

    def answer_callback_query(self, callback_id, text=None, show_alert=False, url=None):
        self.answers.append((text, show_alert))


@pytest.fixture
def bot_chat(client: TestClient, session: Session, monkeypatch) -> BotChat:
    chat = BotChat(client, session)
    for name in ("send_message", "send_rich_message", "edit_chat_message_text", "delete_message", "clear_inline_keyboard"):
        monkeypatch.setattr(panel, name, getattr(chat, name))
    for name in ("send_message", "send_photo", "answer_callback_query"):
        monkeypatch.setattr(flow, name, getattr(chat, name))
    monkeypatch.setattr(flow, "download_file", lambda file_id, **k: b"receipt-bytes")
    monkeypatch.setattr(bot_pro, "answer_callback_query", chat.answer_callback_query)
    monkeypatch.setattr(bot_pro, "create_invoice_link", lambda invoice: f"https://t.me/$invoice-{invoice['payload']}")
    monkeypatch.setattr(shared, "send_message", chat.send_message)
    monkeypatch.setenv("TG_BOT_USERNAME", "SplitTheBillsBot")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz")
    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)
    return chat
