from decimal import Decimal, ROUND_HALF_UP

# Currencies a bill can be denominated in. The flag lives in the frontend
# catalog (currencyCatalog.ts) and in bot_copy; the symbols below mirror the
# ones that catalog shows. Keep the set in sync with it.
VALID_CURRENCIES = {
    "usd", "eur", "rub", "byn", "uzs", "kzt", "kgs", "tjs", "tmt",
    "gbp", "try", "aed", "uah", "gel", "azn", "cny",
}
DEFAULT_CURRENCY = "uzs"

# Currencies whose minor unit nobody pays in: a share of a bill in sums is
# rounded to whole sums, so nobody is asked for tiyins there are no coins for.
WHOLE_UNIT_CURRENCIES = {"uzs"}


def share_step(currency: str | None) -> int:
    """The smallest amount a share is rounded to, in tiins."""
    return 100 if (currency or DEFAULT_CURRENCY).lower() in WHOLE_UNIT_CURRENCIES else 1


def normalize_currency(value) -> str | None:
    """Return a valid lowercase currency code, or None if the value isn't one."""
    if isinstance(value, str) and value.lower() in VALID_CURRENCIES:
        return value.lower()
    return None

def to_tiins(amount: float) -> int:
    """Convert human-readable currency units to tiins (integer) safely using Decimal"""
    # Convert to string first to avoid float precision artifacts
    d = Decimal(str(amount))
    return int((d * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def from_tiins(tiins: int) -> float:
    """Convert tiins (integer) to human-readable currency units (float)"""
    # We return float for the API, but do the division via Decimal for precision
    return float(Decimal(tiins) / Decimal('100'))


# What the app writes next to an amount. Mirrors currencySymbolFor() in the
# frontend catalog, including the empty entry for sums — that one is spelled out
# per language instead, so the number does not end up bare.
CURRENCY_SYMBOLS = {
    "usd": "$", "eur": "€", "rub": "руб", "byn": "Br", "uzs": "",
    "kzt": "₸", "kgs": "сом", "tjs": "смн", "tmt": "TMT", "gbp": "£",
    "try": "₺", "aed": "AED", "uah": "₴", "gel": "₾", "azn": "₼", "cny": "¥",
}
UZS_BY_LANGUAGE = {"ru": "сум", "uz": "so'm", "en": "uzs"}


def currency_symbol(currency: str, language: str | None = None) -> str:
    code = (currency or "").lower()
    if code == "uzs":
        return UZS_BY_LANGUAGE.get((language or "ru").split("-")[0].lower(), UZS_BY_LANGUAGE["ru"])
    return CURRENCY_SYMBOLS.get(code) or code.upper()


def format_amount(tiins: int, currency: str, language: str | None = None) -> str:
    """An amount the way the Mini App writes it.

    Formatted from the stored integer rather than a float, so no rounding
    happens here at all — the two halves of the product used to disagree on
    12.345 because one rounded half-up and the other to even. Trailing zeros go,
    including a bare «.00»: a bill in sums is always whole and reading «120
    000.00» is worse than reading «120 000».
    """
    symbol = currency_symbol(currency, language)
    return f"{format_number(tiins)} {symbol}".rstrip()


def format_number(tiins: int, grouped: bool = True) -> str:
    """An amount's figure without its currency: grouped by thousands for
    reading, or bare — the form a banking app takes when it is pasted in."""
    sign = "-" if tiins < 0 else ""
    whole, minor = divmod(abs(int(tiins)), 100)
    digits = f"{whole:,}".replace(",", " " if grouped else "")
    if minor:
        digits = f"{digits}.{minor:02d}".rstrip("0")
    return f"{sign}{digits}"
