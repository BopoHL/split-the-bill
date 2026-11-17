"""The app's clock.

The project already runs background coroutines from the lifespan, so this
follows the same shape instead of pulling in a scheduler framework — on a 2 GB
VPS that weight buys nothing.

Every job is guarded by a Postgres advisory lock, so running more than one
backend replica can't send the same reminder twice. On SQLite (the test
database) the lock degrades to a no-op, since there is only ever one process.
"""
import asyncio
import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Engine, text
from sqlmodel import Session

from app.database import engine
from app.jobs import (
    auto_close, broadcast_sender, invite_nudges, labeling, manual_reminders, payment_notices, payment_reminders,
    pro_ending, purge_files, share_refresh, telegram_updates,
)

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
# Shared posts sit in a chat people are reading right now; a minute is long.
SHARE_REFRESH_SECONDS = 30
# An owner who pressed «Remind» is looking at the bill; the reminder should be out
# before they look away.
MANUAL_REMINDERS_SECONDS = 5
PURGE_EVERY_TICKS = 60 * 24  # once a day
# Hourly, so it runs even between frequent deploys: a job's first run waits a
# whole interval after the start.
TELEGRAM_UPDATES_PURGE_SECONDS = 60 * 60
SLOW_JOB_SECONDS = 10
JOB_TIMEOUT_SECONDS = 55
# Jobs get threads of their own: a job stuck past its timeout keeps its thread,
# and on the default pool (a few threads on a small VPS) it would hold up the
# receipt worker and file uploads that share it.
_JOB_THREADS = ThreadPoolExecutor(max_workers=12, thread_name_prefix="job")

# Arbitrary but stable keys — advisory locks are namespaced by the number alone.
LOCK_REMINDERS = 815_001
LOCK_PURGE = 815_002
LOCK_BROADCAST = 815_003
LOCK_AUTO_CLOSE = 815_004
LOCK_SHARE_REFRESH = 815_005
LOCK_MANUAL_REMINDERS = 815_006
LOCK_LABELING = 815_007
LOCK_PRO_ENDING = 815_008
LOCK_TELEGRAM_UPDATES = 815_009
LOCK_INVITE_NUDGES = 815_010
LOCK_PAYMENT_NOTICES = 815_011


@contextmanager
def advisory_lock(bind: Engine, key: int):
    """Hold a cluster-wide lock for the duration of a job, or skip the job.

    Yields False when another replica already holds it, so callers do nothing
    rather than duplicating work. The lock lives on a connection of its own: a
    Postgres advisory lock belongs to the connection, and a job's session hands
    its connection back to the pool at every commit — the lock would stay behind
    on a pooled connection instead of following the job.
    """
    if bind.dialect.name != "postgresql":
        yield True
        return

    with bind.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        acquired = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        try:
            yield bool(acquired)
        finally:
            if acquired:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


def reminders_enabled() -> bool:
    return os.getenv("REMINDERS_ENABLED", "1") not in ("0", "false", "False")


def _run_job(name: str, key: int, fn: Callable[[Session], int | None]) -> None:
    started_at = time.monotonic()
    try:
        with advisory_lock(engine, key) as acquired:
            if not acquired:
                return
            with Session(engine) as session:
                processed = fn(session) or 0
        elapsed = time.monotonic() - started_at
        if elapsed >= SLOW_JOB_SECONDS:
            logger.warning("Scheduled job %s was slow: duration=%.2fs processed=%s", name, elapsed, processed)
        elif processed:
            logger.info("Scheduled job %s processed %s in %.2fs", name, processed, elapsed)
    except Exception:  # noqa: BLE001 — a failing job must not kill the loop
        elapsed = time.monotonic() - started_at
        logger.exception("Scheduled job %s failed after %.2fs", name, elapsed)


async def _job_loop(
    name: str,
    key: int,
    fn: Callable[[Session], int | None],
    interval_seconds: float,
) -> None:
    """Run one scheduled job on its own cadence.

    Jobs are isolated so a slow reminder or broadcast tick cannot starve
    auto-closing bills.
    """
    logger.info("Scheduled job loop %s started", name)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(_JOB_THREADS, _run_job, name, key, fn),
                timeout=JOB_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Scheduled job %s exceeded %.2fs timeout; "
                "the background thread will finish when the job returns",
                name,
                JOB_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled job loop %s failed", name)


async def scheduler_loop() -> None:
    """Start each scheduled job loop and keep them alive."""
    tasks = [
        asyncio.create_task(
            _job_loop(
                "broadcast_sender",
                LOCK_BROADCAST,
                lambda s: broadcast_sender.run(s, now=datetime.utcnow()),
                TICK_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop(
                "auto_close_bills",
                LOCK_AUTO_CLOSE,
                lambda s: auto_close.run(s, datetime.utcnow()),
                TICK_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop("purge_files", LOCK_PURGE, purge_files.run, TICK_SECONDS * PURGE_EVERY_TICKS)
        ),
        asyncio.create_task(
            _job_loop(
                "telegram_updates_purge",
                LOCK_TELEGRAM_UPDATES,
                lambda s: telegram_updates.run(s, datetime.utcnow()),
                TELEGRAM_UPDATES_PURGE_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop(
                "share_refresh",
                LOCK_SHARE_REFRESH,
                lambda s: share_refresh.run(s, datetime.utcnow()),
                SHARE_REFRESH_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop(
                "manual_reminders",
                LOCK_MANUAL_REMINDERS,
                manual_reminders.run,
                MANUAL_REMINDERS_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop(
                "labeling",
                LOCK_LABELING,
                lambda s: labeling.run(s, datetime.utcnow()),
                TICK_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop(
                "pro_ending",
                LOCK_PRO_ENDING,
                lambda s: pro_ending.run(s, datetime.utcnow()),
                TICK_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop(
                "invite_nudges",
                LOCK_INVITE_NUDGES,
                lambda s: invite_nudges.run(s, datetime.utcnow()),
                TICK_SECONDS,
            )
        ),
        asyncio.create_task(
            _job_loop(
                "payment_notices",
                LOCK_PAYMENT_NOTICES,
                lambda s: payment_notices.run(s, datetime.utcnow()),
                TICK_SECONDS,
            )
        ),
    ]
    if reminders_enabled():
        tasks.append(
            asyncio.create_task(
                _job_loop(
                    "payment_reminders",
                    LOCK_REMINDERS,
                    lambda s: payment_reminders.run(s, datetime.utcnow()),
                    TICK_SECONDS,
                )
            )
        )

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
