import asyncio
import logging
import threading
from typing import Dict, Set

logger = logging.getLogger(__name__)


class Notifier:
    """A bill's news for the app screens watching it, over SSE.

    The streams live on the event loop, while a bill changes in any thread — a
    request, a scheduled job, the bot's worker. News is handed to the loop, which
    alone touches the streams."""

    def __init__(self):
        # bill_id -> set of queues
        self.connections: Dict[int, Set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        # Bills changed since the shared posts last caught up; any thread adds.
        self._changed: set[int] = set()
        self._changed_lock = threading.Lock()

    async def subscribe(self, bill_id: int):
        self._loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        if bill_id not in self.connections:
            self.connections[bill_id] = set()
        self.connections[bill_id].add(queue)

        logger.info(f"New subscription for bill {bill_id}. Total listeners: {len(self.connections[bill_id])}")

        try:
            while True:
                try:
                    # Wait for a message with a timeout for heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield message
                except asyncio.TimeoutError:
                    # Send a comment line as heartbeat to keep connection alive
                    yield ": ping\n"
        finally:
            self.connections[bill_id].remove(queue)
            if not self.connections[bill_id]:
                del self.connections[bill_id]
            logger.info(f"Subscription ended for bill {bill_id}. Remaining: {len(self.connections.get(bill_id, []))}")

    def broadcast(self, bill_id: int, message: str):
        """Safe from any thread."""
        self.mark_changed({bill_id})
        if bill_id in self.connections and self._loop is not None:
            self._loop.call_soon_threadsafe(self._deliver, bill_id, message)

    def mark_changed(self, bill_ids: set[int]) -> None:
        with self._changed_lock:
            self._changed |= bill_ids

    def take_changed(self) -> set[int]:
        """The bills changed since the last call, and forget them."""
        with self._changed_lock:
            changed, self._changed = self._changed, set()
        return changed

    def _deliver(self, bill_id: int, message: str):
        listeners = self.connections.get(bill_id, set())
        for queue in listeners:
            queue.put_nowait(message)

        logger.info(f"Broadcasted '{message}' to {len(listeners)} listeners of bill {bill_id}")


# Singleton instance
notifier = Notifier()
