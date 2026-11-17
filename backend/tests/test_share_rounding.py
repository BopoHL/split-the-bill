"""STB-203: the rounding left over when a shared item isn't divisible by the
headcount is given to the owner instead of lingering as an unallocated remainder.

Seats exist for the whole headcount from the start, so a shared item always
allocates in full — an unclaimed guest carries their share like anyone else.
"""

from fastapi.testclient import TestClient


def test_shared_rounding_goes_to_owner(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    owner = 1
    bill = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "expected_people": 3, "include_owner": True},
    ).json()
    bid = bill["id"]

    # Two guests claim the seats waiting for them → 3 people, as declared.
    seats = client.get(f"/bills/{bid}?user_id={owner}").json()["participants"]
    free = [p["id"] for p in seats if p["user_id"] is None]
    client.post("/users/", json={"telegram_id": 2, "username": "a"})
    client.post(f"/bills/{bid}/seats/{free[0]}/claim", json={"user_id": 2})
    client.post("/users/", json={"telegram_id": 3, "username": "b"})
    client.post(f"/bills/{bid}/seats/{free[1]}/claim", json={"user_id": 3})

    # An item whose sum isn't divisible by 3, shared among everyone.
    item = client.post(
        f"/bills/{bid}/items", json={"name": "Pizza", "price": 100, "count": 1}
    ).json()
    client.patch(f"/bills/{bid}/items/{item['id']}", json={"is_shared_globally": True})

    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    # No remainder left to resolve at close.
    assert detail["unallocated_sum"] == 0
    alloc = {p["user_id"]: p["allocated_amount"] for p in detail["participants"]}
    # Owner carries the rounding → strictly more than the evenly-split others.
    assert alloc[owner] > alloc[2]
    assert alloc[2] == alloc[3]


def test_unclaimed_seat_is_allocated_its_share(client: TestClient):
    """The third seat is still a guest, and it owes its third all the same."""
    client.post("/users/", json={"telegram_id": 10, "username": "owner2"})
    owner = 1
    bill = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "expected_people": 3, "include_owner": True},
    ).json()
    bid = bill["id"]
    client.post("/users/", json={"telegram_id": 11, "username": "c"})
    free = [
        p["id"]
        for p in client.get(f"/bills/{bid}?user_id={owner}").json()["participants"]
        if p["user_id"] is None
    ]
    client.post(f"/bills/{bid}/seats/{free[0]}/claim", json={"user_id": 2})

    item = client.post(
        f"/bills/{bid}/items", json={"name": "Cake", "price": 90, "count": 1}
    ).json()
    client.patch(f"/bills/{bid}/items/{item['id']}", json={"is_shared_globally": True})

    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    # 90 / 3 = 30 each, and the still-unclaimed guest holds the third 30.
    assert detail["unallocated_sum"] == 0
    guest = next(p for p in detail["participants"] if p["user_id"] is None)
    assert guest["allocated_amount"] == 30
    assert guest["is_guest"] is True
