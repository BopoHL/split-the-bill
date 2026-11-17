"""Where someone came from, as the links we hand out say it.

A post, an ad or a broadcast carries `src_<channel>` as its start parameter,
for the Mini App (startapp) and the bot (/start) alike.
"""
import re

SOURCE_PREFIX = "src_"
SOURCE_MAX = 64


def source_of(start: str | None) -> str | None:
    """The channel a `src_` start names, kept to what an analytics label can be."""
    if not start or not start.startswith(SOURCE_PREFIX):
        return None
    return re.sub(r"[^a-z0-9_-]", "", start.removeprefix(SOURCE_PREFIX).lower())[:SOURCE_MAX] or None
