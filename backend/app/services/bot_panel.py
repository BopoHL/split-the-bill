"""The bot's panel: one message per chat that the conversation redraws.

Everything that is a place rather than news — the menu, settings, the list of
bills, a bill's card, the steps of creating one — is drawn into the panel. A
tap on the panel redraws it where it stands; a typed command, or a tap on any
other message, opens a fresh panel at the bottom and takes the old one down.
News — a receipt that has been read, a reminder, an invite to forward — still
arrives as messages of its own, and stays.
"""
import logging
from dataclasses import dataclass, field, replace

from app.models import BotPanel, BotPanelKind
from app.repositories.bot_panel_repo import BotPanelRepository
from app.utils.telegram import (
    clear_inline_keyboard,
    delete_message,
    edit_chat_message_text,
    is_refused,
    is_unchanged_message,
    send_message,
    send_rich_message,
)

logger = logging.getLogger(__name__)

NO_PREVIEW = {"is_disabled": True}


@dataclass(frozen=True)
class View:
    """`fallback` is the rich view as an ordinary message, for when Telegram
    refuses the rich one. `screen` is the place it is, as bot_screen_viewed
    names it, and `screen_properties` what else that event says about it; a
    flow's question or an error is no place, and has none."""

    text: str
    rows: list[list[dict]] = field(default_factory=list)
    rich: bool = False
    fallback: str | None = None
    screen: str | None = None
    screen_properties: dict = field(default_factory=dict)

    def with_rows(self, *rows: list[dict]) -> "View":
        return replace(self, rows=[*self.rows, *rows])

    def markup(self) -> dict:
        return {"inline_keyboard": self.rows}


class BotPanels:
    def __init__(self, repo: BotPanelRepository):
        self.repo = repo

    def is_panel(self, chat_id: int, message_id: int | None) -> bool:
        panel = self.repo.get_by_chat(chat_id)
        return panel is not None and panel.message_id == message_id

    def tapped(self, chat_id: int, message_id: int | None, view: View) -> None:
        if self.is_panel(chat_id, message_id):
            self.redraw(chat_id, view)
        else:
            self.open(chat_id, view)

    def redraw(self, chat_id: int, view: View) -> None:
        """Telegram edits text into text only, so a rich side means a fresh panel."""
        panel = self.repo.get_by_chat(chat_id)
        if panel is None or view.rich or panel.kind != BotPanelKind.TEXT:
            self.open(chat_id, view)
            return
        try:
            edit_chat_message_text(chat_id, panel.message_id, view.text, NO_PREVIEW, view.markup())
        except RuntimeError as e:
            if is_unchanged_message(e):
                return
            logger.warning("Could not redraw the panel in chat %s, opening a fresh one: %s", chat_id, e)
            self.open(chat_id, view)

    def answer(self, chat_id: int, message_id: int, view: View, clear: bool = True) -> None:
        """What the person typed in reply to the panel. Right under it, the
        panel changes in place; with something in between — a read receipt,
        an invite — it moves down under the reply instead, or the answer would
        land out of sight. The reply itself goes either way.

        A private chat numbers every message, either side's, in one sequence,
        which is how «right under it» is told. `clear=False` leaves the reply
        where it is: a receipt photo the bot did not keep is the person's only copy."""
        panel = self.repo.get_by_chat(chat_id)
        if panel is not None and message_id == panel.bottom_message_id + 1:
            self.redraw(chat_id, view)
        else:
            self.open(chat_id, view)
        if clear and self.clear_input(chat_id, message_id):
            panel = self.repo.get_by_chat(chat_id)
            panel.bottom_message_id = max(panel.bottom_message_id, message_id)
            self.repo.save(panel)

    def open(self, chat_id: int, view: View) -> None:
        """The old panel comes down only once the new one is there, so a failed
        send leaves the chat as it was."""
        message_id, kind = self._send(chat_id, view)
        panel = self.repo.get_by_chat(chat_id)
        if panel is None:
            panel = BotPanel(chat_id=chat_id, message_id=message_id, bottom_message_id=message_id, kind=kind)
        else:
            self._take_down(chat_id, panel.message_id)
            panel.message_id = panel.bottom_message_id = message_id
            panel.kind = kind
        self.repo.save(panel)

    def close(self, chat_id: int) -> None:
        panel = self.repo.get_by_chat(chat_id)
        if panel is None:
            return
        self._take_down(chat_id, panel.message_id)
        self.repo.delete(panel)

    def remove(self, chat_id: int, message_id: int | None) -> None:
        """A message whose question has been answered, panel or not."""
        if self.is_panel(chat_id, message_id):
            self.close(chat_id)
        elif message_id is not None:
            self._take_down(chat_id, message_id)

    def clear_input(self, chat_id: int, message_id: int | None) -> bool:
        if message_id is None:
            return False
        try:
            delete_message(chat_id, message_id)
            return True
        except RuntimeError as e:
            logger.info("Could not delete message %s in chat %s: %s", message_id, chat_id, e)
            return False

    def _send(self, chat_id: int, view: View) -> tuple[int, BotPanelKind]:
        if view.rich:
            try:
                sent = send_rich_message(chat_id, view.text, view.markup())
                return sent["message_id"], BotPanelKind.RICH
            except RuntimeError as e:
                # Without an answer the rich one may have gone out; a plain copy
                # would sit next to it.
                if view.fallback is None or not is_refused(e):
                    raise
                logger.warning("Rich panel refused in chat %s, sending it plain: %s", chat_id, e)
        text = view.fallback if view.rich else view.text
        sent = send_message(chat_id, text, view.markup())
        return sent["message_id"], BotPanelKind.TEXT

    @staticmethod
    def _take_down(chat_id: int, message_id: int) -> None:
        """Telegram deletes only messages younger than 48 hours; an older one
        loses its buttons instead."""
        try:
            delete_message(chat_id, message_id)
            return
        except RuntimeError as e:
            logger.info("Could not delete the old panel in chat %s: %s", chat_id, e)
        try:
            clear_inline_keyboard(chat_id, message_id)
        except RuntimeError as e:
            logger.info("Could not disarm the old panel in chat %s: %s", chat_id, e)
