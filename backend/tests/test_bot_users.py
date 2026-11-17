"""The person behind a bot update, created once even when met twice at once."""
from sqlmodel import Session, select

from app.models import User
from app.repositories.user_repo import UserRepository
from app.services.user_service import UserService


def test_someone_met_at_the_same_moment_elsewhere_is_not_created_twice(session: Session, monkeypatch, product_events):
    users = UserService(UserRepository(session))
    elsewhere = User(telegram_id=42, name="Lea")
    find = UserRepository.get_by_telegram_id
    looks = []

    def not_there_yet(repo, telegram_id):
        looks.append(telegram_id)
        if len(looks) == 1:
            # The first look misses; another update creates them right after.
            session.add(elsewhere)
            session.commit()
            return None
        return find(repo, telegram_id)

    monkeypatch.setattr(UserRepository, "get_by_telegram_id", not_there_yet)

    user = users.get_or_create_from_bot(42, "Lea", None)

    assert user.id == elsewhere.id
    assert len(session.exec(select(User).where(User.telegram_id == 42)).all()) == 1
    # Whoever made the account kept how they came in.
    assert product_events == []
