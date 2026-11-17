"""The scans screen: the raw material behind a parsed receipt.

The point of it is post-mortems on bad scans, so the OCR text and the model's
answer have to come back verbatim — a summary would hide exactly what went
wrong.
"""
import pytest
from fastapi.testclient import TestClient

from app.models import (
    Bill,
    BillItem,
    FileAsset,
    ReceiptSource,
    ReceiptTask,
    ReceiptTaskStatus,
    ScanMode,
    User,
)
from app.utils.currency import to_tiins


@pytest.fixture(autouse=True)
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    from app.routers import admin

    admin._LOGIN_ATTEMPTS.clear()


def _login(client: TestClient) -> None:
    assert client.post(
        "/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}
    ).status_code == 200


def _scan(session, **kwargs) -> ReceiptTask:
    user = User(telegram_id=kwargs.pop("telegram_id", 500), username="scanner")
    session.add(user)
    session.flush()
    bill = Bill(owner_id=user.id, title="Ужин", total_sum=to_tiins(120))
    session.add(bill)
    session.flush()
    task = ReceiptTask(
        user_id=user.id,
        bill_id=bill.id,
        status=kwargs.pop("status", ReceiptTaskStatus.COMPLETED),
        source=kwargs.pop("source", ReceiptSource.PHOTO),
        **kwargs,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def test_the_scan_list_is_closed_without_a_session(client: TestClient):
    assert client.get("/admin/scans").status_code == 401


def test_a_scan_shows_its_raw_ocr_and_the_model_answer(client: TestClient, session):
    task = _scan(
        session,
        ocr_text="COLA 100\nTOTAL 100",
        llm_response='{"items": [{"name": "Cola"}]}',
        llm_model="gpt-6-luna",
        scan_quality=2,
    )
    session.add(
        BillItem(
            bill_id=task.bill_id, name="Cola", price=to_tiins(100),
            count=1, item_sum=to_tiins(100), receipt_task_id=task.id,
        )
    )
    session.commit()
    _login(client)

    detail = client.get(f"/admin/scans/{task.id}").json()
    assert detail["ocr_text"] == "COLA 100\nTOTAL 100"
    assert detail["llm_response"] == '{"items": [{"name": "Cola"}]}'
    assert detail["llm_model"] == "gpt-6-luna"
    assert detail["scan_quality"] == 2
    assert detail["bill_title"] == "Ужин"
    assert [item["name"] for item in detail["items"]] == ["Cola"]
    assert detail["items_count"] == 1


def test_the_list_narrows_to_what_is_worth_reading(client: TestClient, session):
    _scan(session, telegram_id=501, scan_quality=5)
    poor = _scan(session, telegram_id=502, scan_quality=2)
    failed = _scan(session, telegram_id=503, status=ReceiptTaskStatus.FAILED,
                   error_message="no text found")
    qr = _scan(session, telegram_id=504, source=ReceiptSource.SOLIQ_QR)
    _login(client)

    assert [row["id"] for row in client.get("/admin/scans?quality=low").json()] == [poor.id]
    assert [row["id"] for row in client.get("/admin/scans?status=failed").json()] == [failed.id]
    assert [row["id"] for row in client.get("/admin/scans?source=soliq_qr").json()] == [qr.id]
    # Newest first: a bad scan is looked into right after it happens.
    assert [row["id"] for row in client.get("/admin/scans").json()][0] == qr.id


def test_an_unrated_scan_is_told_apart_from_a_rated_one(client: TestClient, session):
    rated = _scan(session, telegram_id=505, scan_quality=4)
    unrated = _scan(session, telegram_id=506)
    _login(client)

    assert [r["id"] for r in client.get("/admin/scans?quality=rated").json()] == [rated.id]
    assert [r["id"] for r in client.get("/admin/scans?quality=unrated").json()] == [unrated.id]


def test_the_receipt_photo_needs_an_admin_session(client: TestClient, session, tmp_path):
    task = _scan(session, telegram_id=507)
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"\xff\xd8\xff\xdb-not-really-a-jpeg")
    session.add(
        FileAsset(
            user_id=task.user_id, bill_id=task.bill_id, receipt_task_id=task.id,
            path=str(image), size=image.stat().st_size, mime_type="image/jpeg",
        )
    )
    session.commit()

    assert client.get(f"/admin/scans/{task.id}/photo").status_code == 401
    _login(client)
    resp = client.get(f"/admin/scans/{task.id}/photo")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert client.get(f"/admin/scans/{task.id}").json()["has_photo"] is True


def test_a_scan_without_a_photo_says_so_rather_than_erroring(client: TestClient, session):
    task = _scan(session, telegram_id=508)
    _login(client)
    assert client.get(f"/admin/scans/{task.id}/photo").status_code == 404
    assert client.get(f"/admin/scans/{task.id}").json()["has_photo"] is False


def test_the_reader_scoreboard_needs_an_admin_session(client: TestClient):
    assert client.get("/admin/scans/modes").status_code == 401


def test_the_reader_scoreboard_counts_photo_scans_by_mode(client: TestClient, session):
    """Comparing the readers is the reason they are switchable, so the table
    that compares them has to answer at all — it was raising on every request."""
    _scan(session, telegram_id=509, scan_mode=ScanMode.VISION.value, scan_quality=4)
    _scan(
        session, telegram_id=510, scan_mode=ScanMode.VISION.value,
        status=ReceiptTaskStatus.FAILED, error_message="no text found",
    )
    # No mode on the row: it ran before the readers were switchable, so it used
    # the only one there was.
    _scan(session, telegram_id=511)
    # A QR import has no reader to judge and stays out of the table.
    _scan(
        session, telegram_id=512, source=ReceiptSource.SOLIQ_QR,
        scan_mode=ScanMode.VISION.value,
    )
    _login(client)

    rows = {row["mode"]: row for row in client.get("/admin/scans/modes").json()}
    assert rows[ScanMode.VISION.value]["scans"] == 2
    assert rows[ScanMode.VISION.value]["failed"] == 1
    assert rows[ScanMode.VISION.value]["rated"] == 1
    assert rows[ScanMode.VISION.value]["avg_quality"] == 4
    assert rows[ScanMode.OCR_LLM.value]["scans"] == 1
    assert ScanMode.HYBRID.value not in rows
