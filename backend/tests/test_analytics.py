"""Analytics from the person's side: their share, the dishes they had, the people
at their tables and the places they went — for a month, a year or all time."""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Bill, BillItem, BillItemAssignment, BillUser, User
from app.services.analytics import AnalyticsService, Period, PeriodKind
from tests.analytics_world import NOW

def _september(session: Session, world):
    return AnalyticsService(session).for_user(world["me"], Period(PeriodKind.MONTH, 2026, 9), NOW)


def test_the_overview_counts_my_share_in_the_main_currency(session: Session, world):
    overview = (stats := _september(session, world)).overview

    assert (stats.currency, stats.other_currency_bills) == ("uzs", 1)
    assert (overview.bills, overview.owned, overview.joined) == (3, 1, 2)
    assert overview.spent == 145_000
    assert overview.spent_change == 45.0
    assert (overview.average_bill, overview.average_share) == (195_000, 72_500)
    assert (overview.biggest.id, overview.biggest.share, overview.biggest.people) == (world["dinner"].id, 100_000, 3)
    assert overview.smallest.id == world["coffee"].id
    assert (overview.collected, overview.transferred) == (120_000, 45_000)


def test_the_month_is_told_day_by_day_and_by_the_clock_in_tashkent(session: Session, world):
    overview = _september(session, world).overview

    assert len(overview.timeline) == 30
    by_day = {point.key: point for point in overview.timeline}
    assert by_day["2026-09-05"].amount == 100_000
    assert (by_day["2026-09-10"].amount, by_day["2026-09-10"].bills) == (0, 1)
    assert overview.weekdays == [0, 0, 0, 1, 0, 1, 1]
    assert overview.day_parts == [0, 1, 2, 0]


def test_people_at_my_tables_and_at_theirs(session: Session, world):
    people = _september(session, world).people

    alice, bob = people.companions
    assert (alice.name, alice.together, alice.invited, alice.invited_me) == ("Alice", 2, 1, 1)
    assert (alice.paid_me, alice.paid_them) == (120_000, 45_000)
    assert (bob.name, bob.together, bob.invited, bob.invited_me) == ("Bob", 2, 1, 1)
    assert [(speed.name, speed.minutes) for speed in people.speed] == [("Alice", 12)]
    assert people.distinct == 2


def test_dishes_are_the_ones_i_had(session: Session, world):
    food = _september(session, world).food

    assert [(group.group, group.amount) for group in food.groups] == [("food", 77_000), ("drink", 33_000), ("fee", 10_000)]
    # A shared portion is part of one: half a cappuccino here, half there.
    assert [(dish.name, dish.count) for dish in food.top] == [("Бургер", 2), ("Капучино", 1)]
    burger, cappuccino = food.champions
    assert (burger.name, burger.often, burger.priciest, burger.priciest_price) == ("Бургер", "Burger Double", "Burger Black Angus", 54_000)
    assert (cappuccino.often, cappuccino.often_count) == ("Cappuccino", 1)
    assert [(rise.dish, rise.place, rise.change) for rise in food.price_rises] == [("Cappuccino", "Caffeine", 20.0)]
    assert (food.fees, food.labeled) == (10_000, 1.0)


def test_places_and_the_new_ones(session: Session, world):
    places = _september(session, world).places

    assert [(place.name, place.visits, place.spent, place.average_bill) for place in places.top] == [("Caffeine", 2, 145_000, 195_000)]
    assert places.new == ["Caffeine"]
    assert places.unplaced == 0


def test_a_year_and_all_time(session: Session, world):
    service = AnalyticsService(session)

    year = service.for_user(world["me"], Period(PeriodKind.YEAR, 2026), NOW)
    assert year.overview.bills == 4
    assert [point.key for point in year.overview.timeline][-1] == "2026-10"
    assert year.places.unplaced == 1

    ever = service.for_user(world["me"], Period(PeriodKind.ALL), NOW)
    assert [point.key for point in ever.overview.timeline] == ["2026-08", "2026-09", "2026-10"]
    assert (ever.period.first_year, ever.period.first_month) == (2026, 8)
    assert ever.overview.spent_change is None


def test_nothing_yet(session: Session):
    newcomer = User(telegram_id=9, username="new")
    session.add(newcomer)
    session.commit()

    stats = AnalyticsService(session).for_user(newcomer, Period(PeriodKind.MONTH, 2026, 10), NOW)

    assert stats.overview.bills == 0 and stats.overview.biggest is None
    assert stats.people.companions == [] and stats.food.top == [] and stats.places.top == []


