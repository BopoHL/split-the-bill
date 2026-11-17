import pytest
from fastapi.testclient import TestClient


def test_assign_amount(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Assign Test", "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    # Get participant ID for owner
    resp_details = client.get(f"/bills/{bill_id}?user_id=1")
    part_id = resp_details.json()["participants"][0]["id"]
    
    # Assign amount
    assign_data = {
        "participant_id": part_id,
        "allocated_amount": 50.0
    }
    response = client.post(f"/bills/{bill_id}/assign-amount", json=assign_data)
    assert response.status_code == 200
    # The endpoint now returns the full recomputed bill.
    data = response.json()
    assert data["unallocated_sum"] == 50.0
    assigned = next(p for p in data["participants"] if p["id"] == part_id)
    assert assigned["allocated_amount"] == 50.0

def test_assign_excess_amount(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Excess Test", "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    resp_details = client.get(f"/bills/{bill_id}?user_id=1")
    part_id = resp_details.json()["participants"][0]["id"]
    
    response = client.post(f"/bills/{bill_id}/assign-amount", json={
        "participant_id": part_id,
        "allocated_amount": 150.0
    })
    assert response.status_code == 400
    assert "Amount exceeds unallocated sum" in response.json()["detail"]
