from fastapi.testclient import TestClient

from app.models import (
    Bill,
    BillUser,
    BillItem,
    BillItemSource,
    BillStatus,
    ReceiptSource,
    ReceiptTask,
    ReceiptTaskStatus,
    SplitType,
)


def _setup(client: TestClient, users: int = 2):
    user_ids = [
        client.post(
            "/users/",
            json={"telegram_id": 900 + index, "username": f"u{index}"},
        ).json()["id"]
        for index in range(users)
    ]
    owner = user_ids[0]
    bill_id = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "include_owner": True},
    ).json()["id"]
    for user_id in user_ids[1:]:
        response = client.post(
            f"/bills/{bill_id}/participants", json={"user_id": user_id}
        )
        assert response.status_code == 200
    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    participant_ids = {
        participant["user_id"]: participant["id"]
        for participant in detail["participants"]
    }
    return owner, bill_id, user_ids, participant_ids


def _legacy_item(
    session,
    bill_id: int,
    owner_id: int,
    *,
    count: int = 3,
    item_sum: int = 10_000,
    shared: bool = False,
    scanned: bool = False,
    currency: str = "uzs",
):
    receipt_task_id = None
    source = BillItemSource.MANUAL
    if scanned:
        task = ReceiptTask(
            user_id=owner_id,
            filename="legacy.jpg",
            source=ReceiptSource.PHOTO,
            status=ReceiptTaskStatus.COMPLETED,
            bill_id=bill_id,
        )
        session.add(task)
        session.flush()
        receipt_task_id = task.id
        source = BillItemSource.AI

    item = BillItem(
        bill_id=bill_id,
        name="Legacy dish",
        price=item_sum // count,
        count=count,
        item_sum=item_sum,
        is_shared_globally=shared,
        source=source,
        receipt_task_id=receipt_task_id,
    )
    bill = session.get(Bill, bill_id)
    bill.currency = currency
    bill.total_sum = item_sum
    bill.unallocated_sum = item_sum
    bill.split_type = SplitType.BY_ITEMS
    session.add(bill)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item, receipt_task_id


def _assign(client, bill_id, owner_id, ops):
    response = client.post(
        f"/bills/{bill_id}/items/assign-batch?requester_id={owner_id}",
        json={"ops": ops},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_position_patch_splits_one_unit_and_preserves_metadata_and_assignments(
    client: TestClient, session
):
    owner, bill_id, users, participants = _setup(client)
    bob = users[1]
    item, receipt_task_id = _legacy_item(
        session, bill_id, owner, item_sum=10_000, scanned=True, currency="usd"
    )
    _assign(
        client,
        bill_id,
        owner,
        [
            {"item_id": item.id, "participant_id": participants[owner], "is_assigned": True, "portion_index": 0, "expected_count": 3},
            {"item_id": item.id, "participant_id": participants[bob], "is_assigned": True, "portion_index": 1, "expected_count": 3},
            {"item_id": item.id, "participant_id": participants[bob], "is_assigned": True, "portion_index": 2, "expected_count": 3},
        ],
    )

    response = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 1, "expected_count": 3},
        json={"name": "Edited unit", "price": 40},
    )

    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["id"] != item.id
    assert edited["name"] == "Edited unit"
    assert edited["count"] == 1
    assert edited["item_sum"] == 40
    assert edited["receipt_task_id"] == receipt_task_id
    assert edited["portions"] == [[participants[bob]]]

    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    remainder = next(current for current in detail["items"] if current["id"] == item.id)
    assert remainder["count"] == 2
    assert remainder["item_sum"] == 66.67
    assert remainder["portions"] == [[participants[owner]], [participants[bob]]]
    assert detail["total_sum"] == 106.67
    allocations = {p["user_id"]: p["allocated_amount"] for p in detail["participants"]}
    assert allocations[owner] == 33.34
    assert allocations[bob] == 73.33

    session.expire_all()
    stored = session.get(BillItem, edited["id"])
    assert stored.source == BillItemSource.AI
    assert stored.receipt_task_id == receipt_task_id


