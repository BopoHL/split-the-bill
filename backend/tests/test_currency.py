"""STB-206: BYN (Belarusian ruble) is a valid currency and normalizes correctly."""
from app.utils.currency import VALID_CURRENCIES, normalize_currency


def test_byn_is_valid():
    assert "byn" in VALID_CURRENCIES


def test_normalize_currency_accepts_byn_any_case():
    assert normalize_currency("byn") == "byn"
    assert normalize_currency("BYN") == "byn"


def test_normalize_currency_rejects_unknown():
    assert normalize_currency("xxx") is None
    assert normalize_currency(None) is None


def test_amounts_read_the_way_the_app_writes_them():
    """One rule for all sixteen: no trailing zeros, spaces between thousands,
    the symbol rather than the ticker. Mirrors formatCurrency in the frontend."""
    from app.utils.currency import format_amount

    assert format_amount(100000, "usd") == "1 000 $"
    assert format_amount(1250, "rub") == "12.5 руб"
    assert format_amount(1234, "kzt") == "12.34 ₸"
    assert format_amount(100, "eur") == "1 €"
    assert format_amount(-6719998, "byn") == "-67 199.98 Br"
    # An unknown code still prints something rather than swallowing the amount.
    assert format_amount(500, "xxx") == "5 XXX"


def test_the_sum_is_spelled_out_in_the_reader_s_language():
    """It has no symbol of its own, so the ticker would leave a bare number."""
    from app.utils.currency import format_amount

    assert format_amount(12000000, "uzs", "ru") == "120 000 сум"
    assert format_amount(12000000, "uzs", "uz") == "120 000 so'm"
    assert format_amount(12000000, "uzs", "en") == "120 000 uzs"
    assert format_amount(12000000, "uzs", None) == "120 000 сум"
