from fastapi.testclient import TestClient


def _bill(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o"}).json()["id"]
    bid = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "title": "T", "include_owner": True},
    ).json()["id"]
    return owner, bid


def test_edit_item_updates_fields_and_total(client: TestClient):
    owner, bid = _bill(client)
    iid = client.post(f"/bills/{bid}/items", json={"name": "A", "price": 100, "count": 1}).json()["id"]

    r = client.patch(f"/bills/{bid}/items/{iid}", json={"name": "A2", "price": 50, "count": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "A2"
    assert body["price"] == 50
    assert body["count"] == 3
    assert body["item_sum"] == 150

    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    assert detail["total_sum"] == 150


def test_edit_item_shared_flag_switches_to_by_items(client: TestClient):
    owner, bid = _bill(client)
    iid = client.post(f"/bills/{bid}/items", json={"name": "Service", "price": 100, "count": 1}).json()["id"]

    client.patch(f"/bills/{bid}/items/{iid}", json={"is_shared_globally": True})

    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    assert detail["split_type"] == "by_items"
    assert next(i for i in detail["items"] if i["id"] == iid)["is_shared_globally"] is True


def test_edit_unknown_item_404(client: TestClient):
    _owner, bid = _bill(client)
    assert client.patch(f"/bills/{bid}/items/99999", json={"name": "x"}).status_code == 404
