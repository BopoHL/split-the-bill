"""What the app shows about Pro: whether someone has it, what it costs, what
is left of the free day."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.types import UtcDatetime


class ProPlanOffer(BaseModel):
    plan: str
    stars: int
    # The struck-out price it is down from, when the operator set one above it.
    was_stars: int | None = None
    months: int
    # Telegram renews this one by itself every thirty days.
    recurring: bool


class ProOfferTerms(BaseModel):
    """The person's one-off discount while it runs; the plans are already priced with it."""
    percent: int
    # With its zone: the app counts down to it on the phone's clock.
    ends_at: UtcDatetime


class ProOverview(BaseModel):
    active: bool
    # With its zone: read as the phone's local time, it showed a day early.
    until: UtcDatetime | None
    trial: bool
    subscription: bool
    plans: list[ProPlanOffer]
    free_scans_per_day: int
    # None with Pro: there is no limit to run into.
    scans_left_today: int | None
    free_reminders_per_month: int
    # «Remind everyone» presses left this month; None with Pro.
    reminders_left_this_month: int | None
    offer: ProOfferTerms | None = None


class ProInvoiceRequest(BaseModel):
    plan: str


class ProInvoice(BaseModel):
    link: str


class PromoRedeem(BaseModel):
    code: str = Field(min_length=1, max_length=64)
