"""Removing one receipt from a bill that may hold several.

The confirmation asks what should happen to the lines that receipt brought in,
so deletion has two modes, and either way the other receipts keep their items.
"""
import io

from fastapi.testclient import TestClient
from sqlmodel import select

from app.models import BillItem, FileAsset, ReceiptTask, ReceiptTaskStatus, ReceiptSource, StorageType


def _bill(client: TestClient, tg=700):
    owner = client.post("/users/", json={"telegram_id": tg, "username": "o"}).json()["id"]
    bill = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "include_owner": True, "expected_people": 2},
    ).json()
    return owner, bill["id"]


def _attach_scan(session, bill_id, owner, path=None, merchant="Chaikhana"):
    """A completed scan with its parse JSON, as the worker would leave it."""
    task = ReceiptTask(
        user_id=owner,
        filename="r.jpg",
        status=ReceiptTaskStatus.COMPLETED,
        source=ReceiptSource.PHOTO,
        bill_id=bill_id,
        llm_response=f'{{"title": "{merchant}", "total_sum": 100}}',
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    if path:
        path.write_bytes(b"jpeg")
        session.add(
            FileAsset(
                user_id=owner, bill_id=bill_id, receipt_task_id=task.id, path=str(path),
                size=4, mime_type="image/jpeg", storage_type=StorageType.LOCAL,
            )
        )
        session.commit()
    return task


def _add_scanned_item(session, bill_id, task_id, name, amount):
    session.add(
        BillItem(
            bill_id=bill_id, name=name, price=amount, count=1,
            item_sum=amount, receipt_task_id=task_id,
        )
    )
    session.commit()


def test_two_receipts_keep_their_own_items(client: TestClient, session):
    owner, bid = _bill(client, tg=701)
    first = _attach_scan(session, bid, owner, merchant="Chaikhana")
    second = _attach_scan(session, bid, owner, merchant="Coffee")
    _add_scanned_item(session, bid, first.id, "Plov", 5000)
    _add_scanned_item(session, bid, second.id, "Latte", 2000)

    detail = client.get(f"/bills/{bid}?user_id={owner}").json()
    receipts = {r["merchant_name"]: r for r in detail["receipts"]}
    assert receipts["Chaikhana"]["index"] == 1
    assert receipts["Coffee"]["index"] == 2
    assert receipts["Chaikhana"]["items_count"] == 1
    assert receipts["Coffee"]["items_count"] == 1


def test_deleting_a_receipt_takes_only_its_own_items(client: TestClient, session):
    owner, bid = _bill(client, tg=702)
    first = _attach_scan(session, bid, owner, merchant="Chaikhana")
    second = _attach_scan(session, bid, owner, merchant="Coffee")
    _add_scanned_item(session, bid, first.id, "Plov", 5000)
    _add_scanned_item(session, bid, second.id, "Latte", 2000)
    client.post(f"/bills/{bid}/items", json={"name": "Tip", "price": 10, "count": 1})

    resp = client.delete(f"/bills/{bid}/receipts/{first.id}?user_id={owner}&items=delete")
    assert resp.status_code == 200
    body = resp.json()

    names = {i["name"] for i in body["items"]}
    assert names == {"Latte", "Tip"}  # the other receipt and the manual line survive
    assert [r["merchant_name"] for r in body["receipts"]] == ["Coffee"]
    # And the surviving receipt is renumbered rather than leaving a gap.
    assert body["receipts"][0]["index"] == 1


def test_keeping_the_items_detaches_them_instead(client: TestClient, session):
    owner, bid = _bill(client, tg=703)
    task = _attach_scan(session, bid, owner)
    _add_scanned_item(session, bid, task.id, "Plov", 5000)

    resp = client.delete(f"/bills/{bid}/receipts/{task.id}?user_id={owner}&items=keep")
    assert resp.status_code == 200
    body = resp.json()

    assert [i["name"] for i in body["items"]] == ["Plov"]
    assert body["receipts"] == []
    # The line lives on with no receipt behind it.
    session.expire_all()
    item = session.exec(select(BillItem).where(BillItem.bill_id == bid)).first()
    assert item.receipt_task_id is None


def test_deleting_a_receipt_removes_its_photo_and_keeps_the_scan_log(
    client: TestClient, session, tmp_path
):
    owner, bid = _bill(client, tg=704)
    photo = tmp_path / "r.jpg"
    task = _attach_scan(session, bid, owner, path=photo)
    _add_scanned_item(session, bid, task.id, "Plov", 5000)

    client.delete(f"/bills/{bid}/receipts/{task.id}?user_id={owner}&items=delete")

    assert not photo.exists()
    assert session.exec(select(FileAsset)).all() == []
    # The scan's logs and rating outlive the receipt.
    session.expire_all()
    stored = session.exec(select(ReceiptTask)).all()
    assert len(stored) == 1 and stored[0].bill_id is None


def test_delete_impact_quotes_the_price_of_the_decision(client: TestClient, session):
    owner, bid = _bill(client, tg=705)
    task = _attach_scan(session, bid, owner)
    _add_scanned_item(session, bid, task.id, "Plov", 5000)
    _add_scanned_item(session, bid, task.id, "Salad", 3000)

    items = client.get(f"/bills/{bid}?user_id={owner}").json()["items"]
    seat = client.get(f"/bills/{bid}?user_id={owner}").json()["participants"][0]["id"]
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": items[0]["id"], "participant_id": seat, "is_assigned": True}]},
    )

    impact = client.get(f"/bills/{bid}/receipts/{task.id}/impact?user_id={owner}").json()
    assert impact["items_count"] == 2
    assert impact["total"] == 80.0
    assert impact["assigned_count"] == 1


def test_only_the_owner_can_remove_a_receipt(client: TestClient, session):
    owner, bid = _bill(client, tg=706)
    other = client.post("/users/", json={"telegram_id": 707, "username": "x"}).json()["id"]
    task = _attach_scan(session, bid, owner)

    assert client.delete(
        f"/bills/{bid}/receipts/{task.id}?user_id={other}"
    ).status_code == 403


def test_unknown_receipt_is_404(client: TestClient):
    owner, bid = _bill(client, tg=708)
    assert client.delete(f"/bills/{bid}/receipts/9999?user_id={owner}").status_code == 404
