"""The analytics test world: three people, a café, a few labelled dishes and
four bills across August and September 2026, one of them in dollars. The
first of them has Pro."""
from collections import Counter
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session

from app.models import (
    Bill,
    BillItem,
    BillItemAssignment,
    BillUser,
    DishKind,
    DishLabel,
    Place,
    ProGrant,
    User,
)

NOW = datetime(2026, 10, 3, 9, 0)
SUM = 100  # tiins in a sum


@pytest.fixture
def world(session: Session):
    me = User(telegram_id=1, username="leo", name="Leonid", settings={"language": "ru"})
    alice = User(telegram_id=2, username="alice", name="Alice")
    bob = User(telegram_id=3, username="bob", name="Bob")
    session.add_all([me, alice, bob])
    session.commit()
    caffeine = Place(name="Caffeine", name_key="caffeine")
    session.add(caffeine)
    session.add_all([
        DishLabel(name_key="burger double", group="food", kind="burger"),
        DishLabel(name_key="burger black angus", group="food", kind="burger"),
        DishLabel(name_key="cappuccino", group="drink", kind="cappuccino"),
        DishLabel(name_key="обслуживание", group="fee", kind=None),
        DishKind(key="burger", ru="Бургер", uz="Burger", en="Burger"),
        DishKind(key="cappuccino", ru="Капучино", uz="Kapuchino", en="Cappuccino"),
    ])
    session.commit()

    def bill(owner, at, total, place=None, currency="uzs"):
        row = Bill(owner_id=owner.id, total_sum=total * SUM, created_at=at, place_id=place.id if place else None, currency=currency)
        session.add(row)
        session.commit()
        return row

    taken_seats = Counter()

    def seat(row, user, amount, paid_after=None):
        taken = BillUser(
            bill_id=row.id, user_id=user.id, allocated_amount=amount * SUM, claimed_at=row.created_at,
            is_paid=paid_after is not None, paid_at=row.created_at + paid_after if paid_after else None,
            seat_index=taken_seats[row.id],
        )
        taken_seats[row.id] += 1
        session.add(taken)
        session.commit()
        return taken

    def item(row, name, price, count=1, shared=False):
        line = BillItem(bill_id=row.id, name=name, price=price * SUM, count=count, item_sum=price * count * SUM, is_shared_globally=shared)
        session.add(line)
        session.commit()
        return line

    def give(line, portion, *seats):
        for taken in seats:
            session.add(BillItemAssignment(bill_item_id=line.id, participant_id=taken.id, portion_index=portion))
        session.commit()

    # September: my dinner at Caffeine — Alice pays in 12 minutes, Bob not yet.
    dinner = bill(me, datetime(2026, 9, 5, 14, 30), 300_000, caffeine)
    mine = seat(dinner, me, 100_000)
    alices = seat(dinner, alice, 120_000, paid_after=timedelta(minutes=12))
    seat(dinner, bob, 80_000)
    burgers = item(dinner, "Burger Double", 50_000, count=2)
    give(burgers, 0, mine)
    give(burgers, 1, alices)
    give(item(dinner, "Cappuccino", 30_000), 0, mine, alices)
    item(dinner, "Обслуживание", 30_000, shared=True)

    # Alice's coffee at Caffeine, no dishes given to anyone; I paid my half.
    coffee = bill(alice, datetime(2026, 9, 20, 10, 0), 90_000, caffeine)
    seat(coffee, alice, 45_000)
    seat(coffee, me, 45_000, paid_after=timedelta(hours=1))
    item(coffee, "Cappuccino", 36_000)
    item(coffee, "Burger Black Angus", 54_000)

    # Bob's bill in dollars, an evening in September.
    dollars = bill(bob, datetime(2026, 9, 10, 16, 0), 40, currency="usd")
    seat(dollars, bob, 20)
    seat(dollars, me, 20)

    # August: one of mine, nowhere in particular.
    august = bill(me, datetime(2026, 8, 10, 12, 0), 200_000)
    seat(august, me, 100_000)

    # I have Pro, for as long as these tests run; Alice and Bob do not.
    session.add(ProGrant(user_id=me.id, source="promo", starts_at=datetime(2026, 1, 1), ends_at=datetime(2100, 1, 1)))
    session.commit()
    return {"me": me, "alice": alice, "bob": bob, "dinner": dinner, "coffee": coffee}