def test_position_delete_preserves_exact_cents_and_compacts_assignments(
    client: TestClient, session
):
    owner, bill_id, users, participants = _setup(client, users=3)
    bob, carol = users[1:]
    item, _ = _legacy_item(session, bill_id, owner, item_sum=10_000, currency="usd")
    _assign(
        client,
        bill_id,
        owner,
        [
            {"item_id": item.id, "participant_id": participants[owner], "is_assigned": True, "portion_index": 0, "expected_count": 3},
            {"item_id": item.id, "participant_id": participants[bob], "is_assigned": True, "portion_index": 1, "expected_count": 3},
            {"item_id": item.id, "participant_id": participants[carol], "is_assigned": True, "portion_index": 2, "expected_count": 3},
        ],
    )

    response = client.delete(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0, "expected_count": 3},
    )

    assert response.status_code == 204, response.text
    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    remaining = detail["items"][0]
    assert remaining["id"] == item.id
    assert remaining["count"] == 2
    assert remaining["item_sum"] == 66.66
    assert remaining["portions"] == [[participants[bob]], [participants[carol]]]
    assert detail["total_sum"] == 66.66


def test_position_mutations_reject_stale_count_before_changing_data(
    client: TestClient, session
):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner)

    patch = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 1, "expected_count": 2},
        json={"name": "Must not land"},
    )
    assert patch.status_code == 409
    assert patch.json()["detail"]["code"] == "POSITION_STALE"

    delete = client.delete(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 1, "expected_count": 2},
    )
    assert delete.status_code == 409
    assert delete.json()["detail"]["code"] == "POSITION_STALE"

    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    assert detail["items"][0]["name"] == "Legacy dish"
    assert detail["items"][0]["count"] == 3
    assert detail["total_sum"] == 100


def test_multi_count_shared_position_edit_is_explicitly_unsupported_but_delete_works(
    client: TestClient, session
):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner, shared=True, currency="usd")

    patch = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0, "expected_count": 3},
        json={"name": "One shared unit"},
    )
    assert patch.status_code == 409
    assert patch.json()["detail"]["code"] == "SHARED_POSITION_EDIT_UNSUPPORTED"

    delete = client.delete(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0, "expected_count": 3},
    )
    assert delete.status_code == 204, delete.text
    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    remaining = detail["items"][0]
    assert remaining["is_shared_globally"] is True
    assert remaining["count"] == 2
    assert remaining["item_sum"] == 66.66
    assert detail["unallocated_sum"] == 0


def test_shared_position_delete_uses_exact_negative_minor_units(
    client: TestClient, session
):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(
        session, bill_id, owner, item_sum=-100, shared=True, currency="usd"
    )

    response = client.delete(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0, "expected_count": 3},
    )

    assert response.status_code == 204, response.text
    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    remaining = detail["items"][0]
    assert remaining["count"] == 2
    assert remaining["item_sum"] == -0.67
    assert detail["total_sum"] == -0.67
    assert detail["unallocated_sum"] == 0


