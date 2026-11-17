import hashlib
import hmac
import time
from urllib.parse import parse_qsl

def init_data_fields(init_data: str) -> dict[str, str] | None:
    """The fields of Telegram's init data, or None when one comes twice: the
    signature covers only one copy, and the other must not be read as signed."""
    pairs = parse_qsl(init_data)
    fields = dict(pairs)
    return fields if len(fields) == len(pairs) else None


def verify_telegram_webapp_data(init_data: str, bot_token: str) -> bool:
    """
    Verify the validity of data received from the Telegram WebApp.
    init_data: The full query string from window.Telegram.WebApp.initData
    bot_token: Your bot's token
    """
    try:
        vals = init_data_fields(init_data)
        if not vals or 'hash' not in vals:
            return False
            
        data_hash = vals.pop('hash')
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(vals.items())])
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        check_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        # Check if hash matches
        if not hmac.compare_digest(check_hash, data_hash):
            return False
            
        # Optional: Check for data expiration (e.g., 24 hours)
        auth_date = int(vals.get('auth_date', 0))
        age = time.time() - auth_date
        if age < -60 or age > 86400:
            return False
            
        return True
    except Exception:
        return False
