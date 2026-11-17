import json
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse, urlencode

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.bot_worker import update_worker
from app.database import get_session
import app.routers.admin as admin_router
import app.routers.bills as bills_router
import app.services.broadcast_media as broadcast_media
import app.services.product_events as product_events_module
import app.services.receipt_service as receipt_service
from app.models import Bill, ReceiptTask, User
from app.services.telegram_updates import TelegramUpdateQueue
from tests.telegram_world import WORKER

# Shared worlds some test modules build on, as fixtures.
pytest_plugins = ["tests.analytics_world", "tests.pro_world", "tests.bot_chat_world", "tests.voice_world"]

# Use an in-memory SQLite database for tests
DATABASE_URL = "sqlite://"


ANONYMOUS = {"X-Telegram-Init-Data": ""}


def auth_headers(telegram_id: int) -> dict[str, str]:
    return {"X-Telegram-Init-Data": init_data_for(telegram_id)}


def init_data_for(telegram_id: int) -> str:
    """Unsigned init data, accepted because tests opt into ALLOW_UNSIGNED_INIT_DATA.

    Signature verification itself is covered in test_caller_identity.py with a
    real HMAC.
    """
    return urlencode(
        {
            "user": json.dumps({"id": telegram_id, "first_name": "T"}),
            "auth_date": str(int(time.time())),
            "hash": "unsigned-test",
        }
    )


