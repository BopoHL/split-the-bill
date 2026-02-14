import pytest
from fastapi.testclient import TestClient
import json
from urllib.parse import urlencode

def test_user_sync_with_names(client: TestClient):
    # Mock Telegram user data
    tg_user = {
        "id": 12345,
        "first_name": "John",
        "last_name": "Doe",
        "username": "jdoe",
        "photo_url": "http://example.com/avatar.jpg"
    }
    
    # Simulate init_data
    init_data = f"user={json.dumps(tg_user)}&auth_date=12345678&hash=mock_hash"
    
    # 1. Create/Update user
    response = client.post("/users/", json={
        "telegram_id": 12345,
        "username": "jdoe",
        "avatar_url": "http://example.com/avatar.jpg",
        "init_data": init_data
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "John"
    assert data["surname"] == "Doe"
    assert data["username"] == "jdoe"

    # 2. Verify it's saved by fetching again
    response = client.get(f"/users/{data['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "John"
    assert response.json()["surname"] == "Doe"

def test_user_sync_with_widget_data(client: TestClient):
    widget_data = {
        "id": 67890,
        "first_name": "Jane",
        "last_name": "Smith",
        "username": "jsmith",
        "photo_url": "http://example.com/jane.jpg",
        "auth_date": 12345678,
        "hash": "mock_hash"
    }
    
    response = client.post("/users/", json={
        "telegram_id": 67890,
        "username": "jsmith",
        "widget_data": widget_data
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Jane"
    assert data["surname"] == "Smith"

def test_bill_participant_response_has_names(client: TestClient):
    # Setup owner
    resp_owner = client.post("/users/", json={"telegram_id": 1, "username": "owner", "name": "Owner", "surname": "User"})
    owner_id = resp_owner.json()["id"]
    
    # Create bill
    resp_bill = client.post("/bills/", json={"owner_id": owner_id, "total_sum": 100, "title": "Test Bill", "include_owner": True})
    bill_id = resp_bill.json()["id"]
    
    # Get bill details
    response = client.get(f"/bills/{bill_id}")
    assert response.status_code == 200
    participants = response.json()["participants"]
    
    owner_part = next(p for p in participants if p["user_id"] == owner_id)
    assert owner_part["name"] == "Owner"
    assert owner_part["surname"] == "User"
