from typing import Literal

from pydantic import BaseModel

from app.schemas.types import UtcDatetime


class ReminderRequest(BaseModel):
    """One seat to remind, or every seat that owes when left out."""
    participant_id: int | None = None


class SkippedSeat(BaseModel):
    participant_id: int
    # guest | owner | paid | nothing_owed | cooldown
    reason: str


class ReminderRequestResponse(BaseModel):
    queued: int
    skipped: list[SkippedSeat]

    @classmethod
    def of(cls, queued: int, skipped: dict[int, str]) -> "ReminderRequestResponse":
        return cls(
            queued=queued,
            skipped=[SkippedSeat(participant_id=seat_id, reason=reason) for seat_id, reason in skipped.items()],
        )


class OwedTotal(BaseModel):
    currency: str
    amount: float


class OwedSummary(BaseModel):
    """What others owe the user on their open bills: their shares not yet paid."""
    totals: list[OwedTotal]
    people: int
    bills: int
    # Of those people, how many a reminder can go to right now.
    remindable: int
    # When the first of those reminded lately may be reminded again.
    next_reminder_at: UtcDatetime | None = None
    # With nobody to remind and nobody to wait for: what to do first to get somebody.
    why_nobody: Literal["no_bills", "no_people", "unassigned", "guests", "all_paid"] | None = None
