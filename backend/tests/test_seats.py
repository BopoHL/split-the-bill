"""Ephemeral guests: a bill is laid out with a seat per expected person.

Dishes can be put on a seat before anyone claims it, which is the whole reason
assignments point at participants rather than user accounts.
"""
from fastapi.testclient import TestClient

from app.models import Bill, BillStatus
from tests.conftest import auth_headers


def _bill(client: TestClient, expected=3, tg=500):
    owner = client.post("/users/", json={"telegram_id": tg, "username": "owner"}).json()["id"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner, "total_sum": 0, "title": "Dinner",
            "include_owner": True, "expected_people": expected,
        },
    ).json()
    return owner, bill


def _seats(client, bill_id, viewer):
    return sorted(
        client.get(f"/bills/{bill_id}?user_id={viewer}").json()["participants"],
        key=lambda p: p["seat_index"],
    )


def test_creating_a_bill_lays_the_whole_table(client: TestClient):
    owner, bill = _bill(client, expected=4)
    seats = _seats(client, bill["id"], owner)

    assert [s["seat_index"] for s in seats] == [0, 1, 2, 3]
    assert seats[0]["user_id"] == owner and seats[0]["is_guest"] is False
    assert all(s["is_guest"] for s in seats[1:])
    assert all(s["guest_name"] is None for s in seats[1:])


def test_dishes_can_be_assigned_to_an_unclaimed_guest(client: TestClient):
    owner, bill = _bill(client, expected=3, tg=501)
    bid = bill["id"]
    item = client.post(f"/bills/{bid}/items", json={"name": "Plov", "price": 60, "count": 1}).json()
    guest = _seats(client, bid, owner)[1]

    resp = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": item["id"], "participant_id": guest["id"], "is_assigned": True}]},
    )
    assert resp.status_code == 200
    updated = next(p for p in resp.json()["participants"] if p["id"] == guest["id"])
    assert updated["allocated_amount"] == 60


def test_owner_renames_a_guest_but_not_a_real_participant(client: TestClient):
    owner, bill = _bill(client, expected=2, tg=502)
    bid = bill["id"]
    seats = _seats(client, bid, owner)

    ok = client.patch(
        f"/bills/{bid}/participants/{seats[1]['id']}",
        json={"user_id": owner, "guest_name": "Жена"},
    )
    assert ok.status_code == 200 and ok.json()["guest_name"] == "Жена"

    # Blank resets to the default label, which the client builds from seat_index.
    reset = client.patch(
        f"/bills/{bid}/participants/{seats[1]['id']}",
        json={"user_id": owner, "guest_name": "  "},
    )
    assert reset.json()["guest_name"] is None

    # The owner's own seat shows their Telegram name — nothing to rename.
    assert client.patch(
        f"/bills/{bid}/participants/{seats[0]['id']}",
        json={"user_id": owner, "guest_name": "X"},
    ).status_code == 400


def test_claiming_a_seat_inherits_its_dishes(client: TestClient):
    owner, bill = _bill(client, expected=2, tg=503)
    bid = bill["id"]
    item = client.post(f"/bills/{bid}/items", json={"name": "Lagman", "price": 40, "count": 1}).json()
    guest = _seats(client, bid, owner)[1]
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": item["id"], "participant_id": guest["id"], "is_assigned": True}]},
    )

    joiner = client.post("/users/", json={"telegram_id": 504, "username": "j"}).json()["id"]
    resp = client.post(f"/bills/{bid}/seats/{guest['id']}/claim", json={"user_id": joiner})
    assert resp.status_code == 200

    taken = next(p for p in resp.json()["participants"] if p["id"] == guest["id"])
    assert taken["user_id"] == joiner
    assert taken["is_guest"] is False
    assert taken["allocated_amount"] == 40


def test_taken_seat_cannot_be_claimed_twice(client: TestClient):
    owner, bill = _bill(client, expected=3, tg=505)
    bid = bill["id"]
    guest = _seats(client, bid, owner)[1]
    a = client.post("/users/", json={"telegram_id": 506, "username": "a"}).json()["id"]
    b = client.post("/users/", json={"telegram_id": 507, "username": "b"}).json()["id"]

    client.post(f"/bills/{bid}/seats/{guest['id']}/claim", json={"user_id": a})
    resp = client.post(f"/bills/{bid}/seats/{guest['id']}/claim", json={"user_id": b})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SEAT_TAKEN"


