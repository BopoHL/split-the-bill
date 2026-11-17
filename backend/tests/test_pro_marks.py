"""Where Pro shows on a bill: a badge by each name that has it, and a mark on
the picture of a bill kept by someone with it."""
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Bill, ProSource
from app.services.bill_summary import summary_for
from app.services.share_message import fingerprint
from tests.pro_world import NOW, grant


def test_participants_say_who_has_pro(client: TestClient, session: Session, people):
    leo, ann = people
    grant(session, ann, ProSource.PROMO, NOW - timedelta(days=400), 1000)
    client.act_as(leo.telegram_id)
    bill = client.post("/bills/", json={"owner_id": leo.id, "total_sum": 0, "include_owner": True, "expected_people": 2}).json()
    seats = client.get(f"/bills/{bill['id']}").json()["participants"]
    free = next(seat for seat in seats if seat["user_id"] is None)
    client.act_as(ann.telegram_id)
    client.post(f"/bills/{bill['id']}/seats/{free['id']}/claim", json={"user_id": ann.id})

    participants = client.get(f"/bills/{bill['id']}").json()["participants"]

    assert {seat["user_id"]: seat["badge"] for seat in participants} == {leo.id: None, ann.id: "pro"}


def test_the_picture_of_a_pro_bill_is_a_new_picture(session: Session, people):
    leo, _ = people
    bill = Bill(owner_id=leo.id, total_sum=0, title="Ужин")
    session.add(bill)
    session.commit()
    before = summary_for(session, bill)

    grant(session, leo, ProSource.PROMO, NOW - timedelta(days=400), 1000)
    after = summary_for(session, bill)

    assert (before.pro, after.pro) == (False, True)
    assert fingerprint(before, "ru") != fingerprint(after, "ru")
