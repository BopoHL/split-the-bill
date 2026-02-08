import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

def verify_telegram_webapp_data(init_data: str, bot_token: str) -> bool:
    """
    Verify the validity of data received from the Telegram WebApp.
    init_data: The full query string from window.Telegram.WebApp.initData
    bot_token: Your bot's token
    """
    try:
        vals = dict(parse_qsl(init_data))
        if 'hash' not in vals:
            return False
            
        data_hash = vals.pop('hash')
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(vals.items())])
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        check_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        # Check if hash matches
        if check_hash != data_hash:
            return False
            
        # Optional: Check for data expiration (e.g., 24 hours)
        auth_date = int(vals.get('auth_date', 0))
        if time.time() - auth_date > 86400:
            return False
            
        return True
    except Exception:
        return False

def verify_telegram_widget_data(data: dict, bot_token: str) -> bool:
    """
    Verify data received from the official Telegram Login Widget.
    data: Dictionary containing id, first_name, username, photo_url, auth_date, hash
    bot_token: Your bot's token
    """
    try:
        if 'hash' not in data:
            return False
            
        data_hash = data.pop('hash')
        
        # Data check string for widget is different: alphabetical items, joined by \n
        check_list = []
        for key, value in sorted(data.items()):
            if value is not None:
                check_list.append(f"{key}={value}")
        
        data_check_string = "\n".join(check_list)
        
        # Secret key for widget is just SHA256 of bot token
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        check_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        # Restore hash to data for potential further use
        data['hash'] = data_hash
        
        if check_hash != data_hash:
            return False
            
        # Optional: Check for data expiration
        auth_date = int(data.get('auth_date', 0))
        if time.time() - auth_date > 86400:
            return False
            
        return True
    except Exception:
        return False
