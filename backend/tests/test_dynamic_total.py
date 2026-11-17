from fastapi.testclient import TestClient


def test_total_tracks_items_on_add_and_delete(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o"}).json()["id"]
    bid = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "title": "T", "include_owner": True},
    ).json()["id"]

    client.post(f"/bills/{bid}/items", json={"name": "A", "price": 100, "count": 1})
    client.post(f"/bills/{bid}/items", json={"name": "B", "price": 50, "count": 2})

    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    # Total derived from items: 100 + (50*2) = 200
    assert detail["total_sum"] == 200

    item_a = next(i for i in detail["items"] if i["name"] == "A")
    client.delete(f"/bills/{bid}/items/{item_a['id']}")

    after = client.get(f"/bills/{bid}?user_id={owner}").json()
    assert after["total_sum"] == 100
    assert after["unallocated_sum"] == 100


def test_total_zeroes_when_last_item_deleted(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 2, "username": "o2"}).json()["id"]
    bid = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "title": "T", "include_owner": True},
    ).json()["id"]

    item = client.post(f"/bills/{bid}/items", json={"name": "Solo", "price": 500, "count": 1}).json()
    assert client.get(f"/bills/{bid}?user_id={owner}").json()["total_sum"] == 500

    # Deleting the last item must bring the total (and remainder) to 0.
    client.delete(f"/bills/{bid}/items/{item['id']}")
    after = client.get(f"/bills/{bid}?user_id={owner}").json()
    assert after["total_sum"] == 0
    assert after["unallocated_sum"] == 0
    assert after["items"] == []
