import asyncio
import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)

class Notifier:
    def __init__(self):
        # bill_id -> set of queues
        self.connections: Dict[int, Set[asyncio.Queue]] = {}

    async def subscribe(self, bill_id: int):
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
        if bill_id not in self.connections:
            return
            
        for queue in self.connections[bill_id]:
            queue.put_nowait(message)
        
        logger.info(f"Broadcasted '{message}' to {len(self.connections[bill_id])} listeners of bill {bill_id}")

# Singleton instance
notifier = Notifier()
