"""Settings an operator changes while the app is running.

Everything else lives in the environment, which is right for what only changes
with a deploy. This is for the handful of knobs whose whole purpose is to be
turned while watching what happens — so they are read fresh on every use rather
than cached into a process that would then have to be restarted to notice.
"""
import os
import re

from sqlmodel import Session

from app.models import AppSetting, ScanMode

SCAN_MODE_KEY = "scan_mode"
DEFAULT_SCAN_MODE = ScanMode.OCR_LLM

RECEIPT_MODEL_KEY = "receipt_model"
DEFAULT_RECEIPT_MODEL = "gpt-6-luna"


def get_setting(session: Session, key: str) -> str | None:
    row = session.get(AppSetting, key)
    return row.value if row else None


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(AppSetting, key)
    if row:
        row.value = value
    else:
        row = AppSetting(key=key, value=value)
    session.add(row)
    session.commit()


def get_scan_mode(session: Session) -> ScanMode:
    """How photos are being read right now.

    An unreadable value falls back rather than raising: a typo in one row must
    not stop every scan in the product.
    """
    stored = get_setting(session, SCAN_MODE_KEY)
    try:
        return ScanMode(stored)
    except ValueError:
        return DEFAULT_SCAN_MODE


def get_receipt_model(session: Session) -> str:
    """The model that reads receipts: the operator's pick, then the deploy's,
    then ours."""
    stored = (get_setting(session, RECEIPT_MODEL_KEY) or "").strip()
    if stored:
        return stored
    return os.getenv("OPENAI_RECEIPT_MODEL", "").strip() or DEFAULT_RECEIPT_MODEL


LABEL_MODEL_KEY = "label_model"
DEFAULT_LABEL_MODEL = "gpt-6-luna"


def get_label_model(session: Session) -> str:
    """The model that tells what a receipt line is and names the place: the
    operator's pick, then the deploy's, then ours."""
    stored = (get_setting(session, LABEL_MODEL_KEY) or "").strip()
    if stored:
        return stored
    return os.getenv("OPENAI_LABEL_MODEL", "").strip() or DEFAULT_LABEL_MODEL


SUPPORT_USERNAME_KEY = "support_username"
DEFAULT_SUPPORT_USERNAME = "splitt_support"

# Telegram usernames: 5–32 letters, digits and underscores.
_TELEGRAM_USERNAME = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def normalize_telegram_username(raw: str) -> str | None:
    """A username the way Telegram links it — without the @ — or None if it
    could not be one."""
    name = raw.strip().removeprefix("@")
    return name if _TELEGRAM_USERNAME.match(name) else None


def get_support_username(session: Session) -> str:
    """Whom «Contact support» opens a chat with: the operator's pick, or ours."""
    return (get_setting(session, SUPPORT_USERNAME_KEY) or "").strip() or DEFAULT_SUPPORT_USERNAME


# What a Pro plan costs, in Telegram Stars.
PRO_PRICE_KEYS = {"month": "pro_price_month", "half_year": "pro_price_half_year", "year": "pro_price_year"}
DEFAULT_PRO_PRICES = {"month": 100, "half_year": 500, "year": 900}
# Telegram takes 1 to 10 000 Stars for a payment, and a subscription is no exception.
MAX_STARS = 10_000


def _stars(raw: str | None, fallback: int | None) -> int | None:
    try:
        value = int((raw or "").strip())
    except ValueError:
        return fallback
    return value if 1 <= value <= MAX_STARS else fallback


def get_pro_prices(session: Session) -> dict[str, int]:
    """Each plan's price: the operator's, or ours where theirs is unreadable."""
    return {
        plan: _stars(get_setting(session, key), DEFAULT_PRO_PRICES[plan])
        for plan, key in PRO_PRICE_KEYS.items()
    }


# The price a plan is shown struck out, «down from» — only if the operator set one.
PRO_WAS_PRICE_KEYS = {plan: f"pro_was_price_{plan}" for plan in PRO_PRICE_KEYS}


def get_pro_was_prices(session: Session) -> dict[str, int | None]:
    return {plan: _stars(get_setting(session, key), None) for plan, key in PRO_WAS_PRICE_KEYS.items()}


# The one-off discount on paying up front someone is offered the first time they
# see the paywall without having paid: how much off, and for how long. 0% offers none.
PRO_OFFER_PERCENT_KEY = "pro_offer_percent"
PRO_OFFER_HOURS_KEY = "pro_offer_hours"
DEFAULT_PRO_OFFER_PERCENT = 40
DEFAULT_PRO_OFFER_HOURS = 48
MAX_PRO_OFFER_PERCENT = 90
MAX_PRO_OFFER_HOURS = 24 * 14


def _bounded(raw: str | None, low: int, high: int, fallback: int) -> int:
    try:
        value = int((raw or "").strip())
    except ValueError:
        return fallback
    return value if low <= value <= high else fallback


def get_pro_offer_terms(session: Session) -> tuple[int, int]:
    """The offer's percent off and the hours it lasts."""
    return (
        _bounded(get_setting(session, PRO_OFFER_PERCENT_KEY), 0, MAX_PRO_OFFER_PERCENT, DEFAULT_PRO_OFFER_PERCENT),
        _bounded(get_setting(session, PRO_OFFER_HOURS_KEY), 1, MAX_PRO_OFFER_HOURS, DEFAULT_PRO_OFFER_HOURS),
    )


FREE_SCANS_KEY = "free_scans_per_day"
DEFAULT_FREE_SCANS = 3


def get_free_scans_per_day(session: Session) -> int:
    """How many receipts — photos and Soliq QR codes together — someone without
    Pro may read in a day."""
    try:
        return max(0, int((get_setting(session, FREE_SCANS_KEY) or "").strip()))
    except ValueError:
        return DEFAULT_FREE_SCANS
