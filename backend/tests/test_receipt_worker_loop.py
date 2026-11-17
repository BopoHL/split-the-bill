import asyncio
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import app.worker as worker
from app.models import ReceiptTask, ReceiptTaskStatus
from app.queue_manager import QueueManager


@pytest.fixture
def worker_engine(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(worker, "engine", engine)
    monkeypatch.setattr(worker, "queue_manager", QueueManager())
    return engine


async def _run_worker_until(condition):
    loop_task = asyncio.create_task(worker.worker_loop())
    for _ in range(100):
        await asyncio.sleep(0.01)
        if condition():
            break
    loop_task.cancel()
    await asyncio.gather(loop_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_scans_are_handled_side_by_side(worker_engine, monkeypatch):
    """A scan waits 10–30 s on the model, and the app gives up after 90 s."""
    running, peak, finish = set(), [0], asyncio.Event()

    async def slow_scan(task_id):
        running.add(task_id)
        peak[0] = max(peak[0], len(running))
        await finish.wait()
        running.discard(task_id)

    monkeypatch.setattr(worker, "process_task", slow_scan)
    for task_id in range(5):
        await worker.queue_manager.put(task_id)

    await _run_worker_until(lambda: peak[0] >= worker.CONCURRENT_SCANS)
    finish.set()

    assert peak[0] == worker.CONCURRENT_SCANS


@pytest.mark.asyncio
async def test_a_restart_picks_up_only_the_scans_it_just_cut_off(worker_engine, monkeypatch):
    with Session(worker_engine) as session:
        for status in ReceiptTaskStatus:
            session.add(ReceiptTask(status=status))
        # Left hanging by a restart weeks ago: its owner is long gone.
        session.add(ReceiptTask(
            status=ReceiptTaskStatus.PROCESSING, updated_at=datetime.utcnow() - timedelta(days=30),
        ))
        session.commit()
    started = []

    async def scan(task_id):
        started.append(task_id)

    monkeypatch.setattr(worker, "process_task", scan)
    await _run_worker_until(lambda: False)  # every chance for a fourth to start

    assert len(started) == 3
    with Session(worker_engine) as session:
        statuses = {session.get(ReceiptTask, task_id).status for task_id in started}
    assert statuses == {
        ReceiptTaskStatus.PENDING, ReceiptTaskStatus.PROCESSING, ReceiptTaskStatus.STRUCTURING,
    }