def test_batch_expected_count_is_checked_before_shared_or_assignment_changes(
    client: TestClient, session
):
    owner, bill_id, users, participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner, count=2, item_sum=20_000)

    response = client.post(
        f"/bills/{bill_id}/items/assign-batch?requester_id={owner}",
        json={
            "shared": [{"item_id": item.id, "is_shared_globally": True}],
            "ops": [{
                "item_id": item.id,
                "participant_id": participants[users[1]],
                "is_assigned": True,
                "portion_index": 0,
                "expected_count": 3,
            }],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "POSITION_STALE"
    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    stored = detail["items"][0]
    assert stored["is_shared_globally"] is False
    assert stored["portions"] == [[], []]


def test_paid_assignments_and_indirect_paid_allocation_changes_are_locked(
    client: TestClient, session
):
    owner, bill_id, users, participants = _setup(client, users=3)
    bob, carol = users[1:]
    item, _ = _legacy_item(session, bill_id, owner, count=2, item_sum=20_000)
    _assign(
        client,
        bill_id,
        owner,
        [
            {"item_id": item.id, "participant_id": participants[bob], "is_assigned": True, "portion_index": 0, "expected_count": 2},
            {"item_id": item.id, "participant_id": participants[carol], "is_assigned": True, "portion_index": 1, "expected_count": 2},
        ],
    )
    paid = client.post(
        f"/bills/{bill_id}/participants/{participants[bob]}/payment",
        json={"user_id": bob, "is_paid": True},
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == BillStatus.OPEN

    edit = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0, "expected_count": 2},
        json={"price": 120},
    )
    assert edit.status_code == 409
    assert edit.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"

    locked_delete = client.delete(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0, "expected_count": 2},
    )
    assert locked_delete.status_code == 409
    assert locked_delete.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"

    direct = client.post(
        f"/bills/{bill_id}/items/{item.id}/assign?requester_id={bob}",
        json={"participant_id": participants[bob], "is_assigned": False, "portion_index": 0},
    )
    assert direct.status_code == 409
    assert direct.json()["detail"]["code"] == "PAID_ASSIGNMENT_LOCKED"

    indirect = client.post(
        f"/bills/{bill_id}/items/assign-batch?requester_id={owner}",
        json={"ops": [{
            "item_id": item.id,
            "participant_id": participants[carol],
            "is_assigned": True,
            "portion_index": 0,
            "expected_count": 2,
        }]},
    )
    assert indirect.status_code == 409
    assert indirect.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"

    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    assert detail["items"][0]["portions"] == [
        [participants[bob]],
        [participants[carol]],
    ]
    assert next(p for p in detail["participants"] if p["id"] == participants[bob])["allocated_amount"] == 100

    allowed = client.delete(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 1, "expected_count": 2},
    )
    assert allowed.status_code == 204, allowed.text
    after = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    assert after["items"][0]["portions"] == [[participants[bob]]]
    assert next(p for p in after["participants"] if p["id"] == participants[bob])["allocated_amount"] == 100


def test_reopened_owner_paid_marker_does_not_lock_owner_item_or_assignments(
    client: TestClient, session
):
    owner, bill_id, _users, participants = _setup(client, users=1)
    item, _ = _legacy_item(session, bill_id, owner, count=1, item_sum=10_000)
    owner_participant = participants[owner]
    _assign(
        client,
        bill_id,
        owner,
        [
            {
                "item_id": item.id,
                "participant_id": owner_participant,
                "is_assigned": True,
                "portion_index": 0,
                "expected_count": 1,
            }
        ],
    )

    closed = client.post(f"/bills/{bill_id}/close", json={"user_id": owner})
    assert closed.status_code == 200, closed.text
    reopened = client.post(f"/bills/{bill_id}/reopen", json={"user_id": owner})
    assert reopened.status_code == 200, reopened.text
    owner_seat = next(
        participant
        for participant in reopened.json()["participants"]
        if participant["id"] == owner_participant
    )
    assert owner_seat["is_paid"] is True

    edited = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0, "expected_count": 1},
        json={"price": 120},
    )
    assert edited.status_code == 200, edited.text

    removed = client.post(
        f"/bills/{bill_id}/items/{item.id}/assign?requester_id={owner}",
        json={
            "participant_id": owner_participant,
            "is_assigned": False,
            "portion_index": 0,
        },
    )
    assert removed.status_code == 200, removed.text

    restored = client.post(
        f"/bills/{bill_id}/items/assign-batch?requester_id={owner}",
        json={
            "ops": [
                {
                    "item_id": item.id,
                    "participant_id": owner_participant,
                    "is_assigned": True,
                    "portion_index": 0,
                    "expected_count": 1,
                }
            ]
        },
    )
    assert restored.status_code == 200, restored.text
    owner_after = next(
        participant
        for participant in restored.json()["participants"]
        if participant["id"] == owner_participant
    )
    assert owner_after["is_paid"] is True
    assert owner_after["allocated_amount"] == 120


