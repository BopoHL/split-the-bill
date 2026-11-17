"""Addresses of a person's analytics pictures that Telegram can fetch.

A story's picture is fetched by the person's Telegram app and a shared photo
by Telegram's servers, neither with the Mini App's session, so the address is
the permission: it names the picture, the period and the colours, says until
when it is good, and carries a signature only this server can make. One is
handed out only to the person themselves, and for a day — long enough to
share the picture, not to keep a window onto their bills.
"""
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.services.analytics import Period, PeriodKind

LIFETIME = timedelta(days=1)
RECEIPT = "receipt"


@dataclass(frozen=True)
class PictureAddress:
    user_id: int
    # «receipt», or a story's name.
    picture: str
    period: Period
    theme: str
    expires: int

    def _message(self) -> bytes:
        period = self.period
        parts = (self.user_id, self.picture, period.kind.value, period.year or "", period.month or "", self.theme, self.expires)
        return "|".join(str(part) for part in parts).encode()

    def signature(self) -> str:
        return hmac.new(_key(), self._message(), hashlib.sha256).hexdigest()[:32]

    def holds(self, signature: str, now: datetime) -> bool:
        """Whether `signature` is this address's own, and it has not run out."""
        return self.expires >= now.timestamp() and hmac.compare_digest(self.signature(), signature)

    def url(self, base_url: str) -> str:
        query = {"period": self.period.kind.value, "theme": self.theme, "expires": self.expires}
        if self.period.year:
            query["year"] = self.period.year
        if self.period.month:
            query["month"] = self.period.month
        query["sig"] = self.signature()
        return f"{base_url.rstrip('/')}/api/public/analytics/{self.user_id}/{self.picture}.jpg?{urlencode(query)}"


def address_for(user_id: int, picture: str, period: Period, theme: str, now: datetime) -> PictureAddress:
    """A fresh address for one picture; `now` is an aware moment."""
    return PictureAddress(user_id, picture, period, theme, int((now + LIFETIME).timestamp()))


def asked(user_id: int, picture: str, kind: PeriodKind, year: int | None, month: int | None, theme: str, expires: int) -> PictureAddress:
    """The address a request came in on, read the way it was signed."""
    period = Period(kind, year=None if kind == PeriodKind.ALL else year, month=month if kind == PeriodKind.MONTH else None)
    return PictureAddress(user_id, picture, period, theme, expires)


def _key() -> bytes:
    """A key of its own, derived from the bot's token the way Telegram derives
    the one for Mini App data: nothing new to configure, and nothing signed
    here can pass for anything signed elsewhere."""
    token = os.getenv("TG_TOKEN")
    if not token:
        raise RuntimeError("TG_TOKEN is not set")
    return hmac.new(b"AnalyticsPictures", token.encode(), hashlib.sha256).digest()
