"""The guided tour's demo bill: made from a fixture, seen by nobody but its owner."""
from fastapi.testclient import TestClient
from sqlmodel import select

from app.models import Bill, BillItem, BillUser, Invite, PaymentMethod, PaymentReminder, SharedBillMessage
from tests.conftest import auth_headers


def _user(client: TestClient, telegram_id: int) -> int:
    return client.post("/users/", json={"telegram_id": telegram_id, "username": f"u{telegram_id}"}).json()["id"]


def _create_demo(client: TestClient, telegram_id: int, language: str = "ru") -> dict:
    resp = client.post("/demo-bills/", json={"language": language}, headers=auth_headers(telegram_id))
    assert resp.status_code == 201
    return resp.json()


def test_the_demo_bill_looks_like_a_freshly_scanned_receipt(client: TestClient):
    owner = _user(client, 10)

    bill = _create_demo(client, 10, "ru")

    assert bill["owner_id"] == owner
    assert bill["title"] == "Ужин с друзьями"
    assert bill["currency"] == "uzs"
    assert bill["split_type"] == "by_items"
    assert [item["name"] for item in bill["items"]][:2] == ["Плов", "Шашлык из баранины"]
    assert bill["total_sum"] == bill["unallocated_sum"] == 123000
    assert bill["is_demo"] is True
    seats = bill["participants"]
    assert [seat["user_id"] for seat in seats] == [owner, None, None]


def test_the_receipt_reads_in_the_tours_language(client: TestClient):
    _user(client, 11)

    uzbek = _create_demo(client, 11, "uz")
    assert (uzbek["title"], uzbek["items"][0]["name"]) == ("Do'stlar bilan kechki ovqat", "Osh")

    unknown = _create_demo(client, 11, "fr")
    assert unknown["title"] == "Ужин с друзьями"


def test_a_demo_bill_stays_out_of_the_owners_bill_list(client: TestClient):
    owner = _user(client, 12)
    real = client.post("/bills/", json={"owner_id": owner, "total_sum": 100}).json()
    demo = _create_demo(client, 12)

    listed = client.get(f"/users/{owner}/bills").json()

    assert [bill["id"] for bill in listed] == [real["id"]]
    assert client.get(f"/bills/{demo['id']}?user_id={owner}").status_code == 200


def test_starting_the_tour_again_clears_the_bill_it_left_behind(client: TestClient, session):
    _user(client, 13)
    _create_demo(client, 13)

    fresh = _create_demo(client, 13)

    session.expire_all()
    demos = session.exec(select(Bill).where(Bill.is_demo.is_(True))).all()
    assert [bill.id for bill in demos] == [fresh["id"]]
    assert len(session.exec(select(BillItem)).all()) == len(fresh["items"])
    assert len(session.exec(select(BillUser)).all()) == len(fresh["participants"])


def test_the_invited_friends_sit_down_on_the_empty_seats(client: TestClient):
    _user(client, 14)
    demo = _create_demo(client, 14)

    resp = client.post(
        f"/demo-bills/{demo['id']}/friends", json={"language": "en"}, headers=auth_headers(14)
    )

    assert resp.status_code == 200
    guests = [seat for seat in resp.json()["participants"] if seat["user_id"] is None]
    assert [seat["guest_name"] for seat in guests] == ["Alisher", "Madina"]


def test_the_demo_bill_splits_and_closes_like_any_other(client: TestClient):
    owner = _user(client, 15)
    demo = _create_demo(client, 15)
    bill = client.post(
        f"/demo-bills/{demo['id']}/friends", json={"language": "ru"}, headers=auth_headers(15)
    ).json()
    alisher = next(seat for seat in bill["participants"] if seat["guest_name"] == "Алишер")
    plov, kebab = bill["items"][0], bill["items"][1]

    assigned = client.post(
        f"/bills/{demo['id']}/items/assign-batch?requester_id={owner}",
        json={"ops": [
            {"item_id": plov["id"], "participant_id": alisher["id"], "is_assigned": True},
            {"item_id": kebab["id"], "participant_id": alisher["id"], "is_assigned": True},
        ]},
    ).json()
    assert next(p for p in assigned["participants"] if p["id"] == alisher["id"])["allocated_amount"] == 87000
    assert assigned["unallocated_sum"] == 36000

    everyone = [seat["id"] for seat in assigned["participants"]]
    client.post(f"/bills/{demo['id']}/split-remainder", json={"participant_ids": everyone})
    closed = client.post(f"/bills/{demo['id']}/close", json={"user_id": owner}).json()
    assert closed["status"] == "closed"
    assert closed["unallocated_sum"] == 0


