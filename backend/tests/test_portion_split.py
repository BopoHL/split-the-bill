"""STB-176: per-portion item assignment & split.

An item with count N has N portions (each item_sum/N); a portion can be shared
(splits among its takers); unclaimed portions stay in the remainder. count=1
keeps the old "split the whole item among its assignees" behaviour.
"""
from fastapi.testclient import TestClient


def _setup(client: TestClient, n_users=2):
    ids = []
    for i in range(1, n_users + 1):
        u = client.post("/users/", json={"telegram_id": i, "username": f"u{i}"}).json()
        ids.append(u["id"])
    owner = ids[0]
    bill = client.post(
        "/bills/", json={"owner_id": owner, "total_sum": 0, "include_owner": True}
    ).json()
    bid = bill["id"]
    for uid in ids[1:]:
        client.post(f"/bills/{bid}/participants", json={"user_id": uid})
    return bid, ids


def _add_item(client, bid, price, count):
    return client.post(
        f"/bills/{bid}/items", json={"name": "Dish", "price": price, "count": count}
    ).json()


def _pid(client, bid, user_id):
    """Seat id behind a user — assignments target seats, not accounts."""
    d = client.get(f"/bills/{bid}?user_id={user_id}").json()
    return next(p["id"] for p in d["participants"] if p["user_id"] == user_id)


def _assign(client, bid, item_id, user_id, requester, portion=None, assigned=True):
    body = {"participant_id": _pid(client, bid, user_id), "is_assigned": assigned}
    if portion is not None:
        body["portion_index"] = portion
    r = client.post(f"/bills/{bid}/items/{item_id}/assign?requester_id={requester}", json=body)
    assert r.status_code == 200, r.text


def _alloc(client, bid, uid):
    d = client.get(f"/bills/{bid}?user_id={uid}").json()
    p = next(p for p in d["participants"] if p["user_id"] == uid)
    return p["allocated_amount"], d


# --- count=1: existing "share one dish among takers" still works -----------

def test_single_quantity_item_splits_among_takers(client: TestClient):
    bid, (u1, u2) = _setup(client)
    item = _add_item(client, bid, price=100, count=1)
    _assign(client, bid, item["id"], u1, requester=u1)        # whole item (portion None)
    _assign(client, bid, item["id"], u2, requester=u1)
    a1, _ = _alloc(client, bid, u1)
    a2, _ = _alloc(client, bid, u2)
    assert a1 == 50.0 and a2 == 50.0


# --- count>1: distinct portions to different people ------------------------

def test_distinct_portions_to_different_users(client: TestClient):
    bid, (u1, u2) = _setup(client)
    item = _add_item(client, bid, price=100, count=2)  # 2 portions of 100
    _assign(client, bid, item["id"], u1, requester=u1, portion=0)
    _assign(client, bid, item["id"], u2, requester=u2, portion=1)
    a1, d = _alloc(client, bid, u1)
    a2, _ = _alloc(client, bid, u2)
    assert a1 == 100.0 and a2 == 100.0
    assert d["unallocated_sum"] == 0.0
    # Response exposes per-portion assignees.
    it = d["items"][0]
    assert sorted(it["portions"][0]) == [_pid(client, bid, u1)]
    assert sorted(it["portions"][1]) == [_pid(client, bid, u2)]


# --- count>1: one portion shared, the other taken whole -------------------

def test_shared_portion_plus_solo_portion(client: TestClient):
    bid, (u1, u2) = _setup(client)
    item = _add_item(client, bid, price=100, count=2)  # 2 portions of 100
    _assign(client, bid, item["id"], u1, requester=u1, portion=0)  # portion 0 shared
    _assign(client, bid, item["id"], u2, requester=u1, portion=0)
    _assign(client, bid, item["id"], u1, requester=u1, portion=1)  # portion 1 solo u1
    a1, _ = _alloc(client, bid, u1)
    a2, _ = _alloc(client, bid, u2)
    assert a1 == 150.0  # 50 (half of portion 0) + 100 (portion 1)
    assert a2 == 50.0   # half of portion 0


# --- whole-item assign covers every portion -------------------------------

def test_whole_item_assign_covers_all_portions(client: TestClient):
    bid, (u1, u2) = _setup(client)
    item = _add_item(client, bid, price=30, count=3)  # item_sum 90
    _assign(client, bid, item["id"], u1, requester=u1)  # portion None → all 3
    a1, d = _alloc(client, bid, u1)
    assert a1 == 90.0
    assert all(p == [_pid(client, bid, u1)] for p in d["items"][0]["portions"])


# --- unclaimed portion stays in the remainder -----------------------------

def test_unclaimed_portion_goes_to_remainder(client: TestClient):
    bid, (u1, u2) = _setup(client)
    item = _add_item(client, bid, price=100, count=2)  # 2 portions of 100
    _assign(client, bid, item["id"], u1, requester=u1, portion=0)  # only portion 0
    a1, d = _alloc(client, bid, u1)
    assert a1 == 100.0
    assert d["unallocated_sum"] == 100.0  # portion 1 unclaimed


# --- dropping a single portion re-splits ----------------------------------

def test_drop_single_portion(client: TestClient):
    bid, (u1, u2) = _setup(client)
    item = _add_item(client, bid, price=100, count=2)
    _assign(client, bid, item["id"], u1, requester=u1)  # all portions → u1 (=200)
    a1, _ = _alloc(client, bid, u1)
    assert a1 == 200.0
    _assign(client, bid, item["id"], u1, requester=u1, portion=1, assigned=False)
    a1, d = _alloc(client, bid, u1)
    assert a1 == 100.0
    assert d["unallocated_sum"] == 100.0
