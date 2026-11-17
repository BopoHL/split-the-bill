from fastapi.testclient import TestClient


def _closed_bill(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "owner"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
    ).json()
    bid = bill["id"]
    assert client.post(f"/bills/{bid}/close", json={"user_id": owner["id"]}).status_code == 200
    assert client.get(f"/bills/{bid}?user_id={owner['id']}").json()["status"] == "closed"
    return owner["id"], bid


def test_owner_reopens_closed_bill(client: TestClient):
    owner_id, bid = _closed_bill(client)
    resp = client.post(f"/bills/{bid}/reopen", json={"user_id": owner_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"
    assert client.get(f"/bills/{bid}?user_id={owner_id}").json()["status"] == "open"


def test_non_owner_cannot_reopen(client: TestClient):
    owner_id, bid = _closed_bill(client)
    other = client.post("/users/", json={"telegram_id": 2, "username": "x"}).json()
    assert client.post(f"/bills/{bid}/reopen", json={"user_id": other["id"]}).status_code == 403
