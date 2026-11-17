from sqlmodel import Session, func, or_, select
from app.models import User

class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def search_condition(term: str):
        """Find a person the way an operator types them: @name, name, or telegram id."""
        needle = term.strip().lstrip("@")
        matches = [func.lower(User.username).contains(needle.lower())]
        if needle.isdigit():
            matches.append(User.telegram_id == int(needle))
        return or_(*matches)

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_many(self, user_ids: set[int]) -> dict[int, User]:
        if not user_ids:
            return {}
        return {user.id: user for user in self.session.exec(select(User).where(User.id.in_(user_ids))).all()}

    def get_by_id_for_update(self, user_id: int) -> User | None:
        """The row as it is now, locked. Settings are one JSON value: two
        read-merge-writes racing each other keep only one of the merges."""
        statement = (
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.exec(statement).first()

    def get_by_telegram_id(self, telegram_id: int) -> User | None:
        statement = select(User).where(User.telegram_id == telegram_id)
        return self.session.exec(statement).first()

    def create(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user
