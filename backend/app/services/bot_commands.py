"""The bot's slash-command list, published from the copy it is written in.

BotFather can hold this list too, but then it lives in three languages nobody
edits alongside the code and drifts on the first copy change. Registering it at
startup keeps the two in step: change a description in bot_copy, deploy, done.
"""
import logging
import os

from app.utils.bot_copy import DEFAULT_LANGUAGE, LANGUAGES, t
from app.utils.telegram import set_my_commands

logger = logging.getLogger(__name__)

# Command name -> the bot_copy key describing it.
COMMANDS = {
    "menu": "cmd_menu",
    "new": "cmd_new",
    "bills": "cmd_bills",
    "settings": "cmd_settings",
    "help": "cmd_help",
    "pro": "cmd_pro",
    "start": "cmd_start",
}


def _commands_for(language: str) -> list[dict]:
    return [
        {"command": name, "description": t(language, key)}
        for name, key in COMMANDS.items()
    ]


def register_bot_commands() -> None:
    """Called once at startup. Never fatal: a bot without a published command
    list still works, an API that refuses to boot does not."""
    if not os.getenv("TG_TOKEN"):
        logger.info("TG_TOKEN unset, skipping command registration")
        return

    # Without a list for no language in particular, anyone whose Telegram speaks
    # none of ours would see no commands at all.
    lists = {None: _commands_for(DEFAULT_LANGUAGE)} | {language: _commands_for(language) for language in LANGUAGES}
    for language, commands in lists.items():
        try:
            set_my_commands(commands, language_code=language)
        except RuntimeError as e:
            logger.warning("Could not register /commands for %s: %s", language or "everyone else", e)