def test_position_params_must_be_sent_together(client: TestClient, session):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner)

    response = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 0},
        json={"name": "No count"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "POSITION_PARAMS_REQUIRED"


def test_legacy_patch_without_position_still_updates_the_whole_item(
    client: TestClient, session
):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner)

    response = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        json={"name": "Whole item", "price": 40, "count": 2},
    )

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["id"] == item.id
    assert updated["name"] == "Whole item"
    assert updated["count"] == 2
    assert updated["item_sum"] == 80

    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    assert [current["id"] for current in detail["items"]] == [item.id]
    assert detail["total_sum"] == 80


def test_renaming_a_whole_line_keeps_a_total_its_unit_price_cannot_express(
    client: TestClient, session
):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner, count=3, item_sum=10_000)

    response = client.patch(f"/bills/{bill_id}/items/{item.id}", json={"name": "Samsa"})

    assert response.status_code == 200, response.text
    assert (response.json()["name"], response.json()["item_sum"]) == ("Samsa", 100)
    assert client.get(f"/bills/{bill_id}?user_id={owner}").json()["total_sum"] == 100


def _resize(client, bill_id, item_id, count):
    response = client.patch(f"/bills/{bill_id}/items/{item_id}", json={"count": count})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_smaller_line_drops_free_dishes_first_then_the_last_taken(client: TestClient, session):
    owner, bill_id, users, participants = _setup(client, users=3)
    bob, carol = participants[users[1]], participants[users[2]]
    item, _ = _legacy_item(session, bill_id, owner, count=4, item_sum=10_000)
    _assign(client, bill_id, owner, [
        {"item_id": item.id, "participant_id": bob, "is_assigned": True, "portion_index": 0, "expected_count": 4},
        {"item_id": item.id, "participant_id": carol, "is_assigned": True, "portion_index": 2, "expected_count": 4},
    ])

    two = _resize(client, bill_id, item.id, 2)
    assert (two["count"], two["item_sum"], two["portions"]) == (2, 50, [[bob], [carol]])

    one = _resize(client, bill_id, item.id, 1)
    assert (one["portions"], one["assigned_participant_ids"]) == ([[bob]], [bob])
    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    assert {p["id"]: p["allocated_amount"] for p in detail["participants"]}[carol] == 0


def test_a_bigger_line_adds_free_dishes_without_reviving_old_assignments(client: TestClient, session):
    owner, bill_id, users, participants = _setup(client)
    bob = participants[users[1]]
    item, _ = _legacy_item(session, bill_id, owner, count=2, item_sum=10_000)
    _assign(client, bill_id, owner, [
        {"item_id": item.id, "participant_id": bob, "is_assigned": True, "portion_index": 1, "expected_count": 2},
    ])
    item.count = 1
    session.add(item)
    session.commit()

    grown = _resize(client, bill_id, item.id, 3)

    assert (grown["count"], grown["item_sum"], grown["portions"]) == (3, 150, [[], [], []])


def test_a_line_keeps_at_least_one_dish(client: TestClient, session):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner, count=2)

    response = client.patch(f"/bills/{bill_id}/items/{item.id}", json={"count": 0})
    created = client.post(f"/bills/{bill_id}/items", json={"name": "Tea", "price": 5, "count": 0})

    assert (response.status_code, created.status_code) == (422, 422)


