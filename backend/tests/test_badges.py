"""The badge by someone's name: picked from what they have, Pro by default."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import Bill, BillUser, ProSource
from app.services.badges import shown_badge
from tests.pro_world import grant


def _keep_ten_bills(session: Session, owner) -> None:
    # At lunch in Tashkent: bills made at the hour the suite runs could earn
    # «Night owl» too.
    lunch = datetime(2026, 10, 1, 7, 0)
    bills = [Bill(owner_id=owner.id, title=f"Ужин {index}", created_at=lunch) for index in range(10)]
    session.add_all(bills)
    session.commit()
    session.add_all([BillUser(bill_id=bill.id, user_id=owner.id, seat_index=0) for bill in bills])
    session.commit()


def test_pro_shows_by_itself_until_something_else_is_picked():
    assert shown_badge(None, pro=True) == "pro"
    assert shown_badge(None, pro=False) is None
    assert shown_badge("pro", pro=False) is None
    assert shown_badge("none", pro=True) is None
    assert shown_badge("treasurer", pro=False) == "treasurer"


def test_a_title_earned_over_all_bills_can_be_picked(client: TestClient, session: Session, people):
    leo, _ = people
    client.act_as(leo.telegram_id)
    assert client.get(f"/users/{leo.id}/badges").json() == {"chosen": None, "shown": None, "available": []}
    assert client.put(f"/users/{leo.id}/badge", json={"badge": "treasurer"}).status_code == 400

    _keep_ten_bills(session, leo)
    grant(session, leo, ProSource.PROMO, datetime.utcnow() - timedelta(days=1), 30)
    offered = client.get(f"/users/{leo.id}/badges").json()
    assert offered["shown"] == "pro"
    assert [badge["key"] for badge in offered["available"]] == ["pro", "treasurer"]

    picked = client.put(f"/users/{leo.id}/badge", json={"badge": "treasurer"}).json()
    assert (picked["chosen"], picked["shown"]) == ("treasurer", "treasurer")
    assert client.put(f"/users/{leo.id}/badge", json={"badge": "none"}).json()["shown"] is None
    assert client.put(f"/users/{leo.id}/badge", json={"badge": None}).json() | {"available": []} == {
        "chosen": None, "shown": "pro", "available": [],
    }


def test_a_title_the_numbers_moved_on_from_stays_while_it_is_shown(client: TestClient, session: Session, people):
    leo, _ = people
    _keep_ten_bills(session, leo)
    client.act_as(leo.telegram_id)
    client.put(f"/users/{leo.id}/badge", json={"badge": "treasurer"})
    for bill in session.exec(select(Bill).where(Bill.owner_id == leo.id)).all()[:5]:
        bill.deleted_at = datetime.utcnow()
        session.add(bill)
    session.commit()

    kept = client.get(f"/users/{leo.id}/badges").json()

    assert kept["shown"] == "treasurer"
    assert kept["available"] == [{"key": "treasurer", "value": None, "subject": None}]
    assert client.put(f"/users/{leo.id}/badge", json={"badge": "treasurer"}).status_code == 200
    client.put(f"/users/{leo.id}/badge", json={"badge": "none"})
    assert client.get(f"/users/{leo.id}/badges").json()["available"] == []


def test_everyone_at_the_bill_sees_each_others_badges(client: TestClient, session: Session, people):
    leo, ann = people
    _keep_ten_bills(session, ann)
    grant(session, leo, ProSource.PROMO, datetime.utcnow() - timedelta(days=1), 30)
    client.act_as(ann.telegram_id)
    client.put(f"/users/{ann.id}/badge", json={"badge": "treasurer"})

    client.act_as(leo.telegram_id)
    bill = client.post("/bills/", json={"owner_id": leo.id, "total_sum": 0, "include_owner": True, "expected_people": 2}).json()
    free = next(seat for seat in client.get(f"/bills/{bill['id']}").json()["participants"] if seat["user_id"] is None)
    client.act_as(ann.telegram_id)
    client.post(f"/bills/{bill['id']}/seats/{free['id']}/claim", json={"user_id": ann.id})

    seats = client.get(f"/bills/{bill['id']}").json()["participants"]
    assert {seat["user_id"]: seat["badge"] for seat in seats} == {leo.id: "pro", ann.id: "treasurer"}
