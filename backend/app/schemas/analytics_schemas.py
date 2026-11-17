"""What the analytics screen shows. Money is in the currency most of the period's
bills were in; bills in other currencies are counted but kept out of sums."""
from datetime import datetime

from pydantic import BaseModel

from app.schemas.types import UtcDatetime


class AnalyticsPeriod(BaseModel):
    kind: str
    year: int | None = None
    month: int | None = None
    # How far back the period switcher can go.
    first_year: int | None = None
    first_month: int | None = None


class BillHighlight(BaseModel):
    id: int
    title: str | None
    created_at: UtcDatetime
    total: float
    share: float
    people: int


class TimelinePoint(BaseModel):
    """A day of a month, a month of a year, or a month of all time."""
    key: str
    amount: float
    bills: int


class OverviewStats(BaseModel):
    bills: int
    owned: int
    joined: int
    spent: float
    spent_change: float | None
    average_bill: float
    average_share: float
    biggest: BillHighlight | None
    smallest: BillHighlight | None
    collected: float
    transferred: float
    timeline: list[TimelinePoint]
    # Monday first.
    weekdays: list[int]
    # Morning, day, evening, night.
    day_parts: list[int]


class Companion(BaseModel):
    user_id: int
    name: str | None
    avatar_url: str | None
    together: int
    # At your table, and you at theirs.
    invited: int
    invited_me: int
    paid_me: float
    paid_them: float


class PaySpeed(BaseModel):
    user_id: int
    name: str | None
    minutes: int
    payments: int


class PeopleStats(BaseModel):
    companions: list[Companion]
    speed: list[PaySpeed]
    distinct: int


class GroupShare(BaseModel):
    group: str
    amount: float


class DishCount(BaseModel):
    kind: str | None
    name: str
    count: int


class Champion(BaseModel):
    kind: str
    name: str
    often: str
    often_count: int
    priciest: str
    priciest_price: float


class PriceRise(BaseModel):
    dish: str
    place: str
    first_price: float
    last_price: float
    change: float
    since: datetime


class FoodStats(BaseModel):
    groups: list[GroupShare]
    top: list[DishCount]
    champions: list[Champion]
    price_rises: list[PriceRise]
    fees: float
    # How much of the period's receipts the labeling job has got through.
    labeled: float


class PlaceStat(BaseModel):
    id: int
    name: str
    visits: int
    spent: float
    average_bill: float
    last_visit: datetime


class PlacesStats(BaseModel):
    top: list[PlaceStat]
    new: list[str]
    unplaced: int


class Badge(BaseModel):
    key: str
    value: int
    subject: str | None = None


class AnalyticsResponse(BaseModel):
    period: AnalyticsPeriod
    # Without Pro only the top of the overview is filled in: how much, how
    # many, and the running total.
    locked: bool = False
    currency: str
    other_currency_bills: int
    overview: OverviewStats
    people: PeopleStats
    food: FoodStats
    places: PlacesStats
    badges: list[Badge]


class StoryPicture(BaseModel):
    story: str
    url: str


class AnalyticsPictures(BaseModel):
    """Signed addresses of the period's pictures, good for a day."""
    receipt: str
    # A year's stories, those it has enough in it for; none for other periods.
    stories: list[StoryPicture]
    # What goes under a story when it is posted.
    story_text: str | None = None
