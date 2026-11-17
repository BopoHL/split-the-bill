"""Soliq QR import: the worker builds a bill straight from the check's JSON API
(no OCR/LLM), fails cleanly when the receipt isn't ready yet, and the upload-qr
endpoint gates on the URL."""
import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

import app.worker as worker
from app.services.soliq import SoliqReceiptNotReady
from app.queue_manager import queue_manager
from app.models import (
    User, Bill, BillItem, BillUser, BillStatus,
    ReceiptTask, ReceiptTaskStatus, ReceiptSource, SplitType,
)
from app.utils.currency import to_tiins

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "soliq_payment_sample.json")
VALID_URL = "https://ofd.soliq.uz/check?t=LG420211643372&r=11975&c=20260619124101&s=133935061946"


def _sample_payment() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _async_return(value):
    async def _fn(*args, **kwargs):
        return value
    return _fn


def _async_raise(exc):
    async def _fn(*args, **kwargs):
        raise exc
    return _fn


@pytest.fixture
def worker_engine(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(worker, "engine", engine)
    return engine


def _make_qr_task(engine, source_url=VALID_URL):
    """A provisional UZS bill already exists (created up front by the endpoint)
    and the QR task points at it — mirrors the real flow."""
    with Session(engine) as s:
        user = User(telegram_id=77, username="qr")
        s.add(user)
        s.commit()
        s.refresh(user)
        bill = Bill(
            owner_id=user.id, total_sum=0, unallocated_sum=0,
            status=BillStatus.OPEN, currency="uzs",
        )
        s.add(bill)
        s.commit()
        s.refresh(bill)
        s.add(BillUser(bill_id=bill.id, user_id=user.id, allocated_amount=0))
        s.commit()
        task = ReceiptTask(
            user_id=user.id, filename=None, source=ReceiptSource.SOLIQ_QR,
            source_url=source_url, status=ReceiptTaskStatus.PENDING, bill_id=bill.id,
            owns_bill=True,
        )
        s.add(task)
        s.commit()
        s.refresh(task)
        return user.id, task.id


# --- worker: happy path (JSON API, no LLM) -------------------------------

def test_qr_worker_builds_bill_from_api(worker_engine, monkeypatch):
    _, task_id = _make_qr_task(worker_engine)
    monkeypatch.setattr(worker, "fetch_soliq_payment", _async_return(_sample_payment()))
    # Deliberately do NOT stub OpenAI/Vision: the Soliq path must not touch them.

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.COMPLETED
        bill = s.get(Bill, task.bill_id)
        items = s.exec(select(BillItem).where(BillItem.bill_id == bill.id)).all()
        assert len(items) == 2
        assert bill.split_type == SplitType.BY_ITEMS
        # Bill total = sum of line totals = the receipt's grand total.
        assert bill.total_sum == to_tiins(52500)

        pizza = next(i for i in items if i.count == 4)
        assert pizza.item_sum == to_tiins(52000)        # line total kept as-is
        assert pizza.price == to_tiins(52000) // 4       # per-unit for display
        assert task.llm_response  # parsed payload stored for debugging


# --- worker: receipt not in the OFD yet → clean failure ------------------

def test_qr_worker_fails_when_receipt_not_ready(worker_engine, monkeypatch):
    _, task_id = _make_qr_task(worker_engine)
    monkeypatch.setattr(
        worker, "fetch_soliq_payment",
        _async_raise(SoliqReceiptNotReady("not ready")),
    )

    asyncio.run(worker.process_task(task_id))

    with Session(worker_engine) as s:
        task = s.get(ReceiptTask, task_id)
        assert task.status == ReceiptTaskStatus.FAILED
        # Failed scan leaves nothing behind: the provisional bill is removed.
        assert task.bill_id is None
        assert s.exec(select(Bill)).all() == []


# --- endpoint: URL allow-list -------------------------------------------

@pytest.fixture
def _no_queue(monkeypatch):
    """The endpoint enqueues to a module-level asyncio.Queue; under TestClient
    that can cross event loops, so stub put() — the worker is tested directly."""
    monkeypatch.setattr(queue_manager, "put", _async_return(None))


def test_upload_qr_rejects_non_soliq_url(client: TestClient, _no_queue):
    owner = client.post("/users/", json={"telegram_id": 88, "username": "q"}).json()
    resp = client.post(
        "/receipts/upload-qr",
        data={"qr_url": "https://evil.example.com/check?t=1&r=1&c=1&s=1", "user_id": owner["id"]},
    )
    assert resp.status_code == 400


def test_upload_qr_creates_task_and_uzs_bill(client: TestClient, _no_queue):
    owner = client.post("/users/", json={"telegram_id": 89, "username": "q2"}).json()
    resp = client.post(
        "/receipts/upload-qr", data={"qr_url": VALID_URL, "user_id": owner["id"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["bill_id"] is not None
    assert body["filename"] is None
    # Bill is bound to UZS (Soliq receipts are always in sum).
    detail = client.get(f"/bills/{body['bill_id']}?user_id={owner['id']}").json()
    assert detail["currency"] == "uzs"
