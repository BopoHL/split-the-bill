import pytest
from fastapi.testclient import TestClient

def test_split_remainder_basic(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    client.post("/users/", json={"telegram_id": 2, "username": "p1"})
    client.post("/users/", json={"telegram_id": 3, "username": "p2"})
    
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "title": "Remainder Test", "include_owner": True})
    bill_data = resp_bill.json()
    bill_id = bill_data["id"]
    
    # Add participants
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 2})
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 3})
    
    # Get participant IDs
    resp_details = client.get(f"/bills/{bill_id}")
    participants = resp_details.json()["participants"]
    p_ids = [p["id"] for p in participants]
    
    # Split remainder among p1 and p2 (ID mapping: owner is p_ids[0], p1 is p_ids[1], p2 is p_ids[2])
    # Total sum is 100, unallocated is 100
    target_p_ids = [p_ids[1], p_ids[2]]
    response = client.post(f"/bills/{bill_id}/split-remainder", json={"participant_ids": target_p_ids})
    
    assert response.status_code == 200
    updated_participants = response.json()
    assert len(updated_participants) == 3 # Returns all participants now
    
    # p1 and p2 should each get 50.0, owner should have 0.0
    for p in updated_participants:
        if p["user_id"] in [2, 3]:
            assert p["allocated_amount"] == 50.0
        else:
            assert p["allocated_amount"] == 0.0

def test_split_remainder_with_existing_allocations(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    client.post("/users/", json={"telegram_id": 2, "username": "p1"})
    
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "include_owner": True})
    bill_id = resp_bill.json()["id"]
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 2})
    
    resp_details = client.get(f"/bills/{bill_id}")
    participants = resp_details.json()["participants"]
    owner_p_id = [p["id"] for p in participants if p["user_id"] == 1][0]
    p1_p_id = [p["id"] for p in participants if p["user_id"] == 2][0]
    
    # Manually assign 30 to owner
    client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": owner_p_id, "allocated_amount": 30.0})
    
    # Now unallocated is 70. Split it to p1.
    response = client.post(f"/bills/{bill_id}/split-remainder", json={"participant_ids": [p1_p_id]})
    assert response.status_code == 200
    p1_data = next(p for p in response.json() if p["id"] == p1_p_id)
    assert p1_data["allocated_amount"] == 70.0
    
    # Verify owner still has 30
    resp_final = client.get(f"/bills/{bill_id}")
    for p in resp_final.json()["participants"]:
        if p["id"] == owner_p_id:
            assert p["allocated_amount"] == 30.0

def test_split_remainder_division_remainder(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 0.1, "include_owner": True}) # 10 cents
    bill_id = resp_bill.json()["id"]
    
    client.post("/users/", json={"telegram_id": 2, "username": "p1"})
    client.post("/users/", json={"telegram_id": 3, "username": "p2"})
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 2})
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 3})
    
    resp_details = client.get(f"/bills/{bill_id}")
    p_ids = [p["id"] for p in resp_details.json()["participants"]]
    
    # Split 10 cents among 3 people. 10 / 3 = 3 cents each, 1 cent remainder.
    # Owner is p1, so owner should get 4 cents (0.04).
    response = client.post(f"/bills/{bill_id}/split-remainder", json={"participant_ids": p_ids})
    assert response.status_code == 200
    
    for p in response.json():
        if p["user_id"] == 1:
            assert p["allocated_amount"] == 0.04
        else:
            assert p["allocated_amount"] == 0.03

def test_split_remainder_invalid_inputs(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    # Empty list
    response = client.post(f"/bills/{bill_id}/split-remainder", json={"participant_ids": []})
    assert response.status_code == 400
    
    # Invalid participant ID
    response = client.post(f"/bills/{bill_id}/split-remainder", json={"participant_ids": [999]})
    assert response.status_code == 400

def test_split_remainder_skips_paid(client: TestClient):
    # Setup
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    client.post("/users/", json={"telegram_id": 2, "username": "p1"})
    client.post("/users/", json={"telegram_id": 3, "username": "p2"})
    
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "include_owner": True})
    bill_id = resp_bill.json()["id"]
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 2})
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 3})
    
    resp_details = client.get(f"/bills/{bill_id}")
    participants = resp_details.json()["participants"]
    p1 = next(p for p in participants if p["user_id"] == 2)
    p2 = next(p for p in participants if p["user_id"] == 3)
    
    # Assign 20 to p1 and mark as paid
    client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": p1["id"], "allocated_amount": 20.0})
    client.post(f"/bills/{bill_id}/participants/{p1['id']}/payment", json={"is_paid": True, "user_id": 1})
    
    # Now unallocated is 80. Split remainder among p1 and p2. 
    # p1 is paid, so all 80 should go to p2.
    response = client.post(f"/bills/{bill_id}/split-remainder", json={"participant_ids": [p1["id"], p2["id"]]})
    assert response.status_code == 200
    
    parts = response.json()
    p1_new = next(p for p in parts if p["user_id"] == 2)
    p2_new = next(p for p in parts if p["user_id"] == 3)
    
    assert p1_new["allocated_amount"] == 20.0 # Unchanged
    assert p2_new["allocated_amount"] == 80.0 # Got all the remainder

def test_payment_zero_amount_fails(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    resp_details = client.get(f"/bills/{bill_id}")
    part_id = resp_details.json()["participants"][0]["id"]
    
    # Attempt to mark as paid while amount is 0
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json={"is_paid": True, "user_id": 1})
    assert response.status_code == 400
    assert "Cannot confirm payment for zero or negative amount" in response.json()["detail"]

def test_split_equally_skips_paid(client: TestClient):
    client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    client.post("/users/", json={"telegram_id": 2, "username": "p1"})
    
    resp_bill = client.post("/bills/", json={"owner_id": 1, "total_sum": 100, "include_owner": True})
    bill_id = resp_bill.json()["id"]
    client.post(f"/bills/{bill_id}/participants", json={"user_id": 2})
    
    resp_details = client.get(f"/bills/{bill_id}")
    owner_p = next(p for p in resp_details.json()["participants"] if p["user_id"] == 1)
    p1_p = next(p for p in resp_details.json()["participants"] if p["user_id"] == 2)
    
    # Owner pays 40
    client.post(f"/bills/{bill_id}/assign-amount", json={"participant_id": owner_p["id"], "allocated_amount": 40.0})
    client.post(f"/bills/{bill_id}/participants/{owner_p['id']}/payment", json={"is_paid": True, "user_id": 1})
    
    # Split equally among all (including p1)
    # Total 100. Owner paid 40. Remaining 60 should go to p1 (unpaid).
    response = client.post(f"/bills/{bill_id}/split-equally")
    assert response.status_code == 200
    
    parts = response.json()
    owner_final = next(p for p in parts if p["user_id"] == 1)
    p1_final = next(p for p in parts if p["user_id"] == 2)
    
    assert owner_final["allocated_amount"] == 40.0
    assert p1_final["allocated_amount"] == 60.0
