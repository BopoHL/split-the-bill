import pytest
from fastapi.testclient import TestClient

def test_split_equally(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    client.post("/users/", json={"telegram_id": 2, "username": "p1"})
    client.post("/users/", json={"telegram_id": 3, "username": "p2"})
    
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Split Test", "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    # Add 2 more participants (total 3 including owner)
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 2})
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 3})
    
    # Split equally
    response = client.post(f"/bills/{bill_id}/split-equally")
    assert response.status_code == 200
    participants = response.json()
    assert len(participants) == 3
    
    # 100 / 3 = 33.33 each, but owner gets remainder
    # Tiins: 10000 / 3 = 3333, remainder 1. 
    # Owner (user_id 1) should get 3333 + 1 = 3334 tiins = 33.34
    # Others get 33.33
    for p in participants:
        if p["user_id"] == 1:
            assert p["allocated_amount"] == 33.34
        else:
            assert p["allocated_amount"] == 33.33

def test_assign_amount(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Assign Test", "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    # Get participant ID for owner
    resp_details = client.get(f"/bills/{bill_id}")
    part_id = resp_details.json()["participants"][0]["id"]
    
    # Assign amount
    assign_data = {
        "participant_id": part_id,
        "allocated_amount": 50.0
    }
    response = client.post(f"/bills/{bill_id}/assign-amount", json=assign_data)
    assert response.status_code == 200
    assert response.json()["allocated_amount"] == 50.0
    
    # Check unallocated sum in bill
    resp_final = client.get(f"/bills/{bill_id}")
    assert resp_final.json()["unallocated_sum"] == 50.0

def test_assign_excess_amount(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Excess Test", "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    resp_details = client.get(f"/bills/{bill_id}")
    part_id = resp_details.json()["participants"][0]["id"]
    
    response = client.post(f"/bills/{bill_id}/assign-amount", json={
        "participant_id": part_id,
        "allocated_amount": 150.0
    })
    assert response.status_code == 400
    assert "Amount exceeds unallocated sum" in response.json()["detail"]
