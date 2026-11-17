"""A person's bills seen from above: how much, how often, with whom, what and
where — for a month, a year or all time.

Everything is counted from the person's side. Money is their own share; dishes
are the ones they had (the portions they were given, or an equal part of a bill
nobody assigned dishes in); people are the others at the table. Sums are in the
currency most of the period's bills were in, since adding sums to dollars says
nothing.
"""
import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from statistics import median
from zoneinfo import ZoneInfo

from sqlmodel import Session, func, select

from app.models import (
    Bill,
    BillItem,
    BillItemAssignment,
    BillUser,
    DishGroup,
    DishKind,
    DishLabel,
    Place,
    User,
    dish_key,
)
from app.repositories.bill_repo import BillRepository
from app.schemas.analytics_schemas import (
    AnalyticsPeriod,
    AnalyticsResponse,
    Badge,
    BillHighlight,
    Champion,
    Companion,
    DishCount,
    FoodStats,
    GroupShare,
    OverviewStats,
    PaySpeed,
    PeopleStats,
    PlacesStats,
    PlaceStat,
    PriceRise,
    TimelinePoint,
)
from app.utils.local_time import local_zone
from app.services.shared_bill_service import language_of
from app.utils.currency import from_tiins

TOP_PEOPLE = 8
TOP_DISHES = 6
TOP_CHAMPIONS = 4
TOP_PLACES = 8
TOP_PRICE_RISES = 3
MIN_PRICE_RISE = 0.05
# Morning from 5, day from 11, evening from 17, night from 23.
DAY_PART_STARTS = (5, 11, 17, 23)
SPENDING_GROUPS = (DishGroup.FOOD, DishGroup.DRINK, DishGroup.ALCOHOL, DishGroup.DESSERT, DishGroup.FEE, DishGroup.OTHER)

COFFEE_KINDS = {"coffee", "cappuccino", "latte", "americano", "espresso", "flat_white", "raf", "raf_coffee", "mocha", "macchiato"}
MEAT_KINDS = {"shashlik", "kebab", "steak", "kabob", "barbecue", "ribs", "lula_kebab"}


class PeriodKind(str, Enum):
    MONTH = "month"
    YEAR = "year"
    ALL = "all"


@dataclass(frozen=True)
class Period:
    kind: PeriodKind
    year: int | None = None
    month: int | None = None

    @classmethod
    def named(cls, kind: PeriodKind, year: int | None, month: int | None, today: date) -> "Period":
        """The period asked for: a month or year not named is the current one."""
        return cls(
            kind,
            year=None if kind == PeriodKind.ALL else year or today.year,
            month=(month or today.month) if kind == PeriodKind.MONTH else None,
        )

    def bounds(self, zone: ZoneInfo) -> tuple[datetime | None, datetime | None]:
        """The period as naive UTC, the way bills keep their time."""
        if self.kind == PeriodKind.ALL:
            return None, None
        if self.kind == PeriodKind.YEAR:
            start, end = datetime(self.year, 1, 1), datetime(self.year + 1, 1, 1)
        else:
            start = datetime(self.year, self.month, 1)
            end = datetime(self.year + (self.month == 12), self.month % 12 + 1, 1)
        return _utc(start.replace(tzinfo=zone)), _utc(end.replace(tzinfo=zone))

    def previous(self) -> "Period | None":
        if self.kind == PeriodKind.YEAR:
            return Period(PeriodKind.YEAR, self.year - 1)
        if self.kind == PeriodKind.MONTH:
            return Period(PeriodKind.MONTH, self.year - (self.month == 1), (self.month - 2) % 12 + 1)
        return None


def free_view(data: AnalyticsResponse) -> AnalyticsResponse:
    """What analytics shows without Pro: how much was spent and how that
    compares, how many bills, the average, and the running total. The rest is
    left empty for the paywall to stand in for."""
    overview = data.overview.model_copy(update={
        "weekdays": [0] * 7, "day_parts": [0] * len(DAY_PART_STARTS), "biggest": None, "smallest": None,
        "collected": 0, "transferred": 0,
    })
    return data.model_copy(update={
        "locked": True,
        "overview": overview,
        "people": PeopleStats(companions=[], speed=[], distinct=0),
        "food": FoodStats(groups=[], top=[], champions=[], price_rises=[], fees=0, labeled=1),
        "places": PlacesStats(top=[], new=[], unplaced=0),
        "badges": [],
    })


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class _Table:
    """One of the person's bills with everything about it the numbers need."""

    bill: Bill
    seats: list[BillUser]
    items: list[BillItem]
    # item id → portion → the seats sharing it
    portions: dict[int, dict[int, set[int]]]
    mine: BillUser | None
    local: datetime

    @property
    def owned_by(self) -> int:
        return self.bill.owner_id

    @property
    def my_share(self) -> int:
        return self.mine.allocated_amount if self.mine else 0