def test_dropping_a_paid_persons_dish_is_locked(client: TestClient, session):
    owner, bill_id, users, participants = _setup(client, users=3)
    bob, carol = participants[users[1]], participants[users[2]]
    item, _ = _legacy_item(session, bill_id, owner, count=3, item_sum=9_000)
    _assign(client, bill_id, owner, [
        {"item_id": item.id, "participant_id": bob, "is_assigned": True, "portion_index": 0, "expected_count": 3},
        {"item_id": item.id, "participant_id": bob, "is_assigned": True, "portion_index": 1, "expected_count": 3},
        {"item_id": item.id, "participant_id": carol, "is_assigned": True, "portion_index": 2, "expected_count": 3},
    ])
    paid = client.post(
        f"/bills/{bill_id}/participants/{bob}/payment",
        json={"user_id": users[1], "is_paid": True},
    )
    assert paid.status_code == 200

    response = client.patch(f"/bills/{bill_id}/items/{item.id}", json={"count": 1})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"
    assert client.get(f"/bills/{bill_id}?user_id={owner}").json()["items"][0]["portions"] == [[bob], [bob], [carol]]


def test_legacy_delete_without_position_still_deletes_the_whole_item(
    client: TestClient, session
):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner)

    response = client.delete(f"/bills/{bill_id}/items/{item.id}")

    assert response.status_code == 204, response.text
    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    assert detail["items"] == []
    assert detail["total_sum"] == 0


def test_whole_item_changes_keep_paid_shares_locked(client: TestClient, session):
    owner, bill_id, users, participants = _setup(client, users=3)
    bob, carol = users[1:]
    item, _ = _legacy_item(session, bill_id, owner, count=2, item_sum=20_000)
    _assign(
        client,
        bill_id,
        owner,
        [
            {"item_id": item.id, "participant_id": participants[bob], "is_assigned": True, "portion_index": 0, "expected_count": 2},
            {"item_id": item.id, "participant_id": participants[carol], "is_assigned": True, "portion_index": 1, "expected_count": 2},
        ],
    )
    paid = client.post(
        f"/bills/{bill_id}/participants/{participants[bob]}/payment",
        json={"user_id": bob, "is_paid": True},
    )
    assert paid.status_code == 200

    repriced = client.patch(f"/bills/{bill_id}/items/{item.id}", json={"price": 50})
    assert repriced.status_code == 409
    assert repriced.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"

    removed = client.delete(f"/bills/{bill_id}/items/{item.id}")
    assert removed.status_code == 409
    assert removed.json()["detail"]["code"] == "PAID_ALLOCATION_LOCKED"

    renamed = client.patch(f"/bills/{bill_id}/items/{item.id}", json={"name": "Samsa"})
    assert renamed.status_code == 200, renamed.text

    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    assert [(current["name"], current["item_sum"]) for current in detail["items"]] == [("Samsa", 200)]
    assert next(p for p in detail["participants"] if p["id"] == participants[bob])["allocated_amount"] == 100


