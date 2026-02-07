import pytest
from fastapi.testclient import TestClient

def test_create_and_get_bill(client: TestClient):
    # Create user
    client.post("/users/", json={"telegram_id": 100, "username": "tester"})
    
    # Create bill
    bill_data = {
        "owner_id": 1,
        "total_sum": 150.50,
        "title": "Core Test Bill",
        "payment_details": "Card 1234",
        "include_owner": True
    }
    response = client.post("/bills/", json=bill_data)
    assert response.status_code == 200
    bill = response.json()
    assert bill["title"] == "Core Test Bill"
    assert bill["total_sum"] == 150.50
    assert bill["payment_details"] == "Card 1234"
    assert bill["participants_count"] == 1

    # Get details
    resp_details = client.get(f"/bills/{bill['id']}")
    assert resp_details.status_code == 200
    details = resp_details.json()
    assert details["id"] == bill["id"]
    assert len(details["participants"]) == 1

def test_get_non_existent_bill(client: TestClient):
    response = client.get("/bills/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Bill not found"

def test_get_user_bills(client: TestClient):
    # Create user
    client.post("/users/", json={"telegram_id": 200, "username": "user_with_bills"})
    user_id = 1
    
    # Create 2 bills
    client.post("/bills/", json={"owner_id": user_id, "total_sum": 100, "title": "Bill 1"})
    client.post("/bills/", json={"owner_id": user_id, "total_sum": 200, "title": "Bill 2"})
    
    response = client.get(f"/users/{user_id}/bills")
    assert response.status_code == 200
    bills = response.json()
    assert len(bills) >= 2