class AnalyticsService:
    def __init__(self, session: Session):
        self.session = session

    def for_user(self, user: User, period: Period, now: datetime) -> AnalyticsResponse:
        zone = local_zone()
        tables = self._tables(user.id, *period.bounds(zone), zone)
        currency, other = _dominant_currency(tables)
        counted = [table for table in tables if table.bill.currency == currency]
        spent_before = self._spent_before(user.id, currency, period, zone, now)

        labels = self._labels(tables)
        kinds = self._kinds(labels, language_of(user))
        overview = _overview(tables, counted, user.id, period, spent_before, zone, now)
        people = self._people(tables, counted, user.id)
        food, kind_counts = _food(counted, labels, kinds, self._place_names(tables))
        places = self._places(tables, counted, user.id, period, zone)
        return AnalyticsResponse(
            period=self._period(user.id, period, zone),
            currency=currency,
            other_currency_bills=other,
            overview=overview,
            people=people,
            food=food,
            places=places,
            badges=_badges(overview, people, kind_counts, places, _my_waits(tables, user.id)),
        )

    # ── Loading ──────────────────────────────────────────────────────────────

    def _tables(self, user_id: int, start: datetime | None, end: datetime | None, zone: ZoneInfo) -> list[_Table]:
        conditions = BillRepository.user_bill_conditions(user_id, None, None, None)
        if start:
            conditions += [Bill.created_at >= start, Bill.created_at < end]
        bills = list(self.session.exec(select(Bill).where(*conditions).order_by(Bill.created_at)).all())
        ids = [bill.id for bill in bills]
        if not ids:
            return []

        seats: dict[int, list[BillUser]] = defaultdict(list)
        for seat in self.session.exec(select(BillUser).where(BillUser.bill_id.in_(ids))).all():
            seats[seat.bill_id].append(seat)
        items: dict[int, list[BillItem]] = defaultdict(list)
        for item in self.session.exec(select(BillItem).where(BillItem.bill_id.in_(ids)).order_by(BillItem.id)).all():
            items[item.bill_id].append(item)
        portions: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        item_ids = [item.id for bill_items in items.values() for item in bill_items]
        if item_ids:
            for assignment in self.session.exec(
                select(BillItemAssignment).where(BillItemAssignment.bill_item_id.in_(item_ids))
            ).all():
                portions[assignment.bill_item_id][assignment.portion_index].add(assignment.participant_id)

        return [
            _Table(
                bill=bill,
                seats=seats[bill.id],
                items=items[bill.id],
                portions={item.id: portions[item.id] for item in items[bill.id] if item.id in portions},
                mine=next((seat for seat in seats[bill.id] if seat.user_id == user_id), None),
                local=_local(bill.created_at, zone),
            )
            for bill in bills
        ]

    def _spent_before(self, user_id: int, currency: str, period: Period, zone: ZoneInfo, now: datetime) -> int | None:
        """What the period before had been spent by the same point: a month
        four days in is set against the first four days of the last one."""
        previous = period.previous()
        if previous is None:
            return None
        start, end = period.bounds(zone)
        before_start, before_end = previous.bounds(zone)
        if start <= now < end:
            before_end = min(before_end, before_start + (now - start))
        return self._spent(user_id, currency, before_start, before_end)

    def _spent(self, user_id: int, currency: str, start: datetime, end: datetime) -> int:
        return self.session.exec(
            select(func.coalesce(func.sum(BillUser.allocated_amount), 0))
            .join(Bill, Bill.id == BillUser.bill_id)
            .where(
                BillUser.user_id == user_id,
                Bill.currency == currency,
                Bill.deleted_at.is_(None),
                Bill.is_demo.is_(False),
                Bill.created_at >= start,
                Bill.created_at < end,
            )
        ).one()

    def _labels(self, tables: list[_Table]) -> dict[str, DishLabel]:
        keys = {dish_key(item.name) for table in tables for item in table.items}
        if not keys:
            return {}
        return {label.name_key: label for label in self.session.exec(select(DishLabel).where(DishLabel.name_key.in_(keys))).all()}

    def _kinds(self, labels: dict[str, DishLabel], language: str) -> dict[str, str]:
        keys = {label.kind for label in labels.values() if label.kind}
        if not keys:
            return {}
        return {kind.key: getattr(kind, language) for kind in self.session.exec(select(DishKind).where(DishKind.key.in_(keys))).all()}

    def _place_names(self, tables: list[_Table]) -> dict[int, str]:
        ids = {table.bill.place_id for table in tables if table.bill.place_id}
        if not ids:
            return {}
        return {place.id: place.name for place in self.session.exec(select(Place).where(Place.id.in_(ids))).all()}

    def _period(self, user_id: int, period: Period, zone: ZoneInfo) -> AnalyticsPeriod:
        first = self.session.exec(
            select(func.min(Bill.created_at)).where(*BillRepository.user_bill_conditions(user_id, None, None, None))
        ).one()
        first_local = _local(first, zone) if first else None
        return AnalyticsPeriod(
            kind=period.kind.value,
            year=period.year,
            month=period.month,
            first_year=first_local.year if first_local else None,
            first_month=first_local.month if first_local else None,
        )

    # ── People ───────────────────────────────────────────────────────────────

    def _people(self, tables: list[_Table], counted: list[_Table], me: int) -> PeopleStats:
        together: Counter[int] = Counter()
        invited: Counter[int] = Counter()
        invited_me: Counter[int] = Counter()
        for table in tables:
            others = {seat.user_id for seat in table.seats if seat.user_id and seat.user_id != me}
            if table.owned_by != me:
                others.add(table.owned_by)
                invited_me[table.owned_by] += 1
            else:
                invited.update(others)
            together.update(others)

        paid_me: Counter[int] = Counter()
        paid_them: Counter[int] = Counter()
        waits: dict[int, list[float]] = defaultdict(list)
        for table in counted:
            if table.owned_by == me:
                for seat in table.seats:
                    if seat.user_id and seat.user_id != me and seat.is_paid:
                        paid_me[seat.user_id] += seat.allocated_amount
                        if seat.paid_at:
                            began = max(table.bill.created_at, seat.claimed_at or table.bill.created_at)
                            waits[seat.user_id].append(max(0.0, (seat.paid_at - began).total_seconds() / 60))
            elif table.mine and table.mine.is_paid:
                paid_them[table.owned_by] += table.mine.allocated_amount

        people = {user.id: user for user in self.session.exec(select(User).where(User.id.in_(set(together)))).all()} if together else {}

        def name(user_id: int) -> str | None:
            person = people.get(user_id)
            return (person.name or person.username) if person else None

        companions = [
            Companion(
                user_id=user_id,
                name=name(user_id),
                avatar_url=people[user_id].avatar_url if user_id in people else None,
                together=count,
                invited=invited[user_id],
                invited_me=invited_me[user_id],
                paid_me=from_tiins(paid_me[user_id]),
                paid_them=from_tiins(paid_them[user_id]),
            )
            for user_id, count in sorted(together.items(), key=lambda pair: (-pair[1], pair[0]))[:TOP_PEOPLE]
        ]
        speed = sorted(
            (
                PaySpeed(user_id=user_id, name=name(user_id), minutes=round(median(minutes)), payments=len(minutes))
                for user_id, minutes in waits.items()
            ),
            key=lambda entry: entry.minutes,
        )
        return PeopleStats(companions=companions, speed=speed, distinct=len(together))

    # ── Places ───────────────────────────────────────────────────────────────

    def _places(self, tables: list[_Table], counted: list[_Table], me: int, period: Period, zone: ZoneInfo) -> PlacesStats:
        names = self._place_names(tables)
        visits: dict[int, list[_Table]] = defaultdict(list)
        for table in tables:
            if table.bill.place_id in names:
                visits[table.bill.place_id].append(table)
        counted_ids = {table.bill.id for table in counted}

        top = []
        for place_id, place_tables in visits.items():
            money = [table for table in place_tables if table.bill.id in counted_ids]
            totals = [table.bill.total_sum for table in money if table.bill.total_sum > 0]
            top.append(PlaceStat(
                id=place_id,
                name=names[place_id],
                visits=len(place_tables),
                spent=from_tiins(sum(table.my_share for table in money)),
                average_bill=from_tiins(round(sum(totals) / len(totals))) if totals else 0,
                last_visit=max(table.bill.created_at for table in place_tables),
            ))
        top.sort(key=lambda place: (-place.visits, -place.spent, place.name))

        start, _ = period.bounds(zone)
        new: list[str] = []
        if start and visits:
            seen_before = set(self.session.exec(
                select(Bill.place_id).where(
                    *BillRepository.user_bill_conditions(me, None, None, None),
                    Bill.place_id.in_(list(visits)),
                    Bill.created_at < start,
                ).distinct()
            ).all())
            new = sorted(names[place_id] for place_id in visits if place_id not in seen_before)
        return PlacesStats(
            top=top[:TOP_PLACES],
            new=new,
            unplaced=sum(1 for table in tables if table.owned_by == me and not table.bill.place_id),
        )


