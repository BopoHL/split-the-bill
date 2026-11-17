"""Symmetric encryption for sensitive, user-stored values (payment details).

Uses AES-GCM (authenticated encryption). The key comes from the
``PAYMENT_ENC_KEY`` environment variable (base64-encoded 16/24/32 bytes) on the
app VM. Local development (ALLOW_UNSIGNED_INIT_DATA on) falls back to a fixed
key so the feature works without configuration. Anywhere else a missing key is
an error: the fallback is in the source and the image, so card numbers and
sender logins sealed with it would be readable by anyone holding either.
"""

import os
import base64

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.dependencies import unsigned_init_data_allowed

# Exactly 32 bytes — used only when PAYMENT_ENC_KEY is not configured.
_DEV_KEY = b"split-the-bill-dev-key-32bytes!!"

_NONCE_LEN = 12


def _get_key() -> bytes:
    raw = os.getenv("PAYMENT_ENC_KEY")
    if raw:
        key = base64.b64decode(raw)
        if len(key) not in (16, 24, 32):
            raise ValueError("PAYMENT_ENC_KEY must decode to 16, 24 or 32 bytes")
        return key
    if unsigned_init_data_allowed():
        return _DEV_KEY
    raise RuntimeError("PAYMENT_ENC_KEY is not set")


def require_key() -> None:
    """Fail at boot rather than at the first card someone saves."""
    _get_key()


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returning base64(nonce || ciphertext)."""
    aesgcm = AESGCM(_get_key())
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str) -> str:
    """Reverse :func:`encrypt`."""
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    aesgcm = AESGCM(_get_key())
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