def test_moving_seats_leaves_the_dishes_behind(client: TestClient):
    """The person moves, the plate doesn't — that's why they're moving."""
    owner, bill = _bill(client, expected=3, tg=508)
    bid = bill["id"]
    soup = client.post(f"/bills/{bid}/items", json={"name": "Soup", "price": 10, "count": 1}).json()
    steak = client.post(f"/bills/{bid}/items", json={"name": "Steak", "price": 90, "count": 1}).json()
    seats = _seats(client, bid, owner)
    first, second = seats[1], seats[2]

    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [
            {"item_id": soup["id"], "participant_id": first["id"], "is_assigned": True},
            {"item_id": steak["id"], "participant_id": second["id"], "is_assigned": True},
        ]},
    )

    joiner = client.post("/users/", json={"telegram_id": 509, "username": "j2"}).json()["id"]
    client.post(f"/bills/{bid}/seats/{first['id']}/claim", json={"user_id": joiner})
    resp = client.post(
        f"/bills/{bid}/seats/{second['id']}/claim",
        json={"user_id": joiner, "confirm_move": True},
    )
    assert resp.status_code == 200

    by_id = {p["id"]: p for p in resp.json()["participants"]}
    assert by_id[first["id"]]["is_guest"] is True
    assert by_id[first["id"]]["allocated_amount"] == 10   # soup stayed put
    assert by_id[second["id"]]["user_id"] == joiner
    assert by_id[second["id"]]["allocated_amount"] == 90


def test_leaving_frees_the_seat_without_removing_it(client: TestClient):
    owner, bill = _bill(client, expected=2, tg=510)
    bid = bill["id"]
    guest = _seats(client, bid, owner)[1]
    joiner = client.post("/users/", json={"telegram_id": 511, "username": "j3"}).json()["id"]
    client.post(f"/bills/{bid}/seats/{guest['id']}/claim", json={"user_id": joiner})

    resp = client.post(f"/bills/{bid}/seats/{guest['id']}/release", json={"user_id": joiner})
    assert resp.status_code == 200
    seats = resp.json()["participants"]
    assert len(seats) == 2
    assert next(p for p in seats if p["id"] == guest["id"])["is_guest"] is True


def test_owner_cannot_leave_their_own_bill(client: TestClient):
    owner, bill = _bill(client, expected=2, tg=512)
    seat = _seats(client, bill["id"], owner)[0]
    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/release", json={"user_id": owner}
    )
    assert resp.status_code == 400


