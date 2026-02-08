import os
from fastapi import HTTPException
from app.repositories.user_repo import UserRepository
from app.models import User
from app.schemas.user_schemas import UserCreate
from app.utils.auth import verify_telegram_webapp_data, verify_telegram_widget_data

class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
        self.bot_token = os.getenv("TG_TOKEN")

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.user_repo.get_by_id(user_id)

    def create_or_update_user(self, user_data: UserCreate) -> User:
        # Validate Telegram authentication
        is_valid = False
        
        if user_data.init_data:
            # Validate WebApp data
            is_valid = verify_telegram_webapp_data(user_data.init_data, self.bot_token)
        elif user_data.widget_data:
            # Validate Login Widget data
            is_valid = verify_telegram_widget_data(user_data.widget_data, self.bot_token)
            # Ensure the ID in widget data matches the requested telegram_id
            if is_valid and user_data.widget_data.get('id') != user_data.telegram_id:
                is_valid = False
        
        # In development/local mode, we might want a fallback, 
        # but for security we should be strict if data is provided.
        # If no auth data is provided at all, we reject in production.
        if not is_valid:
            # Extra check: allow bypass ONLY if explicitly in dev mode and no auth data provided
            # For now, let's be strict.
            raise HTTPException(status_code=401, detail="Invalid Telegram authentication")

        existing_user = self.user_repo.get_by_telegram_id(user_data.telegram_id)
        
        if existing_user:
            existing_user.username = user_data.username
            existing_user.avatar_url = user_data.avatar_url
            return self.user_repo.update(existing_user)
        
        new_user = User(
            telegram_id=user_data.telegram_id,
            username=user_data.username,
            avatar_url=user_data.avatar_url
        )
        return self.user_repo.create(new_user)
