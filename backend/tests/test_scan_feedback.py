"""Scan quality is rated per receipt, not per bill.

A bill can hold several receipts scanned with wildly different results, so one
rating for the whole thing said nothing useful. A photo attached without
recognition has nothing to rate at all.
"""
from fastapi.testclient import TestClient

from app.models import ReceiptSource, ReceiptTask, ReceiptTaskStatus


def _make_scanned_bill(client: TestClient, session, source=ReceiptSource.PHOTO, tg=1):
    owner = client.post("/users/", json={"telegram_id": tg, "username": "owner"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "title": "Scanned"}
    ).json()
    task = ReceiptTask(
        user_id=owner["id"],
        filename="r.jpg",
        status=ReceiptTaskStatus.COMPLETED,
        source=source,
        bill_id=bill["id"],
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return owner["id"], bill["id"], task.id


def test_receipts_carry_their_own_rating(client: TestClient, session):
    owner_id, bill_id, task_id = _make_scanned_bill(client, session)
    detail = client.get(f"/bills/{bill_id}?user_id={owner_id}").json()
    assert detail["receipts"][0]["quality"] is None
    assert detail["receipts"][0]["source"] == "photo"


def test_owner_rates_one_receipt(client: TestClient, session):
    owner_id, bill_id, task_id = _make_scanned_bill(client, session)
    resp = client.post(
        f"/bills/{bill_id}/receipts/{task_id}/feedback",
        json={"rating": 4, "user_id": owner_id},
    )
    assert resp.status_code == 200

    detail = client.get(f"/bills/{bill_id}?user_id={owner_id}").json()
    assert detail["receipts"][0]["quality"] == 4


def test_each_receipt_is_rated_separately(client: TestClient, session):
    owner_id, bill_id, first = _make_scanned_bill(client, session, tg=2)
    second = ReceiptTask(
        user_id=owner_id, filename="r2.jpg", status=ReceiptTaskStatus.COMPLETED,
        source=ReceiptSource.SOLIQ_QR, bill_id=bill_id,
    )
    session.add(second)
    session.commit()
    session.refresh(second)

    client.post(
        f"/bills/{bill_id}/receipts/{first}/feedback", json={"rating": 2, "user_id": owner_id}
    )
    client.post(
        f"/bills/{bill_id}/receipts/{second.id}/feedback", json={"rating": 5, "user_id": owner_id}
    )

    ratings = {
        r["task_id"]: r["quality"]
        for r in client.get(f"/bills/{bill_id}?user_id={owner_id}").json()["receipts"]
    }
    assert ratings == {first: 2, second.id: 5}


def test_an_unscanned_photo_has_nothing_to_rate(client: TestClient, session):
    owner_id, bill_id, task_id = _make_scanned_bill(
        client, session, source=ReceiptSource.MANUAL_PHOTO, tg=3
    )
    resp = client.post(
        f"/bills/{bill_id}/receipts/{task_id}/feedback",
        json={"rating": 3, "user_id": owner_id},
    )
    assert resp.status_code == 400


def test_rating_validation_and_auth(client: TestClient, session):
    owner_id, bill_id, task_id = _make_scanned_bill(client, session, tg=4)
    intruder = client.post("/users/", json={"telegram_id": 99, "username": "x"}).json()

    assert client.post(
        f"/bills/{bill_id}/receipts/{task_id}/feedback",
        json={"rating": 9, "user_id": owner_id},
    ).status_code == 400
    assert client.post(
        f"/bills/{bill_id}/receipts/{task_id}/feedback",
        json={"rating": 3, "user_id": intruder["id"]},
    ).status_code == 403
    assert client.post(
        f"/bills/{bill_id}/receipts/999999/feedback",
        json={"rating": 3, "user_id": owner_id},
    ).status_code == 404