def test_seat_preview_by_token_shows_what_is_on_each_plate(client: TestClient):
    owner, bill = _bill(client, expected=2, tg=513)
    bid = bill["id"]
    item = client.post(f"/bills/{bid}/items", json={"name": "Kebab", "price": 50, "count": 1}).json()
    guest = _seats(client, bid, owner)[1]
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": item["id"], "participant_id": guest["id"], "is_assigned": True}]},
    )

    # Readable without being in the bill — you can't have a seat before you pick one.
    client.post("/users/", json={"telegram_id": 9001, "username": "newcomer"})
    resp = client.get(
        f"/bills/public/{bill['public_token']}/seats", headers=auth_headers(9001)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bill_id"] == bid and body["title"] == "Dinner"

    free = next(s for s in body["seats"] if not s["is_taken"])
    assert [i["name"] for i in free["items"]] == ["Kebab"]
    assert free["items"][0]["share"] == 50


def test_participants_come_back_in_seat_order(client: TestClient):
    """Claiming a seat updates a row; without an ORDER BY it would jump to the end."""
    owner, bill = _bill(client, expected=4, tg=520)
    bid = bill["id"]
    joiner = client.post("/users/", json={"telegram_id": 521, "username": "j"}).json()["id"]

    seats = _seats(client, bid, owner)
    client.post(f"/bills/{bid}/seats/{seats[2]['id']}/claim", json={"user_id": joiner})

    after = client.get(f"/bills/{bid}?user_id={owner}").json()["participants"]
    assert [p["seat_index"] for p in after] == [0, 1, 2, 3]


def test_freeing_a_seat_keeps_the_receipts_in_the_response(client: TestClient, session):
    """Actions that answer with the bill must not drop receipts[] on the way."""
    from app.models import ReceiptSource, ReceiptTask, ReceiptTaskStatus

    owner, bill = _bill(client, expected=2, tg=522)
    bid = bill["id"]
    joiner = client.post("/users/", json={"telegram_id": 523, "username": "j2"}).json()["id"]
    seat = _seats(client, bid, owner)[1]
    client.post(f"/bills/{bid}/seats/{seat['id']}/claim", json={"user_id": joiner})

    session.add(
        ReceiptTask(
            user_id=owner, filename="r.jpg", status=ReceiptTaskStatus.COMPLETED,
            source=ReceiptSource.PHOTO, bill_id=bid,
            llm_response='{"title": "Chaikhana", "total_sum": 100}',
        )
    )
    session.commit()

    assert len(client.get(f"/bills/{bid}?user_id={owner}").json()["receipts"]) == 1

    freed = client.post(f"/bills/{bid}/seats/{seat['id']}/release", json={"user_id": joiner})
    assert freed.status_code == 200
    assert len(freed.json()["receipts"]) == 1


def test_remainder_can_be_split_onto_unclaimed_seats(client: TestClient):
    """Closing a bill with empty seats must not inflate everyone else's share."""
    owner, bill = _bill(client, expected=3, tg=524)
    bid = bill["id"]
    client.post(f"/bills/{bid}/items", json={"name": "Plov", "price": 90, "count": 1})

    seat_ids = [p["id"] for p in _seats(client, bid, owner)]
    resp = client.post(
        f"/bills/{bid}/split-remainder", json={"participant_ids": seat_ids}
    )
    assert resp.status_code == 200

    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    assert detail["unallocated_sum"] == 0
    assert all(p["allocated_amount"] == 30 for p in detail["participants"])


def test_moving_back_to_an_earlier_seat_works(client: TestClient):
    """Swapping seats repeatedly, in both directions.

    Vacating and claiming used to happen in one flush, and SQLAlchemy orders
    those UPDATEs by primary key rather than by meaning: moving to a
    lower-numbered seat wrote the new occupant first, briefly putting the same
    user on two seats, which the (bill_id, user_id) unique index rejects. So
    moving «forward» worked and moving back blew up.
    """
    owner, bill = _bill(client, expected=4, tg=530)
    bid = bill["id"]
    joiner = client.post("/users/", json={"telegram_id": 531, "username": "j"}).json()["id"]

    seats = _seats(client, bid, owner)
    first, second, third = seats[1]["id"], seats[2]["id"], seats[3]["id"]

    # Forward, then back, then forward again — each hop must land.
    for target in (second, first, third, first, second):
        resp = client.post(
            f"/bills/{bid}/seats/{target}/claim",
            json={"user_id": joiner, "confirm_move": True},
        )
        assert resp.status_code == 200, resp.text

        occupied = [p for p in resp.json()["participants"] if p["user_id"] == joiner]
        assert [p["id"] for p in occupied] == [target]


def test_a_vacated_seat_goes_back_to_being_an_anonymous_guest(client: TestClient):
    owner, bill = _bill(client, expected=3, tg=532)
    bid = bill["id"]
    seats = _seats(client, bid, owner)
    client.patch(
        f"/bills/{bid}/participants/{seats[1]['id']}",
        json={"user_id": owner, "guest_name": "Жена"},
    )

    joiner = client.post("/users/", json={"telegram_id": 533, "username": "j2"}).json()["id"]
    client.post(f"/bills/{bid}/seats/{seats[1]['id']}/claim", json={"user_id": joiner})
    resp = client.post(
        f"/bills/{bid}/seats/{seats[2]['id']}/claim",
        json={"user_id": joiner, "confirm_move": True},
    )

    vacated = next(p for p in resp.json()["participants"] if p["id"] == seats[1]["id"])
    assert vacated["is_guest"] is True
    assert vacated["guest_name"] is None


def test_a_closed_bill_still_opens_for_whoever_already_sits_on_the_seat(
    client: TestClient, session
):
    """Every button in a personal invite claims the seat on the way in.

    A bill closes itself once everyone has paid, so the person who paid last is
    the one most likely to follow their invite afterwards — and they were the
    one being refused their own bill.
    """
    owner = client.post("/users/", json={"telegram_id": 640, "username": "owner"}).json()
    guest = client.post("/users/", json={"telegram_id": 641, "username": "guest"}).json()
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner["id"],
            "total_sum": 100,
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    seat = next(
        p
        for p in client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()["participants"]
        if p["is_guest"]
    )
    client.post(f"/bills/{bill['id']}/seats/{seat['id']}/claim", json={"user_id": guest["id"]})

    closed = session.get(Bill, bill["id"])
    closed.status = BillStatus.CLOSED
    session.add(closed)
    session.commit()

    again = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/claim", json={"user_id": guest["id"]}
    )

    assert again.status_code == 200
    assert again.json()["status"] == BillStatus.CLOSED


def test_a_closed_bill_still_refuses_a_newcomer(client: TestClient, session):
    owner = client.post("/users/", json={"telegram_id": 650, "username": "owner"}).json()
    stranger = client.post("/users/", json={"telegram_id": 651, "username": "who"}).json()
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner["id"],
            "total_sum": 100,
            "include_owner": True,
            "expected_people": 2,
        },
    ).json()
    seat = next(
        p
        for p in client.get(f"/bills/{bill['id']}?user_id={owner['id']}").json()["participants"]
        if p["is_guest"]
    )
    closed = session.get(Bill, bill["id"])
    closed.status = BillStatus.CLOSED
    session.add(closed)
    session.commit()

    resp = client.post(
        f"/bills/{bill['id']}/seats/{seat['id']}/claim", json={"user_id": stranger["id"]}
    )

    assert resp.status_code == 400


