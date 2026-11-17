"""Import receipt items from an Uzbek fiscal (Soliq/OFD) check.

Every fiscal receipt in Uzbekistan carries a QR code linking to the public check
page on ``ofd.soliq.uz``:

    https://ofd.soliq.uz/check?t=<terminal>&r=<receipt>&c=<datetime>&s=<sign>

That page used to be plain server-rendered HTML we scraped. Soliq has since
replaced it with a client-side SPA that loads the receipt from a JSON endpoint,
so we now call that endpoint directly — the very request the SPA makes:

    POST https://new-ofd.soliq.uz/api/payment
    body:    {terminalId, paymentNo, paymentDate, fiscalSign, paymentType}
    headers: X-Timestamp + X-Signature = HMAC-SHA256(
                 "{terminalId}:{paymentNo}:{timestamp}", SOLIQ_API_SECRET)

The signing key is public in Soliq's own browser bundle. ``SOLIQ_API_SECRET``
can override it if Soliq rotates the key, but the importer must also work in a
fresh environment without an extra private setting.

The response is structured JSON, mapped to the SAME dict shape the photo->GPT
path produces so the worker enriches a bill from either source with one code
path:

    {"title": str|None,
     "total_sum": float,
     "items": [{"name": str, "count": int, "amount": float, "is_shared_globally": bool}]}

``amount`` is the LINE total (the price for the whole quantity), matching the
check's «Narxi» column and the GPT contract.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx

# The QR link the client scanned. We only ever derive request params from an
# ofd.soliq.uz check link — this allow-list is the SSRF gate.
SOLIQ_QR_HOST = "ofd.soliq.uz"
_ALLOWED_PATHS = ("/check", "/epi")
_REQUIRED_PARAMS = ("t", "r", "c")
_SIGN_PARAMS = ("s", "h")

# The SPA reads receipts from this JSON API, signing each request with an
# HMAC-SHA256 over "{terminalId}:{paymentNo}:{timestamp}". The signing key is a
# constant baked into Soliq's frontend bundle; we keep it in an env var so it can
# be rotated without a code change if Soliq changes it.
SOLIQ_API_URL = os.getenv("SOLIQ_API_URL", "https://new-ofd.soliq.uz/api/payment")
DEFAULT_SOLIQ_API_SECRET = "thisIsPaymentSecretKey123@#"
_PAYMENT_TYPE = "CHECK"


class SoliqError(Exception):
    """Soliq QR couldn't be turned into a receipt (bad URL, fetch or parse)."""


class SoliqReceiptNotReady(SoliqError):
    """The receipt isn't in the OFD yet — the user can retry in a moment."""


def _api_secret() -> str:
    return os.getenv("SOLIQ_API_SECRET") or DEFAULT_SOLIQ_API_SECRET


def validate_soliq_url(raw: str) -> str:
    """Validate a scanned QR string is a Soliq check link and normalise it.

    Returns the canonical https URL, or raises SoliqError. This is the SSRF gate
    — only ofd.soliq.uz check/epi links with the four receipt params pass, never
    an arbitrary host/port/credentials.
    """
    if not raw or not isinstance(raw, str):
        raise SoliqError("Empty QR")
    parsed = urlparse(raw.strip())

    if parsed.scheme not in ("http", "https"):
        raise SoliqError("Unsupported URL scheme")
    if "@" in (parsed.netloc or ""):  # no embedded credentials
        raise SoliqError("Invalid URL")
    if (parsed.hostname or "").lower() != SOLIQ_QR_HOST:
        raise SoliqError("Not a Soliq receipt URL")
    if parsed.port not in (None, 80, 443):
        raise SoliqError("Invalid URL")
    path = parsed.path or "/"
    if not any(path == p or path.startswith(p + "/") for p in _ALLOWED_PATHS):
        raise SoliqError("Not a Soliq check URL")
    query = parse_qs(parsed.query)
    if not all(key in query for key in _REQUIRED_PARAMS):
        raise SoliqError("Soliq URL is missing receipt parameters")
    if not any(key in query for key in _SIGN_PARAMS):
        raise SoliqError("Soliq URL is missing receipt signature")

    return urlunparse(("https", SOLIQ_QR_HOST, parsed.path, "", parsed.query, ""))


def _receipt_params(url: str) -> dict:
    """Pull the four receipt identifiers out of a validated check URL into the
    JSON body the API expects."""
    query = parse_qs(urlparse(url).query)
    body = {
        "terminalId": query["t"][0],
        "paymentNo": query["r"][0],
        "paymentDate": query["c"][0],
        "paymentType": _PAYMENT_TYPE,
    }
    if query.get("s"):
        body["fiscalSign"] = query["s"][0]
    if query.get("h"):
        body["fiscalSignHash"] = query["h"][0]
    return body


def _sign(terminal_id: str, payment_no: str, timestamp: int) -> str:
    message = f"{terminal_id}:{payment_no}:{timestamp}"
    return hmac.new(_api_secret().encode(), message.encode(), hashlib.sha256).hexdigest()


async def fetch_soliq_payment(url: str, timeout: float = 12.0) -> dict:
    """POST the (already validated) receipt params to the Soliq JSON API and
    return its ``data`` object.

    Raises SoliqReceiptNotReady when the receipt isn't in the OFD yet, or
    SoliqError on any other fetch/protocol failure.
    """
    params = _receipt_params(url)
    timestamp = int(time.time())
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Timestamp": str(timestamp),
        "X-Signature": _sign(params["terminalId"], params["paymentNo"], timestamp),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(SOLIQ_API_URL, json=params, headers=headers)
    except httpx.HTTPError as exc:
        raise SoliqError(f"Soliq API request failed: {exc}") from exc

    if resp.status_code == 404:
        raise SoliqReceiptNotReady("Receipt is not available in the OFD yet")
    if resp.status_code >= 400:
        raise SoliqError(f"Soliq API returned HTTP {resp.status_code}")

    try:
        data = resp.json().get("data")
    except ValueError as exc:
        raise SoliqError("Soliq API returned a non-JSON response") from exc
    if not data:
        raise SoliqReceiptNotReady("Receipt is not available in the OFD yet")
    return data


# --- response parsing ----------------------------------------------------

def _clean_title(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.strip().replace('"', "").replace("“", "").replace("”", "").strip()
    return cleaned[:80] or None


def parse_soliq_payment(data: dict) -> dict:
    """Map the Soliq API ``data`` object to the worker's receipt dict.

    Each detail's ``price`` is the LINE total for the whole quantity (verified
    against the printed grand total), so it maps straight to ``amount`` — it is
    NOT multiplied by ``amount`` (which is the quantity).
    """
    items: list[dict] = []
    for detail in data.get("paymentDetails") or []:
        name = (detail.get("name") or "").strip()
        line_total = detail.get("price")
        if not name or not isinstance(line_total, (int, float)):
            continue
        try:
            count = int(detail.get("amount") or 1)
        except (TypeError, ValueError):
            count = 1
        if count < 1:
            count = 1
        items.append(
            {
                "name": name,
                "count": count,
                "amount": float(line_total),
                "is_shared_globally": False,
            }
        )

    total = (data.get("cardTotal") or 0) + (data.get("cashTotal") or 0)
    if not total:
        total = round(sum(item["amount"] for item in items), 2)

    title = _clean_title((data.get("extraInfo") or {}).get("companyName"))
    return {"title": title, "total_sum": float(total), "items": items}
