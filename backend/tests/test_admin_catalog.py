"""The admin's view of what analytics count by: places and dish labels.

The wordings are Latin here: SQLite lowercases only ASCII, Postgres all of it."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Bill, BillItem, BillUser, DishKind, DishLabel, Place, User


@pytest.fixture
def admin(client: TestClient, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret")
    from app.routers import admin as admin_router

    admin_router._LOGIN_ATTEMPTS.clear()
    assert client.post("/admin/auth/login", json={"email": "boss@example.com", "password": "s3cret"}).status_code == 200
    return client


@pytest.fixture
def world(session: Session):
    leo, ann = User(telegram_id=1, name="Leo"), User(telegram_id=2, name="Ann")
    caffeine, bar = Place(name="Caffeine", name_key="caffeine"), Place(name="Bar", name_key="bar")
    session.add_all([leo, ann, caffeine, bar])
    session.commit()
    start = datetime(2026, 9, 1)
    bills = [
        Bill(owner_id=leo.id, place_id=caffeine.id, created_at=start),
        Bill(owner_id=ann.id, place_id=caffeine.id, created_at=start + timedelta(days=5)),
        Bill(owner_id=leo.id, place_id=bar.id, created_at=start + timedelta(days=9)),
        Bill(owner_id=leo.id, place_id=bar.id, deleted_at=start, created_at=start),
    ]
    session.add_all(bills)
    session.commit()
    session.add_all([
        BillUser(bill_id=bills[0].id, user_id=leo.id, seat_index=0),
        BillUser(bill_id=bills[0].id, user_id=ann.id, seat_index=1),
        BillUser(bill_id=bills[1].id, user_id=ann.id, seat_index=0),
        BillItem(bill_id=bills[0].id, name="Cappuccino ", price=1, item_sum=1),
        BillItem(bill_id=bills[1].id, name="cappuccino", price=1, item_sum=1),
        BillItem(bill_id=bills[2].id, name="Beer", price=1, item_sum=1),
        BillItem(bill_id=bills[3].id, name="Beer", price=1, item_sum=1),
        DishKind(key="cappuccino", ru="Капучино", uz="Kapuchino", en="Cappuccino"),
        DishKind(key="beer", ru="Пиво", uz="Pivo", en="Beer"),
        DishLabel(name_key="cappuccino", group="drink", kind="cappuccino", model="gpt"),
        DishLabel(name_key="beer", group="drink", kind=None, model="gpt"),
    ])
    session.commit()


def test_places_come_with_their_bills_people_and_dates(admin: TestClient, world):
    body = admin.get("/admin/places").json()

    assert body["total"] == 2
    caffeine, bar = body["items"]
    assert (caffeine["name"], caffeine["bills"], caffeine["people"]) == ("Caffeine", 2, 2)
    assert (caffeine["first_bill_at"], caffeine["last_bill_at"]) == ("2026-09-01T00:00:00", "2026-09-06T00:00:00")
    # The deleted bill does not count.
    assert (bar["bills"], bar["people"]) == (1, 0)
    assert [place["name"] for place in admin.get("/admin/places", params={"q": "BAR"}).json()["items"]] == ["Bar"]


def test_dishes_are_listed_by_how_often_receipts_have_them_and_filtered(admin: TestClient, world):
    items = admin.get("/admin/dishes").json()["items"]

    # The beer on the deleted bill does not count.
    assert [(dish["name_key"], dish["lines"], dish["kind_name"]) for dish in items] == [
        ("cappuccino", 2, "Капучино"), ("beer", 1, None),
    ]
    assert [dish["name_key"] for dish in admin.get("/admin/dishes", params={"kind": "cappuccino"}).json()["items"]] == ["cappuccino"]
    assert admin.get("/admin/dishes", params={"group": "food"}).json()["total"] == 0
    assert admin.get("/admin/dishes", params={"q": "BEE"}).json()["total"] == 1


def test_a_corrected_label_is_marked_as_the_admins(admin: TestClient, world, session: Session):
    fixed = admin.patch("/admin/dishes", json={"name_key": "Beer", "group": "alcohol", "kind": "beer"}).json()

    assert (fixed["group"], fixed["kind"], fixed["kind_name"], fixed["model"], fixed["lines"]) == ("alcohol", "beer", "Пиво", "admin", 1)
    assert session.get(DishLabel, "beer").group == "alcohol"
    assert admin.patch("/admin/dishes", json={"name_key": "beer", "group": "snacks"}).status_code == 400
    assert admin.patch("/admin/dishes", json={"name_key": "beer", "group": "food", "kind": "nope"}).status_code == 400
    assert admin.patch("/admin/dishes", json={"name_key": "tea", "group": "drink"}).status_code == 404


def test_a_new_kind_is_named_in_every_language(admin: TestClient, world):
    made = admin.post("/admin/dish-kinds", json={"key": "Lagman", "ru": "Лагман", "uz": "Lag‘mon", "en": "Lagman"})

    assert made.status_code == 201 and made.json()["key"] == "lagman"
    assert "lagman" in [kind["key"] for kind in admin.get("/admin/dish-kinds").json()]
    assert admin.post("/admin/dish-kinds", json={"key": "lagman", "ru": "a", "uz": "b", "en": "c"}).status_code == 409
    assert admin.post("/admin/dish-kinds", json={"key": "soup", "ru": "", "uz": "b", "en": "c"}).status_code == 400
