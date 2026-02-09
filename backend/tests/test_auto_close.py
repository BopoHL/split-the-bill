import pytest
from fastapi.testclient import TestClient

def test_bill_auto_close_on_full_payment(client: TestClient):
    # 1. Setup participants
    resp_owner = client.post("/users/", json={"telegram_id": 1000, "username": "owner"})
    resp_p1 = client.post("/users/", json={"telegram_id": 1001, "username": "p1"})
    
    owner_id = resp_owner.json()["id"]
    p1_id = resp_p1.json()["id"]
    
    # 2. Create a bill (total 1000)
    bill_data = {
        "owner_id": owner_id,
        "total_sum": 1000.0,
        "title": "Auto-close Test",
        "include_owner": True
    }
    resp_bill = client.post("/bills/", json=bill_data)
    bill_id = resp_bill.json()["id"]
    
    # 3. Add p1
    client.post(f"/bills/{bill_id}/participants", json={"user_id": p1_id})
    
    # 4. Split equally (500 each, unallocated = 0)
    client.post(f"/bills/{bill_id}/split-equally")
    
    # Verify initial state
    bill = client.get(f"/bills/{bill_id}").json()
    assert bill["is_closed"] is False
    assert bill["unallocated_sum"] == 0
    
    participants = bill["participants"]
    owner_part = next(p for p in participants if p["user_id"] == owner_id)
    p1_part = next(p for p in participants if p["user_id"] == p1_id)
    
    # 5. Mark p1 as paid
    client.post(f"/bills/{bill_id}/participants/{p1_part['id']}/payment", json={
        "is_paid": True,
        "user_id": p1_id
    })
    
    # 6. Verify bill status is now PAID (others paid)
    bill_paid = client.get(f"/bills/{bill_id}").json()
    assert bill_paid["status"] == "paid"
    assert bill_paid["is_closed"] is False
    
    # 7. Owner finalizes the bill
    client.post(f"/bills/{bill_id}/close", json={
        "user_id": owner_id
    })
    
    # 8. Verify bill is CLOSED
    final_bill = client.get(f"/bills/{bill_id}").json()
    assert final_bill["status"] == "closed"
    assert final_bill["is_closed"] is True
    
    # Verify owner is now marked as paid
    owner_final = next(p for p in final_bill["participants"] if p["user_id"] == owner_id)
    assert owner_final["is_paid"] is True
