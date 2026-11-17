import asyncio
import contextlib
import logging
import time
from contextlib import contextmanager

import pytest

import app.scheduler as scheduler


class _FakeSession:
    def __init__(self, engine):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_auto_close_loop_runs_when_reminders_are_busy(monkeypatch):
    loop = asyncio.get_running_loop()
    auto_close_called = asyncio.Event()

    def fake_run_job(name, key, fn):
        if name == "payment_reminders":
            time.sleep(0.35)
            return
        if name == "auto_close_bills":
            loop.call_soon_threadsafe(auto_close_called.set)

    monkeypatch.setattr(scheduler, "TICK_SECONDS", 0.01)
    monkeypatch.setattr(scheduler, "reminders_enabled", lambda: True)
    monkeypatch.setattr(scheduler, "_run_job", fake_run_job)

    task = asyncio.create_task(scheduler.scheduler_loop())
    try:
        await asyncio.wait_for(auto_close_called.wait(), timeout=0.2)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def test_run_job_logs_slow_jobs(monkeypatch, caplog):
    @contextmanager
    def fake_lock(bind, key):
        yield True

    def slow_job(session):
        time.sleep(0.02)
        return 3

    monkeypatch.setattr(scheduler, "Session", _FakeSession)
    monkeypatch.setattr(scheduler, "SLOW_JOB_SECONDS", 0.01)
    monkeypatch.setattr(scheduler, "advisory_lock", fake_lock)

    caplog.set_level(logging.WARNING, logger=scheduler.logger.name)

    scheduler._run_job("slow_test", 1, slow_job)

    assert "Scheduled job slow_test was slow" in caplog.text
    assert "processed=3" in caplog.text


@pytest.mark.asyncio
async def test_job_loop_logs_timeouts(monkeypatch, caplog):
    def blocked_run_job(name, key, fn):
        time.sleep(0.2)

    monkeypatch.setattr(scheduler, "_run_job", blocked_run_job)
    monkeypatch.setattr(scheduler, "JOB_TIMEOUT_SECONDS", 0.01)
    caplog.set_level(logging.ERROR, logger=scheduler.logger.name)

    task = asyncio.create_task(
        scheduler._job_loop("blocked_test", 1, lambda session: None, 0.01)
    )
    try:
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if "Scheduled job blocked_test exceeded" in caplog.text:
                break
            await asyncio.sleep(0.01)
        assert "Scheduled job blocked_test exceeded" in caplog.text
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_shared_posts_are_refreshed_on_their_own_cadence(monkeypatch):
    loop = asyncio.get_running_loop()
    refreshed = asyncio.Event()

    def fake_run_job(name, key, fn):
        if name == "share_refresh":
            loop.call_soon_threadsafe(refreshed.set)

    monkeypatch.setattr(scheduler, "SHARE_REFRESH_SECONDS", 0.01)
    monkeypatch.setattr(scheduler, "reminders_enabled", lambda: False)
    monkeypatch.setattr(scheduler, "_run_job", fake_run_job)

    task = asyncio.create_task(scheduler.scheduler_loop())
    try:
        await asyncio.wait_for(refreshed.wait(), timeout=0.2)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