def test_legacy_batch_position_without_expected_count_is_still_accepted(
    client: TestClient, session
):
    owner, bill_id, users, participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner)

    response = client.post(
        f"/bills/{bill_id}/items/assign-batch?requester_id={owner}",
        json={
            "ops": [
                {
                    "item_id": item.id,
                    "participant_id": participants[users[1]],
                    "is_assigned": True,
                    "portion_index": 1,
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    stored = response.json()["items"][0]
    assert stored["portions"] == [[], [participants[users[1]]], []]


def test_legacy_batch_still_rejects_closed_bills_before_mutation(
    client: TestClient, session
):
    owner, bill_id, users, participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner)
    bill = session.get(Bill, bill_id)
    bill.status = BillStatus.CLOSED
    session.add(bill)
    session.commit()

    response = client.post(
        f"/bills/{bill_id}/items/assign-batch?requester_id={owner}",
        json={
            "ops": [
                {
                    "item_id": item.id,
                    "participant_id": participants[users[1]],
                    "is_assigned": True,
                    "portion_index": 1,
                }
            ]
        },
    )

    assert response.status_code == 400
    session.expire_all()
    assert session.get(BillItem, item.id).assignments == []


def test_dishes_shared_by_the_same_guests_split_evenly_and_spare_the_owner(client: TestClient, session):
    owner, bill_id, users, participants = _setup(client, users=4)
    guests = [participants[user_id] for user_id in users[1:]]
    item, _ = _legacy_item(session, bill_id, owner, count=3, item_sum=10_500_000)

    _assign(client, bill_id, owner, [
        {"item_id": item.id, "participant_id": guest, "is_assigned": True, "portion_index": portion, "expected_count": 3}
        for portion in range(3)
        for guest in guests
    ])

    detail = client.get(f"/bills/{bill_id}?user_id={owner}").json()
    allocations = {p["user_id"]: p["allocated_amount"] for p in detail["participants"]}
    assert allocations == {owner: 0, users[1]: 35_000, users[2]: 35_000, users[3]: 35_000}
    assert detail["unallocated_sum"] == 0


def test_a_paid_guest_is_untouched_by_another_dish_of_their_line(client: TestClient, session):
    owner, bill_id, users, participants = _setup(client, users=7)
    item, _ = _legacy_item(session, bill_id, owner, count=2, item_sum=5_000_000)
    first_table, second_table = [participants[u] for u in users[3:6]], [participants[u] for u in (users[1], users[2], users[6])]

    def dish(portion, seat):
        return {"item_id": item.id, "participant_id": seat, "is_assigned": True, "portion_index": portion, "expected_count": 2}

    _assign(client, bill_id, owner, [dish(0, seat) for seat in first_table])
    paid = session.get(BillUser, first_table[0])
    paid.is_paid = True
    session.add(paid)
    session.commit()

    _assign(client, bill_id, owner, [dish(1, seat) for seat in second_table])

    allocations = {p["id"]: p["allocated_amount"] for p in client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]}
    assert sorted(allocations[seat] for seat in first_table) == [8_333, 8_333, 8_334]
    assert sorted(allocations[seat] for seat in second_table) == [8_333, 8_333, 8_334]


def test_renaming_one_dish_of_a_line_leaves_every_share_as_it_was(client: TestClient, session):
    owner, bill_id, users, participants = _setup(client, users=4)
    guests = [participants[user_id] for user_id in users[1:]]
    item, _ = _legacy_item(session, bill_id, owner, count=3, item_sum=10_500_000)
    _assign(client, bill_id, owner, [
        {"item_id": item.id, "participant_id": guest, "is_assigned": True, "portion_index": portion, "expected_count": 3}
        for portion in range(3)
        for guest in guests
    ])
    paid = session.get(BillUser, guests[2])
    paid.is_paid = True
    session.add(paid)
    session.commit()

    response = client.patch(
        f"/bills/{bill_id}/items/{item.id}",
        params={"portion_index": 1, "expected_count": 3},
        json={"name": "Raketka"},
    )

    assert response.status_code == 200, response.text
    allocations = {p["id"]: p["allocated_amount"] for p in client.get(f"/bills/{bill_id}?user_id={owner}").json()["participants"]}
    assert [allocations[guest] for guest in guests] == [35_000, 35_000, 35_000]


def test_deleting_a_dish_in_sums_keeps_the_rest_in_whole_sums(client: TestClient, session):
    owner, bill_id, _users, _participants = _setup(client)
    item, _ = _legacy_item(session, bill_id, owner, count=3, item_sum=10_000_000)

    response = client.delete(f"/bills/{bill_id}/items/{item.id}", params={"portion_index": 0, "expected_count": 3})

    assert response.status_code == 204, response.text
    remaining = next(current for current in client.get(f"/bills/{bill_id}?user_id={owner}").json()["items"] if current["id"] == item.id)
    assert (remaining["count"], remaining["item_sum"]) == (2, 66_666)
