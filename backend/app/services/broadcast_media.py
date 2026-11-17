"""Pictures for rich broadcasts.

A rich message names its pictures by address, and Telegram downloads them while
sending — so they are served without auth, under unguessable names, the way the
receipt behind an invite is. A picture is not tied to one broadcast: the same
one can go into several, and a stray file costs less than the bookkeeping.
"""
import os
import re
import uuid

from app.utils.images import compress_image

MEDIA_DIR = "storage/broadcast-media"
_NAME = re.compile(r"^[0-9a-f]{32}\.jpg$")


class NotAnImage(ValueError):
    pass


class NoPublicAddress(RuntimeError):
    pass


def _public_base_url() -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise NoPublicAddress("PUBLIC_BASE_URL не задан — Telegram не сможет скачать картинку")
    return base


def save(raw: bytes) -> str:
    """Store a picture and return the address Telegram will download it from."""
    base = _public_base_url()
    compressed = compress_image(raw)
    if compressed is None:
        raise NotAnImage("File is not a readable image")
    data, extension, _mime = compressed

    name = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(os.path.join(MEDIA_DIR, name), "wb") as handle:
        handle.write(data)
    return f"{base}/api/broadcasts/media/{name}"


def path_of(name: str) -> str | None:
    if not _NAME.match(name):
        return None
    path = os.path.join(MEDIA_DIR, name)
    return path if os.path.exists(path) else None
