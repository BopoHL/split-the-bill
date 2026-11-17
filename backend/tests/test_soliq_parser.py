"""Tests for the Soliq (ofd.soliq.uz) QR receipt importer: URL allow-listing,
request signing, and mapping the JSON API response into the worker's receipt
dict."""
import asyncio
import hashlib
import hmac
import json
import os

import pytest

import app.services.soliq as soliq
from app.services.soliq import (
    DEFAULT_SOLIQ_API_SECRET,
    SoliqError,
    SoliqReceiptNotReady,
    parse_soliq_payment,
    validate_soliq_url,
    _receipt_params,
    _sign,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "soliq_payment_sample.json")


@pytest.fixture
def sample_data() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


# --- URL validation / SSRF gate ------------------------------------------

VALID_URL = "https://ofd.soliq.uz/check?t=LG420211643372&r=11975&c=20260619124101&s=133935061946"


def test_validate_accepts_check_url():
    assert validate_soliq_url(VALID_URL) == VALID_URL


def test_validate_accepts_hash_signature_url():
    raw = "https://ofd.soliq.uz/check?t=EZ1&r=1&c=20240101000000&h=ABCDEF"
    assert validate_soliq_url(raw) == raw


def test_validate_accepts_epi_url_and_forces_https():
    raw = "http://ofd.soliq.uz/epi?t=EZ1&r=1&c=20240101000000&s=123"
    assert validate_soliq_url(raw).startswith("https://ofd.soliq.uz/epi?")


def test_validate_trims_whitespace():
    assert validate_soliq_url("  " + VALID_URL + "  ") == VALID_URL


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not a url",
        "https://evil.com/check?t=1&r=1&c=1&s=1",  # wrong host
        "https://ofd.soliq.uz.evil.com/check?t=1&r=1&c=1&s=1",  # look-alike host
        "https://ofd.soliq.uz/check?t=1&r=1",  # missing params (c, signature)
        "https://ofd.soliq.uz/check?t=1&r=1&c=1",  # missing signature (s or h)
        "https://user:pass@ofd.soliq.uz/check?t=1&r=1&c=1&s=1",  # credentials
        "ftp://ofd.soliq.uz/check?t=1&r=1&c=1&s=1",  # bad scheme
        "https://ofd.soliq.uz/other?t=1&r=1&c=1&s=1",  # wrong path
    ],
)
def test_validate_rejects_bad_urls(bad):
    with pytest.raises(SoliqError):
        validate_soliq_url(bad)


# --- request building / signing ------------------------------------------

def test_receipt_params_maps_qr_to_body():
    assert _receipt_params(VALID_URL) == {
        "terminalId": "LG420211643372",
        "paymentNo": "11975",
        "paymentDate": "20260619124101",
        "fiscalSign": "133935061946",
        "paymentType": "CHECK",
    }


def test_receipt_params_maps_hash_signature_to_body():
    url = "https://ofd.soliq.uz/check?t=EZ1&r=1&c=20240101000000&h=ABCDEF"
    assert _receipt_params(url) == {
        "terminalId": "EZ1",
        "paymentNo": "1",
        "paymentDate": "20240101000000",
        "fiscalSignHash": "ABCDEF",
        "paymentType": "CHECK",
    }


def test_sign_is_hmac_sha256_over_terminal_payment_timestamp(monkeypatch):
    monkeypatch.setenv("SOLIQ_API_SECRET", "test-secret")
    expected = hmac.new(b"test-secret", b"TERM:42:1700000000", hashlib.sha256).hexdigest()
    assert _sign("TERM", "42", 1700000000) == expected


def test_sign_uses_public_bundle_secret_by_default(monkeypatch):
    monkeypatch.delenv("SOLIQ_API_SECRET", raising=False)
    expected = hmac.new(
        DEFAULT_SOLIQ_API_SECRET.encode(), b"TERM:42:1700000000", hashlib.sha256
    ).hexdigest()
    assert _sign("TERM", "42", 1700000000) == expected


# --- network fetch: status mapping ---------------------------------------

_NO_JSON = object()


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is _NO_JSON:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        return self._resp


def _patch_client(monkeypatch, resp):
    monkeypatch.setenv("SOLIQ_API_SECRET", "test-secret")
    monkeypatch.setattr(soliq.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp))


def test_fetch_returns_data_object(monkeypatch, sample_data):
    _patch_client(monkeypatch, _FakeResp(200, {"data": sample_data}))
    out = asyncio.run(soliq.fetch_soliq_payment(VALID_URL))
    assert out["cardTotal"] == 52500


def test_fetch_404_is_not_ready(monkeypatch):
    _patch_client(monkeypatch, _FakeResp(404, {}))
    with pytest.raises(SoliqReceiptNotReady):
        asyncio.run(soliq.fetch_soliq_payment(VALID_URL))


def test_fetch_empty_data_is_not_ready(monkeypatch):
    _patch_client(monkeypatch, _FakeResp(200, {"data": None}))
    with pytest.raises(SoliqReceiptNotReady):
        asyncio.run(soliq.fetch_soliq_payment(VALID_URL))


def test_fetch_server_error_is_soliq_error(monkeypatch):
    _patch_client(monkeypatch, _FakeResp(500, {}))
    with pytest.raises(SoliqError):
        asyncio.run(soliq.fetch_soliq_payment(VALID_URL))


# --- response parsing ----------------------------------------------------

def test_parse_extracts_item_names(sample_data):
    data = parse_soliq_payment(sample_data)
    assert [i["name"] for i in data["items"]] == [
        "ГП Пицца закрытая ОБЛ",
        "3Пакет маленький логотип",
    ]


def test_parse_keeps_line_total_without_multiplying_by_quantity(sample_data):
    data = parse_soliq_payment(sample_data)
    pizza = data["items"][0]
    assert pizza["count"] == 4
    # `price` is the LINE total for all 4, copied verbatim — NOT price * count.
    assert pizza["amount"] == 52000.0
    assert all(i["is_shared_globally"] is False for i in data["items"])


def test_parse_total_is_grand_total(sample_data):
    data = parse_soliq_payment(sample_data)
    assert data["total_sum"] == 52500.0
    assert sum(i["amount"] for i in data["items"]) == data["total_sum"]


def test_parse_extracts_merchant_title(sample_data):
    data = parse_soliq_payment(sample_data)
    assert data["title"] and "JUGER REGION" in data["title"]


def test_parse_removes_wrapping_quotes_from_merchant_title():
    data = parse_soliq_payment({"extraInfo": {"companyName": '"MEGACAPITAL" MCHJ'}})
    assert data["title"] == "MEGACAPITAL MCHJ"


def test_parse_skips_rows_without_name_or_price():
    data = parse_soliq_payment(
        {
            "cardTotal": 100,
            "paymentDetails": [
                {"name": "Good", "price": 100, "amount": 1},
                {"name": "", "price": 50, "amount": 1},
                {"name": "No price", "price": None, "amount": 1},
            ],
        }
    )
    assert [i["name"] for i in data["items"]] == ["Good"]
