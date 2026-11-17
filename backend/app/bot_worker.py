"""The bot's worker: handles the Telegram updates the webhook has stored.

It runs on the event loop like the receipt worker, but every update is handled
in a thread of its own — from a pool of the worker's own, not the one the
scheduler and the receipt worker share — so the Bot API calls and the database
it waits on hold up nothing else, and nothing else holds it up. The webhook
wakes it the moment it stores an update; a slow poll picks up the rest —
updates stored before a restart, payments waiting to be tried again, anything
another replica left behind.
"""
import asyncio
import logging
import os
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlmodel import Session

from app.database import engine
from app.services.telegram_updates import TelegramUpdateQueue

logger = logging.getLogger(__name__)

# Updates handled at once. Each waits mostly on Telegram, so a few are enough
# for the chats of many people; one lane never gets more than one of them.
SLOTS = int(os.getenv("BOT_UPDATE_WORKERS", "4"))
POLL_SECONDS = 5
# Well within the lease, so a slow update is never taken from a worker still on it.
HOLD_EVERY_SECONDS = 10
# On shutdown, the updates in hand get this long to finish — within what is
# left of Docker's ten seconds after uvicorn's five (see the Dockerfile); the
# rest are taken again after a restart, once their lease runs out.
SHUTDOWN_GRACE_SECONDS = 4


class UpdateWorker:
    def __init__(self, slots: int, sessions: Callable[[], Session]):
        self.slots = slots
        self.sessions = sessions
        self.holder = uuid.uuid4().hex
        # A thread per slot, and one to take updates and renew the hold.
        self._threads = ThreadPoolExecutor(max_workers=slots + 1, thread_name_prefix="bot-update")
        # What this worker is on: each update's lane and the task handling it.
        self._in_hand: dict[int, tuple[str, asyncio.Task]] = {}
        self._wakeup = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    def wake(self) -> None:
        """There is something new to handle. Safe from any thread: the webhook
        runs in the thread pool."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._wakeup.set)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        logger.info("Bot worker started with %s slots", self.slots)
        holding = asyncio.create_task(self._keep_holding())
        try:
            while True:
                self._wakeup.clear()
                await self._take_what_is_ready()
                await self._wait_for_news()
        finally:
            if self._in_hand:
                await asyncio.wait([task for _, task in self._in_hand.values()], timeout=SHUTDOWN_GRACE_SECONDS)
            holding.cancel()
            self._threads.shutdown(wait=False)

    async def _wait_for_news(self) -> None:
        """Until woken, or the next poll. Not asyncio.wait_for: on Python 3.11
        it can swallow the worker's own cancellation when a wake-up lands at
        the same moment, and the worker would never stop."""
        news = asyncio.ensure_future(self._wakeup.wait())
        try:
            await asyncio.wait({news}, timeout=POLL_SECONDS)
        finally:
            news.cancel()

    async def _keep_holding(self) -> None:
        """Renew the lease on what is in hand, however long it takes."""
        while True:
            await asyncio.sleep(HOLD_EVERY_SECONDS)
            if not self._in_hand:
                continue
            try:
                await self._in_thread(self._hold, list(self._in_hand))
            except Exception:  # noqa: BLE001 — tried again at the next round
                logger.exception("Could not renew the hold on Telegram updates")

    async def _take_what_is_ready(self) -> None:
        free = self.slots - len(self._in_hand)
        if free <= 0:
            return
        try:
            busy_lanes = frozenset(lane for lane, _ in self._in_hand.values())
            claimed = await self._in_thread(self._claim, free, busy_lanes)
        except Exception:  # noqa: BLE001 — the database may be back by the next poll
            logger.exception("Could not take Telegram updates")
            return
        for update_id, lane in claimed.items():
            self._in_hand[update_id] = (lane, asyncio.create_task(self._handle(update_id)))

    async def _handle(self, update_id: int) -> None:
        try:
            await self._in_thread(self._handle_in_thread, update_id)
        except Exception:  # noqa: BLE001 — its lease runs out and it is taken again
            logger.exception("Telegram update %s was left unfinished", update_id)
        finally:
            del self._in_hand[update_id]
            # Its lane may have the next update waiting, and a slot is free.
            self._wakeup.set()

    def _in_thread(self, work: Callable, *args):
        return self._loop.run_in_executor(self._threads, work, *args)

    def _claim(self, limit: int, busy_lanes: frozenset[str]) -> dict[int, str]:
        with self.sessions() as session:
            return TelegramUpdateQueue(session).claim(
                datetime.utcnow(), limit, holder=self.holder, busy_lanes=busy_lanes,
            )

    def _hold(self, update_ids: list[int]) -> None:
        with self.sessions() as session:
            TelegramUpdateQueue(session).hold(update_ids, datetime.utcnow(), holder=self.holder)

    def _handle_in_thread(self, update_id: int) -> None:
        with self.sessions() as session:
            TelegramUpdateQueue(session).handle(update_id, holder=self.holder)


update_worker = UpdateWorker(SLOTS, lambda: Session(engine))
