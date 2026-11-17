from fastapi.testclient import TestClient

from tests.conftest import auth_headers


def _pid(client, bid, user_id):
    """Seat id behind a user — assignments target seats, not accounts."""
    d = client.get(f"/bills/{bid}?user_id={user_id}").json()
    return next(p["id"] for p in d["participants"] if p["user_id"] == user_id)


def _mk_bill(client, tg, uname):
    owner = client.post("/users/", json={"telegram_id": tg, "username": uname}).json()["id"]
    bid = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "title": "T", "include_owner": True},
    ).json()["id"]
    return owner, bid


def test_assign_batch_applies_every_op_and_returns_bill(client: TestClient):
    """Whole multi-select lands in one request — no portion dropped (the iOS bug)."""
    owner, bid = _mk_bill(client, 1, "o")
    a = client.post(f"/bills/{bid}/items", json={"name": "A", "price": 100, "count": 1}).json()
    b = client.post(f"/bills/{bid}/items", json={"name": "B", "price": 30, "count": 2}).json()

    resp = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [
            {"item_id": a["id"], "participant_id": _pid(client, bid, owner), "is_assigned": True},
            {"item_id": b["id"], "participant_id": _pid(client, bid, owner), "is_assigned": True, "portion_index": 0},
            {"item_id": b["id"], "participant_id": _pid(client, bid, owner), "is_assigned": True, "portion_index": 1},
        ]},
    )
    assert resp.status_code == 200
    bill = resp.json()
    items = {i["name"]: i for i in bill["items"]}
    assert _pid(client, bid, owner) in items["A"]["assigned_participant_ids"]
    assert _pid(client, bid, owner) in items["B"]["assigned_participant_ids"]
    me = next(p for p in bill["participants"] if p["user_id"] == owner)
    assert me["allocated_amount"] == 160  # 100 + 30 + 30
    assert bill["unallocated_sum"] == 0

    resp2 = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": b["id"], "participant_id": _pid(client, bid, owner), "is_assigned": False, "portion_index": 1}]},
    )
    assert resp2.status_code == 200
    me2 = next(p for p in resp2.json()["participants"] if p["user_id"] == owner)
    assert me2["allocated_amount"] == 130
    assert resp2.json()["unallocated_sum"] == 30


def test_assign_batch_dedups_duplicate_ops(client: TestClient):
    """Duplicate (item, user, portion) ops must not violate the unique index."""
    owner, bid = _mk_bill(client, 2, "o2")
    bob = client.post("/users/", json={"telegram_id": 3, "username": "bob"}).json()["id"]
    client.post(f"/bills/{bid}/participants", json={"user_id": bob})
    item = client.post(f"/bills/{bid}/items", json={"name": "Pizza", "price": 90, "count": 1}).json()

    resp = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [
            {"item_id": item["id"], "participant_id": _pid(client, bid, bob), "is_assigned": True},
            {"item_id": item["id"], "participant_id": _pid(client, bid, bob), "is_assigned": True},
        ]},
    )
    assert resp.status_code == 200
    piz = next(i for i in resp.json()["items"] if i["name"] == "Pizza")
    assert piz["assigned_participant_ids"] == [_pid(client, bid, bob)]


def test_assign_batch_shares_item_and_clears_personal(client: TestClient):
    """Shared-flag op + unassign in one batch: item becomes globally shared."""
    owner, bid = _mk_bill(client, 4, "o4")
    bob = client.post("/users/", json={"telegram_id": 5, "username": "bob2"}).json()["id"]
    client.post(f"/bills/{bid}/participants", json={"user_id": bob})
    item = client.post(f"/bills/{bid}/items", json={"name": "Cake", "price": 80, "count": 1}).json()

    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": item["id"], "participant_id": _pid(client, bid, bob), "is_assigned": True}]},
    )
    resp = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={
            "shared": [{"item_id": item["id"], "is_shared_globally": True}],
            "ops": [{"item_id": item["id"], "participant_id": _pid(client, bid, bob), "is_assigned": False}],
        },
    )
    assert resp.status_code == 200
    cake = next(i for i in resp.json()["items"] if i["name"] == "Cake")
    assert cake["is_shared_globally"] is True
    assert _pid(client, bid, bob) not in cake["assigned_participant_ids"]