def test_only_i_see_my_analytics(client: TestClient, session: Session, world):
    client.act_as(2)
    assert client.get(f"/users/{world['me'].id}/analytics").status_code == 403
    client.act_as(1)
    response = client.get(f"/users/{world['me'].id}/analytics", params={"period": "month", "year": 2026, "month": 9})
    client.act_as(None)

    assert response.status_code == 200
    assert response.json()["overview"]["spent"] == 145_000
    assert response.json()["locked"] is False


def test_without_pro_only_the_top_of_the_overview_comes(client: TestClient, session: Session, world):
    client.act_as(world["alice"].telegram_id)
    body = client.get(f"/users/{world['alice'].id}/analytics", params={"period": "month", "year": 2026, "month": 9}).json()

    assert body["locked"] is True
    assert (body["overview"]["bills"], body["overview"]["spent"]) == (2, 165_000)
    assert len(body["overview"]["timeline"]) == 30
    assert body["overview"]["biggest"] is None and body["overview"]["weekdays"] == [0] * 7
    assert (body["people"]["companions"], body["food"]["top"], body["places"]["top"], body["badges"]) == ([], [], [], [])


def test_badges_come_from_the_numbers(session: Session, world, monkeypatch):
    import app.services.analytics as analytics

    monkeypatch.setattr(analytics, "REGULAR", 2)
    monkeypatch.setattr(analytics, "COFFEE_LOVER", 1)
    monkeypatch.setattr(analytics, "FAST_PAYER_PAYMENTS", 1)
    monkeypatch.setattr(analytics, "FAST_PAYER_MINUTES", 60)

    badges = {badge.key: (badge.value, badge.subject) for badge in _september(session, world).badges}

    assert badges == {"coffee_lover": (1, None), "regular": (2, "Caffeine"), "fast_payer": (60, None)}


def _july_dinner(session: Session, world, *lines: tuple[str, int, int]) -> Bill:
    """A July dinner at Caffeine for me, Alice and Bob, each line one portion
    the three of us shared."""
    dinner = Bill(owner_id=world["me"].id, total_sum=0, created_at=datetime(2026, 7, 10, 14, 0),
                  place_id=world["dinner"].place_id)
    session.add(dinner)
    session.commit()
    seats = [BillUser(bill_id=dinner.id, user_id=user.id, allocated_amount=10_000 * 100, seat_index=index)
             for index, user in enumerate((world["me"], world["alice"], world["bob"]))]
    session.add_all(seats)
    session.commit()
    for name, price, count in lines:
        line = BillItem(bill_id=dinner.id, name=name, price=price * 100, count=count, item_sum=price * count * 100)
        session.add(line)
        session.commit()
        session.add_all([BillItemAssignment(bill_item_id=line.id, participant_id=seat.id, portion_index=0) for seat in seats])
    session.commit()
    return dinner


def test_a_month_under_way_is_set_against_the_same_days_of_the_last_one(session: Session, world):
    october = Bill(owner_id=world["me"].id, total_sum=50_000 * 100, created_at=datetime(2026, 10, 2, 12, 0))
    session.add(october)
    session.commit()
    session.add(BillUser(bill_id=october.id, user_id=world["me"].id, allocated_amount=50_000 * 100, seat_index=0))
    session.commit()

    sixth = datetime(2026, 10, 6, 9, 0)
    overview = AnalyticsService(session).for_user(world["me"], Period(PeriodKind.MONTH, 2026, 10), sixth).overview

    # The first six days of September had the dinner, not Alice's coffee on the 20th.
    assert (overview.spent, overview.spent_change) == (50_000, -50.0)


def test_a_dish_shared_by_three_is_still_a_dish_had(session: Session, world):
    _july_dinner(session, world, ("Burger Double", 60_000, 1))

    food = AnalyticsService(session).for_user(world["me"], Period(PeriodKind.MONTH, 2026, 7), NOW).food

    assert [(dish.name, dish.count) for dish in food.top] == [("Бургер", 1)]


def test_a_dish_written_twice_on_one_receipt_is_not_a_price_rise(session: Session, world):
    _july_dinner(session, world, ("Cappuccino", 30_000, 1), ("Cappuccino", 40_000, 1))

    food = AnalyticsService(session).for_user(world["me"], Period(PeriodKind.MONTH, 2026, 7), NOW).food

    assert food.price_rises == []