# ── Overview ─────────────────────────────────────────────────────────────────

def _overview(
    tables: list[_Table],
    counted: list[_Table],
    me: int,
    period: Period,
    spent_before: int | None,
    zone: ZoneInfo,
    now: datetime,
) -> OverviewStats:
    spent = sum(table.my_share for table in counted)
    priced = [table for table in counted if table.bill.total_sum > 0]
    shares = [table.my_share for table in counted if table.my_share > 0]
    weekdays = [0] * 7
    day_parts = [0] * 4
    for table in tables:
        weekdays[table.local.weekday()] += 1
        day_parts[_day_part(table.local.hour)] += 1

    return OverviewStats(
        bills=len(tables),
        owned=sum(1 for table in tables if table.owned_by == me),
        joined=sum(1 for table in tables if table.owned_by != me),
        spent=from_tiins(spent),
        spent_change=round((spent - spent_before) / spent_before * 100, 1) if spent_before else None,
        average_bill=from_tiins(round(sum(table.bill.total_sum for table in priced) / len(priced))) if priced else 0,
        average_share=from_tiins(round(sum(shares) / len(shares))) if shares else 0,
        biggest=_highlight(max(priced, key=lambda table: table.bill.total_sum)) if priced else None,
        smallest=_highlight(min(priced, key=lambda table: table.bill.total_sum)) if len(priced) > 1 else None,
        collected=from_tiins(sum(
            seat.allocated_amount
            for table in counted if table.owned_by == me
            for seat in table.seats if seat.is_paid and seat.user_id != me
        )),
        transferred=from_tiins(sum(
            table.my_share for table in counted if table.owned_by != me and table.mine and table.mine.is_paid
        )),
        timeline=_timeline(tables, counted, period, _local(now, zone)),
        weekdays=weekdays,
        day_parts=day_parts,
    )


