import pytest
from fastapi.testclient import TestClient

def test_payment_flow(client: TestClient):
    # 1. Create owner and participant users
    resp_owner = client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    resp_part = client.post("/users/", json={"telegram_id": 2, "username": "participant"})
    
    owner_id = resp_owner.json()["id"]
    participant_user_id = resp_part.json()["id"]
    
    # 2. Create a bill
    bill_data = {
        "owner_id": owner_id,
        "total_sum": 1000.0,
        "title": "Payment Test Bill",
        "include_owner": True
    }
    response = client.post("/bills/", json=bill_data)
    bill = response.json()
    bill_id = bill["id"]

    # 3. Add participant
    participant_data = {
        "user_id": participant_user_id
    }
    response = client.post(f"/bills/{bill_id}/participants", json=participant_data)
    participants = response.json()
    # Find the recently added participant
    participant = next(p for p in participants if p["user_id"] == participant_user_id)
    part_id = participant["id"]

    # 3.1 Assign manual amount
    client.post(f"/bills/{bill_id}/assign-amount", json={
        "participant_id": part_id,
        "allocated_amount": 500.0
    })

    # 4. Participant marks themselves as paid (Success)
    payment_data = {
        "is_paid": True,
        "user_id": participant_user_id
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 200
    assert response.json()["is_paid"] is True

    # 5. Participant tries to mark as unpaid (Failure)
    payment_data = {
        "is_paid": False,
        "user_id": participant_user_id
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 403

    # 6. Owner marks as unpaid (Success)
    payment_data = {
        "is_paid": False,
        "user_id": owner_id
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 200
    assert response.json()["is_paid"] is False

    # 7. No-op check (Return 200 if same status)
    payment_data = {
        "is_paid": False,
        "user_id": owner_id
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 200

    # 8. Random user tries to change status (Failure)
    payment_data = {
        "is_paid": True,
        "user_id": 999
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 403

def test_add_guest_participant_resets_split_type(client: TestClient):
    resp_user = client.post("/users/", json={"telegram_id": 1, "username": "owner"})
    owner_id = resp_user.json()["id"]
    resp_bill = client.post("/bills/", json={"owner_id": owner_id, "total_sum": 100, "title": "Reset Test"})
    bill_id = resp_bill.json()["id"]
    
    # Manually set to EQUALLY via split route
    client.post(f"/bills/{bill_id}/participants", json={"guest_name": "P1"})
    client.post(f"/bills/{bill_id}/split-equally")
    
    # Verify it is EQUALLY
    assert client.get(f"/bills/{bill_id}").json()["split_type"] == "equally"
    
    # Add another participant
    client.post(f"/bills/{bill_id}/participants", json={"guest_name": "Ghost User"})
    
    # Verify it is now EQUALLY (because auto-split happened and kept the mode)
    assert client.get(f"/bills/{bill_id}").json()["split_type"] == "equally"

def test_remove_participant(client: TestClient):
    # 1. Setup: Create users and a bill
    # Using unique telegram IDs to avoid conflicts if DB is not cleared
    resp_owner = client.post("/users/", json={"telegram_id": 100, "username": "owner"})
    resp_p1 = client.post("/users/", json={"telegram_id": 101, "username": "p1"})
    resp_p2 = client.post("/users/", json={"telegram_id": 102, "username": "p2"})
    
    owner_id = resp_owner.json()["id"]
    p1_id = resp_p1.json()["id"]
    p2_id = resp_p2.json()["id"]
    
    # Bill with owner (include_owner=True)
    resp_bill = client.post("/bills/", json={"owner_id": owner_id, "total_sum": 300, "title": "Removal Test", "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    # 2. Add participants
    client.post(f"/bills/{bill_id}/participants", json={"user_id": p1_id})
    client.post(f"/bills/{bill_id}/participants", json={"user_id": p2_id})
    
    # Trigger equal split
    client.post(f"/bills/{bill_id}/split-equally")
    
    # Verify initial split (3 participants: owner, p1, p2)
    bill = client.get(f"/bills/{bill_id}").json()
    assert len(bill["participants"]) == 3
    for p in bill["participants"]:
        assert p["allocated_amount"] == 100
    
    p2_participant = next(p for p in bill["participants"] if p["user_id"] == p2_id)
    p2_participant_id = p2_participant["id"]
    
    # 3. Owner removes p2
    response = client.request(
        "DELETE", 
        f"/bills/{bill_id}/participants/{p2_participant_id}",
        json={"user_id": owner_id}
    )
    assert response.status_code == 200
    bill_after_removal = response.json()
    assert len(bill_after_removal["participants"]) == 2
    
    # 4. Verify re-split happened (300 / 2 = 150 each)
    for p in bill_after_removal["participants"]:
        assert p["allocated_amount"] == 150
    
    # 5. Unauthorized removal attempt
    p1_participant = next(p for p in bill_after_removal["participants"] if p["user_id"] == p1_id)
    p1_participant_id = p1_participant["id"]
    
    response = client.request(
        "DELETE",
        f"/bills/{bill_id}/participants/{p1_participant_id}",
        json={"user_id": 999} # Random user
    )
    assert response.status_code == 403
