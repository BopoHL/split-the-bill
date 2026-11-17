import io

from fastapi.testclient import TestClient
from PIL import Image


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (50, 30), (10, 120, 200)).save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_owner_attaches_receipt_to_bill(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    bill = client.post(
        "/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Manual"}
    ).json()
    bill_id = bill["id"]

    # No receipt yet.
    assert client.get(f"/bills/{bill_id}?user_id=1").json()["has_receipt"] is False

    resp = client.post(
        f"/bills/{bill_id}/receipt",
        data={"user_id": 1},
        files={"file": ("receipt.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 201

    # Flagged and served (re-encoded to jpeg by the compressor).
    assert client.get(f"/bills/{bill_id}?user_id=1").json()["has_receipt"] is True
    img = client.get(f"/bills/{bill_id}/receipt?user_id=1")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"


def test_non_owner_cannot_attach_receipt(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    client.post("/users/", json={"telegram_id": 2, "username": "intruder"})
    bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100}).json()

    resp = client.post(
        f"/bills/{bill['id']}/receipt",
        data={"user_id": 2},
        files={"file": ("receipt.png", _png_bytes(), "image/png")},
    )
    assert resp.status_code == 403


def test_attach_rejects_non_image(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100}).json()

    resp = client.post(
        f"/bills/{bill['id']}/receipt",
        data={"user_id": 1},
        files={"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert resp.status_code == 400


def test_attached_photo_becomes_a_receipt_on_the_bill(client: TestClient):
    """A photo the user chose not to have recognised is still a receipt.

    It has to appear in the list, otherwise there is nowhere to open or remove it.
    """
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    bill_id = client.post(
        "/bills/", json={"owner_id": 1, "total_sum": 100, "include_owner": True}
    ).json()["id"]

    client.post(
        f"/bills/{bill_id}/receipt",
        data={"user_id": 1},
        files={"file": ("receipt.png", _png_bytes(), "image/png")},
    )

    receipts = client.get(f"/bills/{bill_id}?user_id=1").json()["receipts"]
    assert len(receipts) == 1
    assert receipts[0]["items_count"] == 0
    assert receipts[0]["has_photo"] is True

    # And it can be removed like any other receipt.
    task_id = receipts[0]["task_id"]
    resp = client.delete(f"/bills/{bill_id}/receipts/{task_id}?user_id=1&items=delete")
    assert resp.status_code == 200
    assert resp.json()["receipts"] == []