def _highlight(table: _Table) -> BillHighlight:
    return BillHighlight(
        id=table.bill.id,
        title=table.bill.title,
        created_at=table.bill.created_at.replace(tzinfo=timezone.utc),
        total=from_tiins(table.bill.total_sum),
        share=from_tiins(table.my_share),
        people=len(table.seats),
    )


def _timeline(tables: list[_Table], counted: list[_Table], period: Period, today: datetime) -> list[TimelinePoint]:
    if period.kind == PeriodKind.MONTH:
        days = calendar.monthrange(period.year, period.month)[1]
        if (period.year, period.month) == (today.year, today.month):
            days = today.day
        keys = [f"{period.year:04d}-{period.month:02d}-{day:02d}" for day in range(1, days + 1)]
        key_of = lambda moment: moment.strftime("%Y-%m-%d")
    else:
        if period.kind == PeriodKind.YEAR:
            first, last = (period.year, 1), (period.year, 12 if period.year < today.year else today.month)
        elif tables:
            first, last = (tables[0].local.year, tables[0].local.month), (today.year, today.month)
        else:
            return []
        keys = []
        year, month = first
        while (year, month) <= last:
            keys.append(f"{year:04d}-{month:02d}")
            year, month = year + (month == 12), month % 12 + 1
        key_of = lambda moment: moment.strftime("%Y-%m")

    amounts: Counter[str] = Counter()
    bills: Counter[str] = Counter()
    for table in tables:
        bills[key_of(table.local)] += 1
    for table in counted:
        amounts[key_of(table.local)] += table.my_share
    return [TimelinePoint(key=key, amount=from_tiins(amounts[key]), bills=bills[key]) for key in keys]


def _day_part(hour: int) -> int:
    morning, day, evening, night = DAY_PART_STARTS
    if morning <= hour < day:
        return 0
    if day <= hour < evening:
        return 1
    if evening <= hour < night:
        return 2
    return 3


