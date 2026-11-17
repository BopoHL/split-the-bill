import asyncio


class QueueManager:
    """Receipt tasks waiting for the worker, which runs on the event loop."""

    def __init__(self):
        self.queue = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def put(self, task_id: int):
        await self.queue.put(task_id)

    async def get(self) -> int:
        self._loop = asyncio.get_running_loop()
        return await self.queue.get()

    def submit(self, task_id: int) -> None:
        """Queue a task from a thread outside the event loop. Before the worker
        first waits there is no loop to hand it to, and nobody to wake: it
        reads pending tasks from the database when it starts."""
        if self._loop is None:
            self.queue.put_nowait(task_id)
        else:
            self._loop.call_soon_threadsafe(self.queue.put_nowait, task_id)

    def task_done(self):
        self.queue.task_done()


# Singleton instance
queue_manager = QueueManager()
