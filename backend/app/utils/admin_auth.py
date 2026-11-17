"""Authentication for the admin panel.

A separate contour from the mini app on purpose: Telegram initData proves who a
user is inside Telegram, which says nothing about whether they may read every
bill in the database. This is a single operator account held in env vars — there
is no admin user table because there is no second admin.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, HTTPException, Request

TOKEN_TTL_SECONDS = 12 * 60 * 60
COOKIE_NAME = "stb_admin"


def _secret() -> str:
    secret = os.getenv("ADMIN_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Admin panel is not configured")
    return secret


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def issue_token(subject: str, now: int | None = None) -> str:
    """A minimal signed token — no JWT library for one claim set."""
    now = now or int(time.time())
    payload = {"sub": subject, "exp": now + TOKEN_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def verify_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    expected = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_unb64(signature), expected):
        raise HTTPException(status_code=401, detail="Invalid token")

    payload = json.loads(_unb64(body))
    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def check_credentials(email: str, password: str) -> bool:
    """Compare against the configured operator account in constant time."""
    expected_email = os.getenv("ADMIN_EMAIL")
    expected_password = os.getenv("ADMIN_PASSWORD")
    if not expected_email or not expected_password:
        raise HTTPException(status_code=503, detail="Admin panel is not configured")

    email_ok = secrets.compare_digest(email.strip().lower(), expected_email.strip().lower())
    password_ok = secrets.compare_digest(password, expected_password)
    # Both are evaluated regardless, so a wrong email and a wrong password take
    # the same time.
    return email_ok and password_ok


def require_admin(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[len("Bearer "):]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return verify_token(token)


AdminSession = Depends(require_admin)