# ── Food ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Had:
    """A receipt line from the person's side: what they paid for it and how
    much of it they had — three beers shared by three is one beer each."""

    item: BillItem
    table: _Table
    amount: float
    count: float


def _food(
    counted: list[_Table],
    labels: dict[str, DishLabel],
    kinds: dict[str, str],
    places: dict[int, str],
) -> tuple[FoodStats, Counter[str]]:
    """What the person had, and how many of each kind — the badges count those."""
    had = [line for table in counted for line in _lines_had(table)]
    groups: Counter[str] = Counter()
    by_kind: dict[str, list[_Had]] = defaultdict(list)
    plain: Counter[str] = Counter()
    plain_names: dict[str, str] = {}
    labeled = 0
    for line in had:
        label = labels.get(dish_key(line.item.name))
        labeled += label is not None
        group = DishGroup(label.group) if label else DishGroup.OTHER
        groups[group] += line.amount
        if label and label.kind and label.kind in kinds:
            by_kind[label.kind].append(line)
        elif group in (DishGroup.FOOD, DishGroup.DRINK, DishGroup.DESSERT, DishGroup.ALCOHOL):
            key = dish_key(line.item.name)
            plain[key] += line.count
            plain_names.setdefault(key, line.item.name.strip())

    kind_counts = Counter({kind: _whole(sum(line.count for line in lines)) for kind, lines in by_kind.items()})
    counts = [DishCount(kind=kind, name=kinds[kind], count=kind_counts[kind]) for kind in by_kind]
    counts += [DishCount(kind=None, name=plain_names[key], count=_whole(count)) for key, count in plain.items()]
    counts.sort(key=lambda dish: (-dish.count, dish.name))

    return FoodStats(
        groups=[
            GroupShare(group=group.value, amount=from_tiins(round(groups[group])))
            for group in sorted(SPENDING_GROUPS, key=lambda group: -groups[group])
            if groups[group] > 0
        ],
        top=[dish for dish in counts if dish.count > 0][:TOP_DISHES],
        champions=_champions(by_kind, kinds, counted, labels),
        price_rises=_price_rises(counted, labels, kinds, places),
        fees=from_tiins(round(groups[DishGroup.FEE])),
        labeled=round(labeled / len(had), 2) if had else 1.0,
    ), kind_counts


def _whole(count: float) -> int:
    """Dishes as people count them: a third of a pizza is still a pizza had."""
    return max(1, round(count)) if count > 0 else 0


def _lines_had(table: _Table) -> list[_Had]:
    """The lines the person had a part in. A dish given to particular people is
    theirs, portion by portion; with no dishes given to anyone, the person had
    everything in the share they pay."""
    if not table.mine:
        return []
    allocated = sum(seat.allocated_amount for seat in table.seats)
    my_part = table.mine.allocated_amount / allocated if allocated else 0
    anyone_assigned = bool(table.portions)
    had = []
    for item in table.items:
        portions = table.portions.get(item.id)
        if portions:
            mine = [sharing for sharing in portions.values() if table.mine.id in sharing]
            if mine:
                per_portion = item.item_sum / max(item.count, 1)
                had.append(_Had(
                    item,
                    table,
                    sum(per_portion / len(sharing) for sharing in mine),
                    sum(1 / len(sharing) for sharing in mine),
                ))
        elif item.is_shared_globally or not anyone_assigned:
            if my_part:
                had.append(_Had(item, table, item.item_sum * my_part, 0 if item.is_shared_globally else item.count * my_part))
    return had


def _champions(by_kind: dict[str, list[_Had]], kinds: dict[str, str], counted: list[_Table], labels: dict[str, DishLabel]) -> list[Champion]:
    """For the kinds the person has most: the variant they had most often, and
    the priciest one seen at their tables."""
    priciest: dict[str, BillItem] = {}
    for table in counted:
        for item in table.items:
            label = labels.get(dish_key(item.name))
            if label and label.kind in by_kind and item.price > 0:
                best = priciest.get(label.kind)
                if best is None or item.price > best.price:
                    priciest[label.kind] = item

    ranked = sorted(by_kind.items(), key=lambda pair: (-sum(line.count for line in pair[1]), pair[0]))
    champions = []
    for kind, lines in [pair for pair in ranked if pair[0] in priciest][:TOP_CHAMPIONS]:
        variants: Counter[str] = Counter()
        names: dict[str, str] = {}
        for line in lines:
            variants[dish_key(line.item.name)] += line.count
            names.setdefault(dish_key(line.item.name), line.item.name.strip())
        often_key, often_count = variants.most_common(1)[0]
        top = priciest[kind]
        champions.append(Champion(
            kind=kind,
            name=kinds[kind],
            often=names[often_key],
            often_count=_whole(often_count),
            priciest=top.name.strip(),
            priciest_price=from_tiins(top.price),
        ))
    return champions


