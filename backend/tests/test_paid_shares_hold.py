"""A share somebody has paid stays as it was, whatever the owner does next:
deleting a receipt, closing, setting amounts by hand, changing the table, a
cheaper line — and a paid seat is not stood up from. Each of these used to
move a paid share, or leave the bill owing more than it costs."""
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import BillItem, ReceiptTask, ReceiptTaskStatus
from tests.conftest import auth_headers

OWNER, GUEST = 7100, 7101


def _table(client: TestClient, people: int = 3, price: int = 300):
    """The owner, a guest who claimed seat 1, an empty seat 2, and Plov."""
    owner = client.post("/users/", json={"telegram_id": OWNER, "username": "owner"}).json()["id"]
    guest = client.post("/users/", json={"telegram_id": GUEST, "username": "guest"}).json()["id"]
    bill = client.post(
        "/bills/", json={"owner_id": owner, "total_sum": 0, "include_owner": True, "expected_people": people},
    ).json()
    plov = client.post(f"/bills/{bill['id']}/items", json={"name": "Plov", "price": price, "count": 1}).json()
    seats = client.get(f"/bills/{bill['id']}?user_id={owner}").json()["participants"]
    client.post(f"/bills/{bill['id']}/seats/{seats[1]['id']}/claim", json={"user_id": guest})
    return owner, guest, bill["id"], plov, [seat["id"] for seat in seats]


def _pay(client: TestClient, bill_id: int, seat_id: int, guest: int):
    paid = client.post(f"/bills/{bill_id}/participants/{seat_id}/payment", json={"is_paid": True, "user_id": guest})
    assert paid.status_code == 200, paid.json()


def _shares(client: TestClient, bill_id: int, owner: int) -> dict[int, float]:
    return {seat["id"]: seat["allocated_amount"] for seat in client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]}


def _by_hand(client: TestClient, bill_id: int, seat_id: int, amount: float):
    assert client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": seat_id, "allocated_amount": amount}).status_code == 200


def test_deleting_a_receipt_does_not_take_dishes_off_a_paid_plate(client: TestClient, session: Session):
    owner, guest, bill_id, _plov, seats = _table(client)
    task = ReceiptTask(user_id=owner, bill_id=bill_id, status=ReceiptTaskStatus.COMPLETED, filename="r.jpg")
    session.add(task)
    session.commit()
    pizza = BillItem(bill_id=bill_id, name="Pizza", price=10000, count=1, item_sum=10000, receipt_task_id=task.id)
    session.add(pizza)
    session.commit()
    client.post(f"/bills/{bill_id}/items/{pizza.id}/assign", json={"participant_id": seats[1], "is_assigned": True}, headers=auth_headers(GUEST))
    _pay(client, bill_id, seats[1], guest)

    refused = client.delete(f"/bills/{bill_id}/receipts/{task.id}?user_id={owner}&items=delete")

    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"
    assert _shares(client, bill_id, owner)[seats[1]] == 100
    assert any(item["name"] == "Pizza" for item in client.get(f"/bills/{bill_id}?user_id={owner}").json()["items"])


def test_closing_a_bill_split_by_hand_shares_out_the_rest_as_money(client: TestClient):
    owner, guest, bill_id, _plov, seats = _table(client, people=2)
    _by_hand(client, bill_id, seats[1], 100)
    _pay(client, bill_id, seats[1], guest)

    closed = client.post(f"/bills/{bill_id}/close", json={"user_id": owner, "remainder": "me"})

    assert closed.status_code == 200, closed.json()
    shares = {seat["id"]: seat["allocated_amount"] for seat in closed.json()["participants"]}
    assert (shares[seats[0]], shares[seats[1]]) == (200, 100)


def test_a_paid_guest_keeps_the_sum_set_for_them_by_hand(client: TestClient):
    owner, guest, bill_id, _plov, seats = _table(client)
    _by_hand(client, bill_id, seats[1], 100)
    _pay(client, bill_id, seats[1], guest)

    moved = client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": seats[1], "allocated_amount": 50})
    onto_paid = client.post(f"/bills/{bill_id}/split-remainder", json={"participant_ids": [seats[1]]})

    assert moved.status_code == 409 and onto_paid.status_code == 409
    assert _shares(client, bill_id, owner)[seats[1]] == 100


def test_a_seat_holding_money_is_not_dropped_with_the_headcount(client: TestClient):
    owner, _guest, bill_id, _plov, seats = _table(client)
    _by_hand(client, bill_id, seats[2], 100)

    shrunk = client.patch(f"/bills/{bill_id}", json={"user_id": owner, "expected_people": 2})

    assert shrunk.status_code == 409 and shrunk.json()["detail"]["code"] == "SEATS_IN_USE"
    assert len(client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]) == 3


def test_a_cheaper_line_cannot_leave_a_paid_share_above_the_bill(client: TestClient):
    owner, guest, bill_id, plov, seats = _table(client, people=2)
    _by_hand(client, bill_id, seats[1], 150)
    _pay(client, bill_id, seats[1], guest)

    cheaper = client.patch(f"/bills/{bill_id}/items/{plov['id']}", json={"price": 100})

    assert cheaper.status_code == 409 and cheaper.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"
    assert client.get(f"/bills/{bill_id}?user_id={owner}").json()["total_sum"] == 300


def test_a_paid_seat_is_not_stood_up_from(client: TestClient):
    owner, guest, bill_id, plov, seats = _table(client)
    client.post(f"/bills/{bill_id}/items/{plov['id']}/assign", json={"participant_id": seats[1], "is_assigned": True}, headers=auth_headers(GUEST))
    # Someone still owes, so the bill stays open.
    tea = client.post(f"/bills/{bill_id}/items", json={"name": "Tea", "price": 10, "count": 1}).json()
    client.post(
        f"/bills/{bill_id}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": tea["id"], "participant_id": seats[2], "is_assigned": True}]},
    )
    _pay(client, bill_id, seats[1], guest)

    left = client.request("DELETE", f"/bills/{bill_id}/participants/{seats[1]}", json={"user_id": guest}, headers=auth_headers(GUEST))

    assert (left.status_code, left.json()["detail"]) == (409, "SEAT_PAID")
    seat = next(s for s in client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"] if s["id"] == seats[1])
    assert (seat["user_id"], seat["is_paid"]) == (guest, True)


def test_a_seat_that_owes_nothing_is_no_one_to_wait_for(client: TestClient):
    owner, guest, bill_id, plov, seats = _table(client)
    client.post(f"/bills/{bill_id}/items/{plov['id']}/assign", json={"participant_id": seats[1], "is_assigned": True}, headers=auth_headers(GUEST))
    _pay(client, bill_id, seats[1], guest)

    listed = next(b for b in client.get(f"/users/{owner}/bills").json() if b["id"] == bill_id)

    # Seat 2 owes nothing: «1 of 1 paid», not «1 of 2».
    assert (listed["payers_paid"], listed["payers_count"]) == (1, 1)