def test_assign_batch_takes_one_person_off_an_item_shared_among_all(client: TestClient):
    """Leaving a global share spells the item out for everyone else in one batch."""
    owner, bid = _mk_bill(client, 8, "o8")
    bob = client.post("/users/", json={"telegram_id": 9, "username": "bob8"}).json()["id"]
    carol = client.post("/users/", json={"telegram_id": 10, "username": "carol8"}).json()["id"]
    for user in (bob, carol):
        client.post(f"/bills/{bid}/participants", json={"user_id": user})
    tea = client.post(f"/bills/{bid}/items", json={"name": "Tea", "price": 90, "count": 1}).json()
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [], "shared": [{"item_id": tea["id"], "is_shared_globally": True}]},
    )
    seats = {user: _pid(client, bid, user) for user in (owner, bob, carol)}

    resp = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={
            "shared": [{"item_id": tea["id"], "is_shared_globally": False}],
            "ops": [
                {"item_id": tea["id"], "portion_index": 0, "expected_count": 1, "participant_id": seat, "is_assigned": user != bob}
                for user, seat in seats.items()
            ],
        },
    )

    assert resp.status_code == 200
    item = next(i for i in resp.json()["items"] if i["name"] == "Tea")
    assert item["is_shared_globally"] is False
    assert sorted(item["assigned_participant_ids"]) == sorted([seats[owner], seats[carol]])
    shares = {p["user_id"]: p["allocated_amount"] for p in resp.json()["participants"]}
    assert (shares[owner], shares[bob], shares[carol]) == (45, 0, 45)


def test_assign_batch_rejects_non_owner_assigning_others(client: TestClient):
    """A non-owner may only (un)assign themselves in a batch."""
    owner, bid = _mk_bill(client, 6, "o6")
    bob = client.post("/users/", json={"telegram_id": 7, "username": "bob3"}).json()["id"]
    client.post(f"/bills/{bid}/participants", json={"user_id": bob})
    item = client.post(f"/bills/{bid}/items", json={"name": "X", "price": 10, "count": 1}).json()

    resp = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={bob}",
        json={"ops": [{"item_id": item["id"], "participant_id": _pid(client, bid, owner), "is_assigned": True}]},
    )
    assert resp.status_code == 403


def test_assign_batch_rejects_non_owner_shared_change_and_rolls_back_own_assignment(
    client: TestClient,
):
    owner, bid = _mk_bill(client, 8, "o8")
    bob = client.post("/users/", json={"telegram_id": 9, "username": "bob4"}).json()["id"]
    client.post(f"/bills/{bid}/participants", json={"user_id": bob})
    item = client.post(
        f"/bills/{bid}/items",
        json={"name": "Shared", "price": 25, "count": 1},
    ).json()
    bob_participant = _pid(client, bid, bob)

    response = client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={bob}",
        json={
            "shared": [{"item_id": item["id"], "is_shared_globally": True}],
            "ops": [
                {
                    "item_id": item["id"],
                    "participant_id": bob_participant,
                    "is_assigned": True,
                    "portion_index": 0,
                    "expected_count": 1,
                }
            ],
        },
    )

    assert response.status_code == 403
    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    stored = next(current for current in detail["items"] if current["id"] == item["id"])
    assert stored["is_shared_globally"] is False
    assert stored["portions"] == [[]]


def test_a_guest_cannot_turn_a_split_by_hand_into_one_by_dishes(client: TestClient):
    """Picking would recalculate by dishes and wipe every unpaid hand-set share."""
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o"}).json()["id"]
    guest = client.post("/users/", json={"telegram_id": 2, "username": "g"}).json()["id"]
    bill = client.post(
        "/bills/", json={"owner_id": owner, "total_sum": 0, "include_owner": True, "expected_people": 2}
    ).json()
    bid = bill["id"]
    pizza = client.post(f"/bills/{bid}/items", json={"name": "Pizza", "price": 150, "count": 1}).json()
    seats = client.get(f"/bills/{bid}?user_id={owner}").json()["participants"]
    mine = next(s for s in seats if s["user_id"] is None)
    client.post(f"/bills/{bid}/seats/{mine['id']}/claim", json={"user_id": guest})
    for seat in seats:
        client.post(f"/bills/{bid}/assign-amount", json={"participant_id": seat["id"], "allocated_amount": 75})

    single = client.post(
        f"/bills/{bid}/items/{pizza['id']}/assign",
        json={"participant_id": mine["id"], "is_assigned": True},
        headers=auth_headers(2),
    )
    batch = client.post(
        f"/bills/{bid}/items/assign-batch",
        json={"ops": [{"item_id": pizza["id"], "participant_id": mine["id"], "is_assigned": True}]},
        headers=auth_headers(2),
    )

    assert single.status_code == batch.status_code == 409
    after = client.get(f"/bills/{bid}?user_id={owner}").json()
    assert after["split_type"] == "manual"
    assert [p["allocated_amount"] for p in after["participants"]] == [75, 75]