class IdentityTestClient(TestClient):
    """A test client that speaks for a Telegram user, the way the mini app does.

    The real client attaches the caller's signed identity to every request. Tests
    name their actor the same way the API contract does — `user_id`,
    `requester_id`, `owner_id` — so the client turns that into the header.
    `act_as` pins an actor for calls that do not name one.

    That endpoints actually reject a missing or forged identity is proven
    head-on in test_caller_identity.py, rather than smeared across every call.
    """

    ACTOR_FIELDS = ("user_id", "requester_id", "owner_id")

    def __init__(self, *args, session: Session, **kwargs):
        super().__init__(*args, **kwargs)
        self._session = session
        self._pinned: int | None = None

    def act_as(self, telegram_id: int | None) -> None:
        self._pinned = telegram_id

    def request(self, method, url, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        if "X-Telegram-Init-Data" not in headers:
            telegram_id = self._pinned or self._telegram_id_for(url, kwargs)
            if telegram_id is not None:
                headers["X-Telegram-Init-Data"] = init_data_for(telegram_id)
        body = kwargs.get("json")
        if isinstance(body, dict) and "token" not in body:
            token = self._invite_token_for(urlparse(str(url)).path)
            if token:
                kwargs["json"] = {**body, "token": token}
        return super().request(method, url, headers=headers, **kwargs)

    def _invite_token_for(self, path: str) -> str | None:
        """A seat claim carries the invite link's token, the way the real client
        does — it reached the seat picker through that link. That a claim
        without it is refused is asserted in test_caller_identity.py."""
        parts = [p for p in path.split("/") if p]
        is_claim = len(parts) == 5 and parts[0] == "bills" and parts[2] == "seats" and parts[4] == "claim"
        if is_claim and parts[1].isdigit():
            bill = self._session.get(Bill, int(parts[1]))
            return bill.public_token if bill else None
        return None

    def _telegram_id_for(self, url, kwargs) -> int | None:
        for user_id in self._candidate_user_ids(url, kwargs):
            user = self._session.get(User, user_id)
            if user:
                return user.telegram_id
        return None

    def _candidate_user_ids(self, url, kwargs) -> list[int]:
        path = urlparse(str(url)).path
        # There `user_id` is the person the owner seats, not the caller.
        seats_someone = path.rstrip("/").endswith("/participants")
        claimed = None if seats_someone else self._claimed_user_id(url, kwargs)
        owner = self._owner_of_resource(path)
        return [uid for uid in (claimed, owner) if uid is not None]

    def _claimed_user_id(self, url, kwargs) -> int | None:
        sources = [kwargs.get("json"), kwargs.get("data"), kwargs.get("params")]
        path = urlparse(str(url)).path
        sources.append(parse_qs(urlparse(str(url)).query))
        for source in sources:
            if not isinstance(source, dict):
                continue
            for field in self.ACTOR_FIELDS:
                value = source.get(field)
                if isinstance(value, list):
                    value = value[0] if value else None
                if value is not None and str(value).lstrip("-").isdigit():
                    return int(value)
        return None

    def _owner_of_resource(self, path: str) -> int | None:
        """Who a request about someone else's resource is implicitly from.

        Owner-only bill routes carry no actor at all — that is the very gap this
        branch closes — so a test that says "edit this bill's items" means the
        owner. Whether a non-owner is actually turned away is asserted directly
        in test_caller_identity.py.
        """
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            return None
        if parts[0] == "receipts" and parts[1] == "tasks":
            parts = parts[:1] + parts[2:]
        if not parts[1].isdigit():
            return None
        resource, resource_id = parts[0], int(parts[1])
        if resource == "users":
            return resource_id
        if resource == "bills":
            bill = self._session.get(Bill, resource_id)
            return bill.owner_id if bill else None
        if resource == "receipts":
            task = self._session.get(ReceiptTask, resource_id)
            return task.user_id if task else None
        return None


@pytest.fixture(autouse=True)
def _allow_unsigned_init_data(monkeypatch):
    """Tests carry unsigned init data; the signature path has its own test."""
    monkeypatch.setenv("ALLOW_UNSIGNED_INIT_DATA", "true")


@pytest.fixture(autouse=True)
def _fresh_limiters():
    """In-process counters of guesses: ids start over with every test's database."""
    from app.routers import pro as pro_router

    admin_router._LOGIN_ATTEMPTS.clear()
    pro_router._PROMO_MISSES.clear()
    yield


@pytest.fixture(autouse=True)
def _isolated_receipt_storage(monkeypatch, tmp_path):
    """Redirect receipt file storage to a temp dir so tests never leave
    images behind in backend/storage/receipts (STB-68)."""
    storage = tmp_path / "receipts"
    storage.mkdir()
    monkeypatch.setattr(receipt_service, "STORAGE_DIR", str(storage))
    monkeypatch.setattr(admin_router, "BROADCAST_PHOTO_DIR", str(tmp_path / "broadcasts"))
    monkeypatch.setattr(broadcast_media, "MEDIA_DIR", str(tmp_path / "broadcast-media"))
    yield

@pytest.fixture(autouse=True)
def product_events(monkeypatch) -> list[tuple[str, str, dict]]:
    """What the server would send to PostHog, kept here instead of sent:
    events, and person properties as ("$set", distinct_id, properties)."""
    sent = []

    class Recorder:
        def capture(self, event: str, distinct_id: str, properties: dict) -> None:
            sent.append((event, distinct_id, properties))

        def set(self, distinct_id: str, properties: dict) -> None:
            sent.append(("$set", distinct_id, properties))

        def set_once(self, distinct_id: str, properties: dict) -> None:
            sent.append(("$set_once", distinct_id, properties))

    monkeypatch.setattr(product_events_module, "_client", Recorder)
    return sent


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

def handle_kept_updates(session: Session) -> None:
    """What the bot's worker does in the background, done at once: a test sees
    the bot's answer as soon as the webhook has answered."""
    queue = TelegramUpdateQueue(session)
    while claimed := queue.claim(datetime.utcnow(), limit=100, holder=WORKER):
        for update_id in claimed:
            queue.handle(update_id, holder=WORKER)


@pytest.fixture(name="client")
def client_fixture(session: Session, monkeypatch):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    # The bill stream opens a session of its own instead of the request's.
    monkeypatch.setattr(bills_router, "engine", session.get_bind())
    monkeypatch.setattr(update_worker, "wake", lambda: handle_kept_updates(session))
    client = IdentityTestClient(app, base_url="http://testserver/api", session=session)
    yield client
    app.dependency_overrides.clear()
