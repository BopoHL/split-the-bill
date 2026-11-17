import secrets
import threading
import time
from dataclasses import dataclass

TICKET_TTL_SECONDS = 60


@dataclass(frozen=True)
class _Ticket:
    user_id: int
    resource: str
    expires_at: float


class SseTicketStore:
    """Single-use, short-lived tickets for EventSource connections.

    EventSource cannot carry headers, so the signed Telegram identity is
    exchanged for something safe to put in a URL: a ticket valid once, for one
    resource, for a minute. The ticket only transports identity — the stream
    endpoint still decides whether that user may read the resource.

    Kept in process memory, which matches the single-worker deployment
    (backend/Dockerfile runs uvicorn without --workers). A second worker would
    need shared storage.
    """

    def __init__(self, ttl_seconds: int = TICKET_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._tickets: dict[str, _Ticket] = {}
        # Tickets are issued from the request threads and redeemed on the event
        # loop: without it a sweep meets a dict changing under it, and two
        # redemptions of one ticket can both get through.
        self._lock = threading.Lock()

    def issue(self, user_id: int, resource: str) -> str:
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            now = time.monotonic()
            self._evict_expired(now)
            self._tickets[ticket] = _Ticket(user_id, resource, now + self._ttl)
        return ticket

    def redeem(self, ticket: str | None, resource: str) -> int | None:
        if not ticket:
            return None
        with self._lock:
            self._evict_expired(time.monotonic())
            issued = self._tickets.get(ticket)
            if not issued or issued.resource != resource:
                return None
            # Only a matching redemption spends the ticket, so a probe for the
            # wrong resource cannot burn a legitimate one.
            del self._tickets[ticket]
        return issued.user_id

    def _evict_expired(self, now: float) -> None:
        for key in [k for k, v in self._tickets.items() if v.expires_at <= now]:
            del self._tickets[key]


def resource_key(resource_type: str, resource_id: int) -> str:
    return f"{resource_type}:{resource_id}"


sse_tickets = SseTicketStore()