def test_erasing_the_demo_bill_leaves_nothing_behind(client: TestClient, session):
    _user(client, 16)
    demo = _create_demo(client, 16)

    assert client.delete(f"/demo-bills/{demo['id']}", headers=auth_headers(16)).status_code == 204

    session.expire_all()
    assert session.get(Bill, demo["id"]) is None
    assert session.exec(select(BillUser).where(BillUser.bill_id == demo["id"])).all() == []
    assert session.exec(select(BillItem).where(BillItem.bill_id == demo["id"])).all() == []


def test_erasing_takes_what_sharing_left_behind(client: TestClient, session):
    """A demo bill opened outside the tour can still be shared; that must not
    make it impossible to erase — or to start the tour again."""
    owner = _user(client, 19)
    demo = _create_demo(client, 19)
    seat = next(p for p in demo["participants"] if p["user_id"] is None)
    session.add(Invite(bill_id=demo["id"], inviter_user_id=owner, seat_participant_id=seat["id"]))
    session.add(SharedBillMessage(bill_id=demo["id"], invite_code="c0de", language="ru"))
    session.add(PaymentReminder(bill_id=demo["id"], participant_id=seat["id"]))
    session.commit()

    _create_demo(client, 19)

    session.expire_all()
    assert len(session.exec(select(Bill).where(Bill.is_demo.is_(True))).all()) == 1
    assert session.exec(select(Invite)).all() == []
    assert session.exec(select(SharedBillMessage)).all() == []
    assert session.exec(select(PaymentReminder)).all() == []


def test_the_card_typed_in_the_tour_stays_on_the_demo_bill(client: TestClient, session):
    owner = _user(client, 21)

    bill = client.post(
        "/demo-bills/", json={"language": "ru", "payment_details": "8600 1234 5678 9010"},
        headers=auth_headers(21),
    ).json()

    assert bill["payment_details"] == "8600 1234 5678 9010"
    assert client.get(f"/users/{owner}/payment-methods/").json() == []

    client.delete(f"/demo-bills/{bill['id']}", headers=auth_headers(21))
    session.expire_all()
    assert session.exec(select(PaymentMethod)).all() == []


def test_a_real_bill_says_it_is_not_a_demo(client: TestClient):
    owner = _user(client, 20)
    real = client.post("/bills/", json={"owner_id": owner, "total_sum": 100}).json()

    assert client.get(f"/bills/{real['id']}?user_id={owner}").json()["is_demo"] is False


def test_demo_routes_never_touch_a_real_bill_or_someone_elses_demo(client: TestClient, session):
    owner = _user(client, 17)
    _user(client, 18)
    real = client.post("/bills/", json={"owner_id": owner, "total_sum": 100}).json()
    theirs = _create_demo(client, 18)

    assert client.delete(f"/demo-bills/{real['id']}", headers=auth_headers(17)).status_code == 404
    assert client.delete(f"/demo-bills/{theirs['id']}", headers=auth_headers(17)).status_code == 404
    assert client.post(
        f"/demo-bills/{theirs['id']}/friends", json={}, headers=auth_headers(17)
    ).status_code == 404

    session.expire_all()
    assert session.get(Bill, real["id"]) is not None
    assert session.get(Bill, theirs["id"]) is not None


def test_only_a_signed_in_person_gets_a_demo_bill(client: TestClient):
    assert client.post("/demo-bills/", json={}, headers={"X-Telegram-Init-Data": ""}).status_code == 401
