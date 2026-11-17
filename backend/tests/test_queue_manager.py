"""Receipt tasks handed to the worker from outside the event loop."""
import asyncio

import pytest

from app.queue_manager import QueueManager


@pytest.mark.asyncio
async def test_a_task_submitted_from_a_thread_reaches_the_waiting_worker():
    manager = QueueManager()
    waiting = asyncio.create_task(manager.get())
    await asyncio.sleep(0)

    await asyncio.to_thread(manager.submit, 7)

    assert await asyncio.wait_for(waiting, timeout=1) == 7


@pytest.mark.asyncio
async def test_a_task_submitted_before_the_worker_waits_is_kept():
    manager = QueueManager()

    manager.submit(7)

    assert await asyncio.wait_for(manager.get(), timeout=1) == 7