def test_the_owner_cannot_be_moved_off_their_own_seat(client: TestClient):
    """The hole behind «a guest took the organiser's dishes».

    `release_seat` has always refused to let the owner stand up, but claiming
    another seat went around it: seat 0 was vacated with the owner's dishes
    still on it, and the next arrival could simply take them.
    """
    owner, bill = _bill(client, expected=3, tg=540)
    bid = bill["id"]
    steak = client.post(f"/bills/{bid}/items", json={"name": "Steak", "price": 100, "count": 1}).json()
    seats = _seats(client, bid, owner)
    own, guest = seats[0], seats[1]
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": steak["id"], "participant_id": own["id"], "is_assigned": True}]},
    )

    # Following a personal invite meant for a guest — the way this actually
    # happened: the owner taps the link in the chat they sent it to.
    resp = client.post(
        f"/bills/{bid}/seats/{guest['id']}/claim",
        json={"user_id": owner, "confirm_move": True},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "OWNER_SEAT_FIXED"

    after = {p["id"]: p for p in _seats(client, bid, owner)}
    assert after[own["id"]]["user_id"] == owner
    assert after[own["id"]]["allocated_amount"] == 100
    assert after[guest["id"]]["is_guest"] is True


def test_a_paid_seat_has_to_be_unpaid_before_moving(client: TestClient):
    owner, bill = _bill(client, expected=3, tg=542)
    bid = bill["id"]
    soup = client.post(f"/bills/{bid}/items", json={"name": "Soup", "price": 40, "count": 1}).json()
    tea = client.post(f"/bills/{bid}/items", json={"name": "Tea", "price": 10, "count": 1}).json()
    seats = _seats(client, bid, owner)
    first, second = seats[1], seats[2]
    # The second seat gets a share of its own, or the bill settles the moment
    # the only payer pays and the move is refused for being on a closed bill.
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [
            {"item_id": soup["id"], "participant_id": first["id"], "is_assigned": True},
            {"item_id": tea["id"], "participant_id": second["id"], "is_assigned": True},
        ]},
    )

    joiner = client.post("/users/", json={"telegram_id": 543, "username": "j"}).json()["id"]
    client.post(f"/bills/{bid}/seats/{first['id']}/claim", json={"user_id": joiner})
    client.post(
        f"/bills/{bid}/participants/{first['id']}/payment",
        json={"user_id": joiner, "is_paid": True},
    )

    # The payment was for THIS plate; moving would quietly re-point it at another.
    resp = client.post(
        f"/bills/{bid}/seats/{second['id']}/claim",
        json={"user_id": joiner, "confirm_move": True},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SEAT_PAID"

    # Undo the payment and the move goes through.
    client.post(
        f"/bills/{bid}/participants/{first['id']}/payment",
        json={"user_id": joiner, "is_paid": False},
    )
    moved = client.post(
        f"/bills/{bid}/seats/{second['id']}/claim",
        json={"user_id": joiner, "confirm_move": True},
    )
    assert moved.status_code == 200


def test_a_move_nobody_confirmed_is_refused(client: TestClient):
    """A tapped link must not reseat anyone on its own.

    Taking a first seat needs no confirmation — there is nothing to leave
    behind. Moving does, because the dishes stay on the seat being vacated.
    """
    owner, bill = _bill(client, expected=3, tg=545)
    bid = bill["id"]
    seats = _seats(client, bid, owner)
    first, second = seats[1], seats[2]
    joiner = client.post("/users/", json={"telegram_id": 546, "username": "j"}).json()["id"]

    sit_down = client.post(f"/bills/{bid}/seats/{first['id']}/claim", json={"user_id": joiner})
    assert sit_down.status_code == 200

    unconfirmed = client.post(f"/bills/{bid}/seats/{second['id']}/claim", json={"user_id": joiner})
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["detail"] == "SEAT_MOVE_CONFIRM"
    still = {p["id"]: p for p in _seats(client, bid, owner)}
    assert still[first["id"]]["user_id"] == joiner

    confirmed = client.post(
        f"/bills/{bid}/seats/{second['id']}/claim",
        json={"user_id": joiner, "confirm_move": True},
    )
    assert confirmed.status_code == 200


def test_re_opening_the_same_invite_is_not_a_move(client: TestClient):
    """Tapping your own link twice must stay harmless."""
    owner, bill = _bill(client, expected=3, tg=548)
    bid = bill["id"]
    seat = _seats(client, bid, owner)[1]
    joiner = client.post("/users/", json={"telegram_id": 549, "username": "j"}).json()["id"]

    client.post(f"/bills/{bid}/seats/{seat['id']}/claim", json={"user_id": joiner})
    again = client.post(f"/bills/{bid}/seats/{seat['id']}/claim", json={"user_id": joiner})
    assert again.status_code == 200
