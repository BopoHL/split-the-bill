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
    assert next(p for p in response.json()["participants"] if p["id"] == part_id)["is_paid"] is True

    # 5. Participant cancels their OWN payment — allowed while the bill is open
    payment_data = {
        "is_paid": False,
        "user_id": participant_user_id
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 200
    assert next(p for p in response.json()["participants"] if p["id"] == part_id)["is_paid"] is False

    # 5b. ...and can re-confirm it again (free toggle while open)
    payment_data = {
        "is_paid": True,
        "user_id": participant_user_id
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 200
    assert next(p for p in response.json()["participants"] if p["id"] == part_id)["is_paid"] is True

    # 6. The owner can take a claimed participant's payment back when the
    # money never arrived, but cannot confirm one for them.
    response = client.post(
        f"/bills/{bill_id}/participants/{part_id}/payment", json={"is_paid": False, "user_id": owner_id}
    )
    assert response.status_code == 200
    assert next(p for p in response.json()["participants"] if p["id"] == part_id)["is_paid"] is False

    response = client.post(
        f"/bills/{bill_id}/participants/{part_id}/payment", json={"is_paid": True, "user_id": owner_id}
    )
    assert response.status_code == 403

    # 7. Participant marks themselves as unpaid (Success)
    payment_data = {
        "is_paid": False,
        "user_id": participant_user_id
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 200
    assert next(p for p in response.json()["participants"] if p["id"] == part_id)["is_paid"] is False

    # 7b. No-op check (Return 200 if the same authorized user repeats it)
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 200

    # 8. Random user tries to change status (Failure)
    stranger = client.post(
        "/users/", json={"telegram_id": 999, "username": "stranger"}
    ).json()["id"]
    payment_data = {
        "is_paid": True,
        "user_id": stranger
    }
    response = client.post(f"/bills/{bill_id}/participants/{part_id}/payment", json=payment_data)
    assert response.status_code == 403


def test_owner_can_confirm_empty_guest_payment(client: TestClient):
    owner_id = client.post("/users/", json={"telegram_id": 10, "username": "owner"}).json()["id"]
    bill_id = client.post(
        "/bills/",
        json={"owner_id": owner_id, "total_sum": 100, "include_owner": True, "expected_people": 2},
    ).json()["id"]

    guest = next(
        p for p in client.get(f"/bills/{bill_id}?user_id={owner_id}").json()["participants"]
        if p["user_id"] is None
    )
    client.post(
        f"/bills/{bill_id}/assign-amount",
        json={"participant_id": guest["id"], "allocated_amount": 100.0},
    )

    response = client.post(
        f"/bills/{bill_id}/participants/{guest['id']}/payment",
        json={"is_paid": True, "user_id": owner_id},
    )

    assert response.status_code == 200
    paid_guest = next(p for p in response.json()["participants"] if p["id"] == guest["id"])
    assert paid_guest["is_paid"] is True


def test_cannot_add_guest_or_nonexistent_participant(client: TestClient):
    owner_id = client.post("/users/", json={"telegram_id": 1, "username": "owner"}).json()["id"]
    bill_id = client.post("/bills/", json={"owner_id": owner_id, "total_sum": 100, "title": "No Guests"}).json()["id"]

    # Free-text guests are no longer accepted (user_id is required).
    assert client.post(f"/bills/{bill_id}/participants", json={"guest_name": "Ghost"}).status_code == 422
    assert client.post(f"/bills/{bill_id}/participants", json={}).status_code == 422
    # A user_id that doesn't exist is rejected.
    assert client.post(f"/bills/{bill_id}/participants", json={"user_id": 99999}).status_code == 404

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
    
    # Split by hand: 100 each
    for seat in client.get(f"/bills/{bill_id}?user_id=1").json()["participants"]:
        client.post(
            f"/bills/{bill_id}/assign-amount",
            json={"participant_id": seat["id"], "allocated_amount": 100},
        )

    # Verify initial split (3 participants: owner, p1, p2)
    bill = client.get(f"/bills/{bill_id}?user_id=1").json()
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
    # The bill has no declared headcount, so the freed seat is dropped rather
    # than left behind as a phantom person in the split.
    assert len(bill_after_removal["participants"]) == 2
    
    # 4. The two who stay keep their shares; the one who left goes back to the pool
    for p in bill_after_removal["participants"]:
        assert p["allocated_amount"] == 100
    assert bill_after_removal["unallocated_sum"] == 100
    
    # 5. Unauthorized removal attempt
    p1_participant = next(p for p in bill_after_removal["participants"] if p["user_id"] == p1_id)
    p1_participant_id = p1_participant["id"]
    
    stranger = client.post(
        "/users/", json={"telegram_id": 999, "username": "stranger"}
    ).json()["id"]
    response = client.request(
        "DELETE",
        f"/bills/{bill_id}/participants/{p1_participant_id}",
        json={"user_id": stranger}
    )
    assert response.status_code == 403
