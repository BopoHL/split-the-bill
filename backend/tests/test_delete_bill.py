from fastapi.testclient import TestClient
from sqlmodel import select

from app.models import ReceiptTask, ReceiptTaskStatus, FileAsset, StorageType, Bill, BillUser, BillItem


def test_owner_deletes_bill_softly(client: TestClient, session):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "owner"}).json()
    part = client.post("/users/", json={"telegram_id": 2, "username": "p"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
    ).json()
    bid = bill["id"]
    client.post(f"/bills/{bid}/participants", json={"user_id": part["id"]})
    client.post(f"/bills/{bid}/items", json={"name": "Pizza", "price": 50, "count": 1})
    # An AI-scan task and a stored file asset both reference the bill.
    session.add(
        ReceiptTask(
            user_id=owner["id"], filename="r.jpg",
            status=ReceiptTaskStatus.COMPLETED, bill_id=bid, scan_quality=5,
        )
    )
    session.add(
        FileAsset(
            user_id=owner["id"], bill_id=bid, path="/tmp/nope-does-not-exist.jpg",
            size=1, mime_type="image/jpeg", storage_type=StorageType.LOCAL,
        )
    )
    session.commit()

    # Non-owner can't delete.
    assert client.delete(f"/bills/{bid}?user_id={part['id']}").status_code == 403

    # Owner deletes.
    assert client.delete(f"/bills/{bid}?user_id={owner['id']}").status_code == 204

    # Gone from the API…
    assert client.get(f"/bills/{bid}?user_id={owner['id']}").status_code == 404
    assert all(b["id"] != bid for b in client.get(f"/users/{owner['id']}/bills").json())
    assert all(b["id"] != bid for b in client.get(f"/users/{part['id']}/bills").json())

    # …but everything is still on disk, which is what makes restore possible.
    session.expire_all()
    stored = session.exec(select(Bill).where(Bill.id == bid)).first()
    assert stored is not None and stored.deleted_at is not None
    assert len(session.exec(select(BillItem).where(BillItem.bill_id == bid)).all()) == 1
    assert len(session.exec(select(BillUser).where(BillUser.bill_id == bid)).all()) == 2

    # The scan task keeps pointing at the bill now — it is needed to restore it.
    tasks = session.exec(select(ReceiptTask)).all()
    assert len(tasks) == 1 and tasks[0].bill_id == bid and tasks[0].scan_quality == 5
    assert len(session.exec(select(FileAsset)).all()) == 1


def test_deleted_bill_is_unreachable_by_invite(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 5, "username": "o"}).json()
    guest = client.post("/users/", json={"telegram_id": 6, "username": "g"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
    ).json()

    client.delete(f"/bills/{bill['id']}?user_id={owner['id']}")

    resp = client.post(
        "/bills/join-by-token",
        json={"token": bill["public_token"], "user_id": guest["id"]},
    )
    assert resp.status_code == 404


def test_delete_is_idempotent_from_the_api(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 7, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
    ).json()

    assert client.delete(f"/bills/{bill['id']}?user_id={owner['id']}").status_code == 204
    # A second delete sees no bill at all.
    assert client.delete(f"/bills/{bill['id']}?user_id={owner['id']}").status_code == 404


def test_restore_brings_the_bill_back(client: TestClient, session):
    from app.repositories.bill_repo import BillRepository
    from app.repositories.user_repo import UserRepository
    from app.services.bill_core_service import BillCoreService

    owner = client.post("/users/", json={"telegram_id": 8, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
    ).json()
    client.post(f"/bills/{bill['id']}/items", json={"name": "Tea", "price": 40, "count": 1})
    client.delete(f"/bills/{bill['id']}?user_id={owner['id']}")

    service = BillCoreService(BillRepository(session), UserRepository(session))
    service.restore_bill(bill["id"])

    detail = client.get(f"/bills/{bill['id']}?user_id={owner['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["items"]) == 1


def test_delete_missing_bill_404(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o"}).json()
    assert client.delete(f"/bills/99999?user_id={owner['id']}").status_code == 404
def test_purge_removes_photos_of_finished_bills_only(client: TestClient, session, tmp_path):
    from datetime import datetime, timedelta
    from sqlalchemy import update
    from app.repositories.bill_repo import BillRepository
    from app.repositories.user_repo import UserRepository
    from app.services.bill_core_service import BillCoreService

    owner = client.post("/users/", json={"telegram_id": 9, "username": "o"}).json()

    def make_bill_with_photo(name: str) -> tuple[int, str]:
        bill = client.post(
            "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
        ).json()
        photo = tmp_path / name
        photo.write_bytes(b"jpeg")
        asset = FileAsset(
            user_id=owner["id"], bill_id=bill["id"], path=str(photo),
            size=4, mime_type="image/jpeg", storage_type=StorageType.LOCAL,
        )
        asset.created_at = datetime.utcnow() - timedelta(days=40)
        session.add(asset)
        session.commit()
        return bill["id"], str(photo)

    open_id, open_photo = make_bill_with_photo("open.jpg")
    closed_id, closed_photo = make_bill_with_photo("closed.jpg")
    deleted_id, deleted_photo = make_bill_with_photo("deleted.jpg")

    client.post(f"/bills/{closed_id}/close", json={"user_id": owner["id"]})
    client.delete(f"/bills/{deleted_id}?user_id={owner['id']}")

    service = BillCoreService(BillRepository(session), UserRepository(session))
    assert service.purge_receipt_files(older_than_days=30, pro_older_than_days=90) == 2

    import os
    assert os.path.exists(open_photo)          # still in use
    assert not os.path.exists(closed_photo)
    assert not os.path.exists(deleted_photo)
    assert len(session.exec(select(FileAsset)).all()) == 1

    # Left open and untouched for half a year: nobody is coming back to it.
    from app.models import Bill
    session.execute(update(Bill).where(Bill.id == open_id).values(updated_at=datetime.utcnow() - timedelta(days=181)))
    session.commit()
    assert service.purge_receipt_files(older_than_days=30, pro_older_than_days=90) == 1
    assert not os.path.exists(open_photo)


def test_purge_keeps_recent_photos(client: TestClient, session, tmp_path):
    from app.repositories.bill_repo import BillRepository
    from app.repositories.user_repo import UserRepository
    from app.services.bill_core_service import BillCoreService

    owner = client.post("/users/", json={"telegram_id": 10, "username": "o"}).json()
    bill = client.post(
        "/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}
    ).json()
    photo = tmp_path / "fresh.jpg"
    photo.write_bytes(b"jpeg")
    session.add(
        FileAsset(
            user_id=owner["id"], bill_id=bill["id"], path=str(photo),
            size=4, mime_type="image/jpeg", storage_type=StorageType.LOCAL,
        )
    )
    session.commit()
    client.delete(f"/bills/{bill['id']}?user_id={owner['id']}")

    service = BillCoreService(BillRepository(session), UserRepository(session))
    assert service.purge_receipt_files(older_than_days=30, pro_older_than_days=90) == 0
    assert photo.exists()


def test_a_pro_owner_keeps_photos_for_the_longer_term(client: TestClient, session, tmp_path):
    from datetime import datetime, timedelta
    from app.models import ProGrant
    from app.repositories.bill_repo import BillRepository
    from app.repositories.user_repo import UserRepository
    from app.services.bill_core_service import BillCoreService

    owner = client.post("/users/", json={"telegram_id": 11, "username": "o"}).json()
    session.add(ProGrant(user_id=owner["id"], source="promo", starts_at=datetime.utcnow() - timedelta(days=1), ends_at=datetime.utcnow() + timedelta(days=30)))
    photos = []
    for age in (40, 100):
        bill = client.post("/bills/", json={"owner_id": owner["id"], "total_sum": 100, "include_owner": True}).json()
        photo = tmp_path / f"{age}.jpg"
        photo.write_bytes(b"jpeg")
        asset = FileAsset(
            user_id=owner["id"], bill_id=bill["id"], path=str(photo),
            size=4, mime_type="image/jpeg", storage_type=StorageType.LOCAL,
        )
        asset.created_at = datetime.utcnow() - timedelta(days=age)
        session.add(asset)
        session.commit()
        client.delete(f"/bills/{bill['id']}?user_id={owner['id']}")
        photos.append(photo)

    service = BillCoreService(BillRepository(session), UserRepository(session))
    assert service.purge_receipt_files(older_than_days=30, pro_older_than_days=90) == 1
    assert photos[0].exists() and not photos[1].exists()
