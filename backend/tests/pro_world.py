"""Two people for the Pro tests, a way to give either of them Pro, and
Telegram's side of refunds and renewals."""
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from app.models import ProGrant, ProSource, User
from app.utils import telegram

NOW = datetime(2026, 10, 4, 9, 0)


@pytest.fixture
def people(session: Session):
    leo = User(telegram_id=11, username="leo", name="Leo", settings={"language": "ru"})
    ann = User(telegram_id=22, username="ann", name="Ann", settings={"language": "en"})
    session.add_all([leo, ann])
    session.commit()
    return leo, ann


def grant(session: Session, user: User, source: ProSource, starts: datetime, days: int) -> ProGrant:
    given = ProGrant(user_id=user.id, source=source.value, starts_at=starts, ends_at=starts + timedelta(days=days))
    session.add(given)
    session.commit()
    return given


@pytest.fixture
def stars(monkeypatch):
    """Telegram's side of refunds and renewals, recorded; `fail` makes the next call refused."""
    calls = {"refunds": [], "renewals": [], "fail": None}

    def answer():
        if calls["fail"]:
            raise RuntimeError(f"Telegram error: {calls['fail']}")

    def refund(telegram_user_id, charge_id):
        answer()
        calls["refunds"].append((telegram_user_id, charge_id))

    def renewal(telegram_user_id, first_charge_id, canceled):
        answer()
        calls["renewals"].append((telegram_user_id, first_charge_id, canceled))

    monkeypatch.setattr(telegram, "refund_star_payment", refund)
    monkeypatch.setattr(telegram, "edit_star_subscription", renewal)
    return calls
