"""The free day's scans: photos and Soliq QR codes together, from midnight in
Tashkent, failed ones not counted, none of it for Pro."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import ProSource, ReceiptTask, User
from app.services.app_settings import set_setting
from app.services.scan_allowance import ScanAllowance, ScanLimitReached
from tests.pro_world import NOW, grant


def _scan(session: Session, user: User, at: datetime, source="photo", status="completed") -> None:
    session.add(ReceiptTask(user_id=user.id, source=source, status=status, created_at=at))
    session.commit()


def test_free_scans_count_from_midnight_in_tashkent_and_skip_failed_ones(session: Session, people):
    leo, _ = people
    allowance = ScanAllowance(session)
    # 09:00 UTC is 14:00 in Tashkent; its midnight was 19:00 UTC the day before.
    _scan(session, leo, datetime(2026, 10, 3, 18, 30))
    _scan(session, leo, datetime(2026, 10, 3, 19, 30))
    _scan(session, leo, NOW - timedelta(hours=1), source="soliq_qr")
    _scan(session, leo, NOW - timedelta(minutes=5), status="failed")

    assert allowance.left_today(leo.id, NOW) == 1
    _scan(session, leo, NOW)
    with pytest.raises(ScanLimitReached):
        allowance.ensure(leo.id, NOW)

    grant(session, leo, ProSource.PROMO, NOW - timedelta(days=1), 30)
    assert allowance.left_today(leo.id, NOW) is None


def test_a_scan_past_the_free_ones_opens_the_paywall(client: TestClient, session: Session, people):
    leo, _ = people
    set_setting(session, "free_scans_per_day", "0")

    answer = client.post(
        "/receipts/upload", data={"user_id": leo.id}, files={"file": ("r.jpg", b"jpeg", "image/jpeg")},
    )

    assert answer.status_code == 402
    assert answer.json()["detail"] == {"code": "SCAN_LIMIT", "limit": 0}


def test_uploads_sent_at_once_cannot_all_take_the_last_free_scan(client: TestClient, session: Session, people, monkeypatch):
    """The check counts tasks, and a task is written only after its photo is
    read and squeezed. Ten uploads at once all read «one left» without a lock."""
    import asyncio
    import time as clock

    import httpx

    from app.main import app
    from app.queue_manager import queue_manager
    from app.services.receipt_service import ReceiptService
    from tests.conftest import auth_headers

    leo, _ = people
    set_setting(session, "free_scans_per_day", "1")
    squeeze = ReceiptService._compress
    monkeypatch.setattr(ReceiptService, "_compress", staticmethod(lambda raw: (clock.sleep(0.2), squeeze(raw))[1]))
    monkeypatch.setattr(queue_manager, "put", lambda task_id: asyncio.sleep(0))

    async def upload_twice():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver/api") as http:
            send = lambda: http.post(  # noqa: E731
                "/receipts/upload",
                data={"user_id": str(leo.id)},
                files={"file": ("r.jpg", b"jpeg", "image/jpeg")},
                headers=auth_headers(leo.telegram_id),
            )
            return await asyncio.gather(send(), send())

    answers = asyncio.run(upload_twice())

    assert sorted(answer.status_code for answer in answers) == [200, 402]
