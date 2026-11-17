import io
import os

import pytest

from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import select

from app.models import FileAsset, Bill, BillStatus, ReceiptTask
from app.repositories.file_repo import FileAssetRepository
from app.repositories.receipt_repo import ReceiptRepository
from app.services.receipt_service import ReceiptService
import app.services.receipt_service as receipt_service_mod


def test_upload_stores_compressed_file_asset(client: TestClient, session):
    user = client.post("/users/", json={"telegram_id": 1, "username": "u"}).json()

    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 30, 30)).save(buf, format="PNG")
    buf.seek(0)

    resp = client.post(
        "/receipts/upload",
        data={"user_id": user["id"], "currency": "usd"},
        files={"file": ("receipt.png", buf, "image/png")},
    )
    assert resp.status_code == 200
    # The bill is created up front and returned on the task.
    assert resp.json()["bill_id"] is not None

    assets = session.exec(select(FileAsset)).all()
    assert len(assets) == 1
    asset = assets[0]
    assert asset.user_id == user["id"]
    assert asset.mime_type == "image/jpeg"  # re-encoded for storage
    assert asset.size > 0
    # Linked to the provisional bill straight away (no longer deferred).
    assert asset.bill_id is not None
    assert session.get(Bill, asset.bill_id) is not None
    assert asset.storage_type == "local"
    assert session.get(Bill, asset.bill_id).currency == "usd"


def test_upload_rejects_non_image(client: TestClient):
    uploader = client.post(
        "/users/", json={"telegram_id": 77, "username": "up"}
    ).json()["id"]
    resp = client.post(
        "/receipts/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"user_id": uploader},
    )
    assert resp.status_code == 400


def test_save_receipt_rolls_back_task_asset_and_file(session, monkeypatch):
    upload = type("Upload", (), {})()
    upload.filename = "receipt.png"
    upload.read = lambda: None

    async def read():
        buf = io.BytesIO()
        Image.new("RGB", (10, 10), (1, 2, 3)).save(buf, format="PNG")
        return buf.getvalue()

    upload.read = read
    service = ReceiptService(ReceiptRepository(session), FileAssetRepository(session))
    monkeypatch.setattr(session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

    with pytest.raises(RuntimeError, match="db down"):
        import asyncio
        asyncio.run(service.save_receipt(upload, user_id=None, bill_id=None))

    assert session.exec(select(ReceiptTask)).all() == []
    assert session.exec(select(FileAsset)).all() == []
    assert os.listdir(receipt_service_mod.STORAGE_DIR) == []


def test_upload_failure_removes_provisional_bill(client: TestClient, session, monkeypatch):
    owner = client.post("/users/", json={"telegram_id": 4, "username": "u"}).json()

    async def fail_save(*args, **kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(ReceiptService, "save_receipt", fail_save)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        client.post(
            "/receipts/upload",
            data={"user_id": owner["id"]},
            files={"file": ("receipt.png", io.BytesIO(b"image"), "image/png")},
        )

    assert session.exec(select(Bill)).all() == []


def test_bill_receipt_repository_lists_every_photo_oldest_first(session):
    """A bill can hold several receipts, so the repo returns all of them."""
    session.add(FileAsset(path="storage/receipts/first.jpg", bill_id=10))
    session.add(FileAsset(path="storage/receipts/second.jpg", bill_id=10))
    session.commit()

    repo = FileAssetRepository(session)
    paths = [a.path for a in repo.list_by_bill(10)]
    assert [p.rsplit("/", 1)[-1] for p in paths] == ["first.jpg", "second.jpg"]
    # The Telegram invite preview can only show one — it takes the first.
    assert repo.get_first_by_bill_id(10).path.endswith("first.jpg")


def test_paid_bill_cannot_be_rescanned(client: TestClient, session):
    owner = client.post("/users/", json={"telegram_id": 5, "username": "u"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 10, "include_owner": True}
    ).json()
    stored = session.get(Bill, bill["id"])
    stored.status = BillStatus.PAID
    session.add(stored)
    session.commit()

    response = client.post(
        "/receipts/upload",
        data={"user_id": owner["id"], "bill_id": bill["id"]},
        files={"file": ("receipt.png", io.BytesIO(b"image"), "image/png")},
    )
    assert response.status_code == 409
    assert session.exec(select(ReceiptTask)).all() == []


def test_a_photo_is_compressed_off_the_event_loop(session, monkeypatch):
    """On the loop, a phone photo's re-encode held up every request meanwhile."""
    import asyncio
    import threading

    from fastapi import UploadFile

    threads = []

    def compress(raw):
        threads.append(threading.current_thread())
        return None  # kept as uploaded

    monkeypatch.setattr(receipt_service_mod, "compress_image", compress)
    service = ReceiptService(ReceiptRepository(session), FileAssetRepository(session))

    asyncio.run(service.save_receipt(UploadFile(io.BytesIO(b"x"), filename="r.jpg"), user_id=None))

    assert threads and threads[0] is not threading.main_thread()
