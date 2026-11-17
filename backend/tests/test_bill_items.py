import pytest
from fastapi.testclient import TestClient

def test_add_items_to_bill_with_sum(client: TestClient):
    # Setup: Create user and bill
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 1000, "title": "Item Sum Test"})
    bill_id = resp_bill.json()["id"]

    # Add item
    item_data = {
        "name": "Pizza",
        "price": 450.0,
        "count": 2
    }
    response = client.post(f"/bills/{bill_id}/items", json=item_data)
    assert response.status_code == 200
    item = response.json()
    assert item["name"] == "Pizza"
    assert item["price"] == 450.0
    assert item["count"] == 2
    assert item["item_sum"] == 900.0  # 450 * 2

    # Check bill details has item with sum
    resp_details = client.get(f"/bills/{bill_id}?user_id=1")
    details = resp_details.json()
    assert len(details["items"]) == 1
    assert details["items"][0]["item_sum"] == 900.0

def test_delete_bill_item(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 1000, "title": "Delete Test"})
    bill_id = resp_bill.json()["id"]
    
    # Add item
    resp_item = client.post(f"/bills/{bill_id}/items", json={"name": "Water", "price": 50, "count": 1})
    item_id = resp_item.json()["id"]
    
    # Delete item
    response = client.delete(f"/bills/{bill_id}/items/{item_id}")
    assert response.status_code == 204
    
    # Verify item is gone
    resp_details = client.get(f"/bills/{bill_id}?user_id=1")
    assert len(resp_details.json()["items"]) == 0

def test_delete_non_existent_item(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Fail Delete"})
    bill_id = resp_bill.json()["id"]
    
    response = client.delete(f"/bills/{bill_id}/items/999")
    assert response.status_code == 404


def test_items_say_which_receipt_they_came_from(client: TestClient, session):
    """The client groups the list by this — without it nothing grouped."""
    from app.models import ReceiptSource, ReceiptTask, ReceiptTaskStatus

    owner = client.post("/users/", json={"telegram_id": 610, "username": "o"}).json()["id"]
    bill_id = client.post(
        "/bills/", json={"owner_id": owner, "total_sum": 0, "include_owner": True}
    ).json()["id"]

    task = ReceiptTask(
        user_id=owner, filename="r.jpg", status=ReceiptTaskStatus.COMPLETED,
        source=ReceiptSource.PHOTO, bill_id=bill_id,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    from app.models import BillItem

    session.add(
        BillItem(bill_id=bill_id, name="Plov", price=100, count=1, item_sum=100,
                 receipt_task_id=task.id)
    )
    session.commit()
    client.post(f"/bills/{bill_id}/items", json={"name": "Tip", "price": 10, "count": 1})

    items = {i["name"]: i for i in client.get(f"/bills/{bill_id}?user_id={owner}").json()["items"]}
    assert items["Plov"]["receipt_task_id"] == task.id
    assert items["Tip"]["receipt_task_id"] is None
