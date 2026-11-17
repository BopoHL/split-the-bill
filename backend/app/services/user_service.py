import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.dependencies import telegram_id_from_init_data, unsigned_init_data_allowed
from app.utils.auth import init_data_fields
from app.repositories.invite_repo import InviteRepository
from app.repositories.user_repo import UserRepository
from app.models import User
from app.services.product_events import set_person_once
from app.schemas.user_schemas import (
    UserCreate,
    UserSettingsUpdate,
    UserWriteAccessUpdate,
)


def bot_may_write(user: User) -> bool:
    """Whether the bot is known to be able to write to the person: they let it
    in the app, started it, or its last message got through. Someone who only
    ever tapped a post in a group has not — the bot cannot start that chat."""
    return (user.settings or {}).get("bot_blocked") is False


def remember_first_touch(user: User, start: str, source: str | None) -> None:
    """How someone first came in, on their PostHog person from the moment the
    account is made — never from a later visit."""
    set_person_once(user.id, first_start=start, **({"first_source": source} if source else {}))


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.user_repo.get_by_id(user_id)

    def get_or_create_from_bot(
        self,
        telegram_id: int,
        name: str | None,
        username: str | None,
        start: str = "bot",
        source: str | None = None,
    ) -> User:
        """The account behind a chat with the bot. `start` and `source` say how
        someone came in, kept as their first touch when this makes the account.

        No init_data to verify here: the update arrived on the webhook, which is
        already authenticated by the secret token Telegram echoes back, so the
        sender's id is as trustworthy as a signed Mini App payload.
        """
        user = self.user_repo.get_by_telegram_id(telegram_id)
        if user:
            return user
        try:
            created = self.user_repo.create(User(telegram_id=telegram_id, name=name, username=username))
        except IntegrityError:
            # Met at the same moment elsewhere — another of their updates, or the app.
            self.user_repo.session.rollback()
            return self.user_repo.get_by_telegram_id(telegram_id)
        remember_first_touch(created, start, source)
        return created

    def update_settings(self, user_id: int, payload: UserSettingsUpdate) -> User:
        user = self.user_repo.get_by_id_for_update(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # Merge: keep existing keys, overwrite only the ones provided.
        merged = dict(user.settings or {})
        merged.update(payload.model_dump(exclude_none=True))
        user.settings = merged  # reassign so SQLAlchemy detects the change
        return self.user_repo.update(user)

    def update_write_access(self, user_id: int, payload: UserWriteAccessUpdate) -> User:
        user = self.user_repo.get_by_id_for_update(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return self.note_write_access(user, payload.allows_write_to_pm)

    def note_write_access(self, user: User, allowed: bool) -> User:
        """What Telegram just showed about the bot writing to the person: a
        message got through or bounced, they started or blocked the bot."""
        if bot_may_write(user) == allowed and "bot_blocked" in (user.settings or {}):
            return user
        user.settings = self._settings_with_write_access(user.settings, allowed)
        return self.user_repo.update(user)

    def create_or_update_user(self, user_data: UserCreate) -> User:
        name = user_data.name
        surname = user_data.surname
        username = user_data.username
        avatar_url = user_data.avatar_url
        allows_write_to_pm = user_data.allows_write_to_pm

        if user_data.init_data:
            # The signed init data says who is calling; the body only claims it.
            # A valid signature of your own must not update somebody else.
            if telegram_id_from_init_data(user_data.init_data) != user_data.telegram_id:
                raise HTTPException(status_code=403, detail="Caller identity mismatch")
            tg_user = json.loads(init_data_fields(user_data.init_data)["user"])
            name = tg_user.get("first_name")
            surname = tg_user.get("last_name")
            # The handle and the photo too: from the body, anyone could take a
            # friend's @name and be found and seated in their place.
            username = tg_user.get("username")
            avatar_url = tg_user.get("photo_url")
            if "allows_write_to_pm" in tg_user:
                allows_write_to_pm = tg_user.get("allows_write_to_pm") is True
        elif not unsigned_init_data_allowed():
            raise HTTPException(status_code=401, detail="Telegram authentication required")

        existing_user = self.user_repo.get_by_telegram_id(user_data.telegram_id)
        
        if existing_user:
            existing_user.username = username
            existing_user.name = name
            existing_user.surname = surname
            existing_user.avatar_url = avatar_url
            existing_user.settings = self._settings_with_write_access(
                existing_user.settings, allows_write_to_pm
            )
            return self.user_repo.update(existing_user)
        
        new_user = User(
            telegram_id=user_data.telegram_id,
            username=username,
            name=name,
            surname=surname,
            avatar_url=avatar_url,
            # First touch only: this branch runs once per account, so a later
            # invite from somebody else cannot rewrite who brought them in.
            invited_by_user_id=self._inviter_id(user_data.invite_code),
            settings=self._settings_with_write_access({}, allows_write_to_pm),
        )
        created = self.user_repo.create(new_user)
        remember_first_touch(created, user_data.start or "none", user_data.source)
        return created

    def _settings_with_write_access(
        self, settings: dict | None, allows_write_to_pm: bool | None
    ) -> dict:
        merged = dict(settings or {})
        if allows_write_to_pm is None:
            return merged
        merged["bot_blocked"] = not allows_write_to_pm
        return merged

    def _inviter_id(self, invite_code: str | None) -> int | None:
        if not invite_code:
            return None
        invite = InviteRepository(self.user_repo.session).get_by_code(invite_code)
        return invite.inviter_user_id if invite else None