def _price_rises(counted: list[_Table], labels: dict[str, DishLabel], kinds: dict[str, str], places: dict[int, str]) -> list[PriceRise]:
    """The same dish at the same place, dearer at the last visit than at the
    first. A visit is a bill: the dish written twice on one receipt is one price."""
    seen: dict[tuple[int, str], dict[int, tuple[datetime, int, str]]] = defaultdict(dict)
    for table in counted:
        if table.bill.place_id not in places:
            continue
        for item in table.items:
            label = labels.get(dish_key(item.name))
            if item.price > 0 and label and label.group != DishGroup.FEE:
                seen[(table.bill.place_id, dish_key(item.name))].setdefault(
                    table.bill.id, (table.bill.created_at, item.price, item.name.strip())
                )

    rises = []
    for (place_id, _), by_visit in seen.items():
        visits = sorted(by_visit.values())
        (since, first, name), (_, last, _) = visits[0], visits[-1]
        if len(visits) > 1 and last > first and (last - first) / first >= MIN_PRICE_RISE:
            rises.append(PriceRise(
                dish=name,
                place=places[place_id],
                first_price=from_tiins(first),
                last_price=from_tiins(last),
                change=round((last - first) / first * 100, 1),
                since=since.replace(tzinfo=timezone.utc),
            ))
    rises.sort(key=lambda rise: -rise.change)
    return rises[:TOP_PRICE_RISES]


# ── Badges ───────────────────────────────────────────────────────────────────

COFFEE_LOVER = 10
MEAT_LOVER = 8
REGULAR = 5
NIGHT_OWL = 5
TREASURER = 10
SOCIAL = 10
FAST_PAYER_MINUTES = 15
FAST_PAYER_PAYMENTS = 3


def _badges(
    overview: OverviewStats,
    people: PeopleStats,
    kind_counts: Counter[str],
    places: PlacesStats,
    my_waits: list[float],
) -> list[Badge]:
    """Small titles the period earned, each with the number that earned it."""
    badges = []
    coffee = sum(count for kind, count in kind_counts.items() if kind in COFFEE_KINDS)
    if coffee >= COFFEE_LOVER:
        badges.append(Badge(key="coffee_lover", value=coffee))
    meat = sum(count for kind, count in kind_counts.items() if kind in MEAT_KINDS)
    if meat >= MEAT_LOVER:
        badges.append(Badge(key="meat_lover", value=meat))
    if places.top and places.top[0].visits >= REGULAR:
        badges.append(Badge(key="regular", value=places.top[0].visits, subject=places.top[0].name))
    if overview.day_parts[3] >= NIGHT_OWL:
        badges.append(Badge(key="night_owl", value=overview.day_parts[3]))
    if overview.owned >= TREASURER:
        badges.append(Badge(key="treasurer", value=overview.owned))
    if people.distinct >= SOCIAL:
        badges.append(Badge(key="social", value=people.distinct))
    if len(my_waits) >= FAST_PAYER_PAYMENTS and median(my_waits) <= FAST_PAYER_MINUTES:
        badges.append(Badge(key="fast_payer", value=round(median(my_waits))))
    return badges


def _my_waits(tables: list[_Table], me: int) -> list[float]:
    """Minutes the person took to pay at other people's tables."""
    return [
        max(0.0, (table.mine.paid_at - max(table.bill.created_at, table.mine.claimed_at or table.bill.created_at)).total_seconds() / 60)
        for table in tables
        if table.owned_by != me and table.mine and table.mine.paid_at
    ]


# ── Shared ───────────────────────────────────────────────────────────────────

def _dominant_currency(tables: list[_Table]) -> tuple[str, int]:
    """The currency most bills were in, and how many were in another."""
    if not tables:
        return "uzs", 0
    counts = Counter(table.bill.currency for table in tables)
    currency = max(counts, key=lambda code: (counts[code], code == "uzs"))
    return currency, len(tables) - counts[currency]


def _local(moment: datetime, zone: ZoneInfo) -> datetime:
    return moment.replace(tzinfo=timezone.utc).astimezone(zone)
