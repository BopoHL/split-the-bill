from fastapi.testclient import TestClient


def _mk_user(client: TestClient, tg: int) -> int:
    return client.post("/users/", json={"telegram_id": tg, "username": f"u{tg}"}).json()["id"]


def test_payment_methods_crud(client: TestClient):
    uid = _mk_user(client, 1)

    # Starts empty.
    assert client.get(f"/users/{uid}/payment-methods/").json() == []

    # Create returns the decrypted value back to its owner.
    r = client.post(
        f"/users/{uid}/payment-methods/",
        json={"value": "1234 5678 9012 3456", "label": "Tinkoff"},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["value"] == "1234 5678 9012 3456"
    assert created["label"] == "Tinkoff"
    method_id = created["id"]

    # Listed back, decrypted.
    listed = client.get(f"/users/{uid}/payment-methods/").json()
    assert len(listed) == 1
    assert listed[0]["value"] == "1234 5678 9012 3456"

    # Delete.
    assert client.delete(f"/users/{uid}/payment-methods/{method_id}").status_code == 204
    assert client.get(f"/users/{uid}/payment-methods/").json() == []


def test_payment_value_is_encrypted_at_rest():
    # Round-trip + random nonce means two encryptions of the same value differ.
    from app.utils import crypto

    a = crypto.encrypt("secret card")
    b = crypto.encrypt("secret card")
    assert a != b
    assert "secret card" not in a
    assert crypto.decrypt(a) == "secret card"


def test_outside_local_dev_a_missing_key_is_an_error(monkeypatch):
    """The fallback key is in the code; nothing real may be sealed with it."""
    import base64

    import pytest

    from app.utils import crypto

    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.delenv("PAYMENT_ENC_KEY", raising=False)
    with pytest.raises(RuntimeError):
        crypto.require_key()
    with pytest.raises(RuntimeError):
        crypto.encrypt("8600 1234")

    monkeypatch.setenv("PAYMENT_ENC_KEY", base64.b64encode(b"k" * 32).decode())
    assert crypto.decrypt(crypto.encrypt("8600 1234")) == "8600 1234"


def test_payment_methods_authorization(client: TestClient):
    # Unknown user can't create — there is no identity to authenticate as.
    assert client.post("/users/99999/payment-methods/", json={"value": "x"}).status_code == 401

    # A user cannot delete someone else's method.
    owner = _mk_user(client, 2)
    other = _mk_user(client, 3)
    mid = client.post(f"/users/{owner}/payment-methods/", json={"value": "x"}).json()["id"]
    assert client.delete(f"/users/{other}/payment-methods/{mid}").status_code == 404

    # Empty value rejected.
    assert client.post(f"/users/{owner}/payment-methods/", json={"value": "   "}).status_code == 400


def test_a_card_used_on_a_bill_can_still_be_removed_from_the_picker(client: TestClient):
    """Bills reference the row, so a hard delete tripped the FK and «delete» did
    nothing. It disappears from the picker but stays readable on past bills."""
    user = client.post("/users/", json={"telegram_id": 400, "username": "u"}).json()
    method = client.post(
        f"/users/{user['id']}/payment-methods",
        json={"value": "8600 1111 2222 3333"},
    ).json()

    bill = client.post(
        "/bills/",
        json={
            "owner_id": user["id"], "total_sum": 100, "include_owner": True,
            "payment_details": "8600 1111 2222 3333",
        },
    ).json()

    assert client.delete(
        f"/users/{user['id']}/payment-methods/{method['id']}"
    ).status_code == 204

    # Gone from the picker…
    assert client.get(f"/users/{user['id']}/payment-methods").json() == []
    # …but the bill still shows what it was paid to.
    detail = client.get(f"/bills/{bill['id']}?user_id={user['id']}").json()
    assert detail["payment_details"] == "8600 1111 2222 3333"

    # And it can't be removed twice.
    assert client.delete(
        f"/users/{user['id']}/payment-methods/{method['id']}"
    ).status_code == 404


def test_reusing_the_same_card_does_not_pile_up_duplicates(client: TestClient):
    user = client.post("/users/", json={"telegram_id": 401, "username": "u2"}).json()
    for _ in range(3):
        client.post(
            "/bills/",
            json={
                "owner_id": user["id"], "total_sum": 10, "include_owner": True,
                "payment_details": "8600 4444 5555 6666",
            },
        )
    assert len(client.get(f"/users/{user['id']}/payment-methods").json()) == 1


def test_saving_a_card_twice_keeps_one(client: TestClient):
    uid = _mk_user(client, 7)

    first = client.post(f"/users/{uid}/payment-methods/", json={"value": "8600 1111 2222 3333"}).json()
    again = client.post(f"/users/{uid}/payment-methods/", json={"value": "8600 1111 2222 3333"}).json()

    assert again["id"] == first["id"]
    assert len(client.get(f"/users/{uid}/payment-methods/").json()) == 1


def test_a_card_put_on_a_bill_and_saved_is_one_card(client: TestClient):
    uid = _mk_user(client, 8)
    bill = client.post("/bills/", json={"owner_id": uid, "total_sum": 100}).json()

    client.patch(f"/bills/{bill['id']}", json={"payment_details": "8600 4444 5555 6666", "user_id": uid})
    client.post(f"/users/{uid}/payment-methods/", json={"value": "8600 4444 5555 6666"})

    assert [m["value"] for m in client.get(f"/users/{uid}/payment-methods/").json()] == ["8600 4444 5555 6666"]
