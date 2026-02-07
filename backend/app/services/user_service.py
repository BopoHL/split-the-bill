from app.repositories.user_repo import UserRepository
from app.models import User
from app.schemas.user_schemas import UserCreate

class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.user_repo.get_by_id(user_id)

    def create_or_update_user(self, user_data: UserCreate) -> User:
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
