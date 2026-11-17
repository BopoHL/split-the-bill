"""Telegram's side of the bot tests."""
from itertools import count

_update_ids = count(1)

# The bot worker the tests act as.
WORKER = "tests"


def next_update_id() -> int:
    """A fresh update id, as Telegram gives every update: the bot keeps an
    update delivered twice only once."""
    return next(_update_ids)
