"""Every route must know who is calling, and believe only the signed header.

The rest of the suite names its actor in the request and lets the harness sign
for them. This module is where the invariant itself is asserted: an anonymous
caller is refused, a caller speaking for somebody else is refused, and the two
streams that cannot carry a header are gated by a ticket instead.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ANONYMOUS, auth_headers


def _user(client: TestClient, telegram_id: int) -> int:
    return client.post(
        "/users/", json={"telegram_id": telegram_id, "username": f"u{telegram_id}"}
    ).json()["id"]


def _bill(client: TestClient, owner_id: int) -> dict:
    return client.post(
        "/bills/",
        json={"owner_id": owner_id, "total_sum": 100, "include_owner": True},
    ).json()


@pytest.fixture(name="cast")
def cast_fixture(client: TestClient):
    owner = _user(client, 8001)
    outsider = _user(client, 8002)
    bill = _bill(client, owner)
    item = client.post(
        f"/bills/{bill['id']}/items", json={"name": "Plov", "price": 50, "count": 1}
    ).json()
    return {
        "owner": owner,
        "outsider": outsider,
        "bill": bill,
        "item": item,
    }


def _anonymous_calls(cast) -> list[tuple[str, str, dict]]:
    bill_id, owner, item_id = cast["bill"]["id"], cast["owner"], cast["item"]["id"]
    return [
        ("GET", f"/users/{owner}", {}),
        ("PATCH", f"/users/{owner}/settings", {"json": {"theme": "dark"}}),
        ("GET", f"/users/{owner}/bills", {}),
        ("GET", f"/users/{owner}/payment-methods/", {}),
        ("POST", f"/users/{owner}/payment-methods/", {"json": {"value": "x"}}),
        ("POST", "/bills/", {"json": {"owner_id": owner, "total_sum": 1}}),
        ("GET", f"/bills/{bill_id}", {}),
        ("DELETE", f"/bills/{bill_id}?user_id={owner}", {}),
        ("PATCH", f"/bills/{bill_id}", {"json": {"user_id": owner, "title": "x"}}),
        ("POST", f"/bills/{bill_id}/items", {"json": {"name": "a", "price": 1, "count": 1}}),
        ("PATCH", f"/bills/{bill_id}/items/{item_id}", {"json": {"name": "b"}}),
        ("DELETE", f"/bills/{bill_id}/items/{item_id}", {}),
        ("POST", f"/bills/{bill_id}/split-remainder", {"json": {"participant_ids": []}}),
        ("POST", f"/bills/{bill_id}/assign-amount",
         {"json": {"participant_id": 1, "allocated_amount": 1}}),
        ("POST", f"/bills/{bill_id}/close", {"json": {"user_id": owner}}),
        ("POST", f"/bills/{bill_id}/reopen", {"json": {"user_id": owner}}),
        ("POST", "/bills/join-by-token",
         {"json": {"token": cast["bill"]["public_token"], "user_id": owner}}),
        ("GET", f"/bills/public/{cast['bill']['public_token']}/seats", {}),
        ("POST", "/receipts/tasks/1/cancel", {}),
        ("GET", "/receipts/1/image", {}),
        ("POST", "/auth/sse-ticket", {"json": {"resource_type": "bill", "resource_id": 1}}),
    ]


def test_every_route_refuses_an_anonymous_caller(client: TestClient, cast):
    for method, url, kwargs in _anonymous_calls(cast):
        response = client.request(method, url, headers=ANONYMOUS, **kwargs)
        assert response.status_code == 401, f"{method} {url} let an anonymous caller in"


def test_a_caller_cannot_act_as_somebody_else(client: TestClient, cast):
    """The header says user 8002, the payload claims to be the owner."""
    bill_id, owner = cast["bill"]["id"], cast["owner"]
    forged = auth_headers(8002)
    calls = [
        ("DELETE", f"/bills/{bill_id}?user_id={owner}", {}),
        ("PATCH", f"/bills/{bill_id}", {"json": {"user_id": owner, "title": "x"}}),
        ("POST", f"/bills/{bill_id}/close", {"json": {"user_id": owner}}),
        ("POST", f"/bills/{bill_id}/reopen", {"json": {"user_id": owner}}),
        ("POST", "/bills/join-by-token",
         {"json": {"token": cast["bill"]["public_token"], "user_id": owner}}),
        ("POST", "/bills/", {"json": {"owner_id": owner, "total_sum": 1}}),
    ]
    for method, url, kwargs in calls:
        response = client.request(method, url, headers=forged, **kwargs)
        assert response.status_code == 403, f"{method} {url} accepted a forged actor"


def test_owner_only_routes_refuse_a_stranger(client: TestClient, cast):
    bill_id, item_id = cast["bill"]["id"], cast["item"]["id"]
    stranger = auth_headers(8002)
    calls = [
        ("POST", f"/bills/{bill_id}/items", {"json": {"name": "a", "price": 1, "count": 1}}),
        ("PATCH", f"/bills/{bill_id}/items/{item_id}", {"json": {"name": "b"}}),
        ("DELETE", f"/bills/{bill_id}/items/{item_id}", {}),
        ("POST", f"/bills/{bill_id}/split-remainder", {"json": {"participant_ids": []}}),
        ("POST", f"/bills/{bill_id}/assign-amount",
         {"json": {"participant_id": 1, "allocated_amount": 1}}),
    ]
    for method, url, kwargs in calls:
        response = client.request(method, url, headers=stranger, **kwargs)
        assert response.status_code == 403, f"{method} {url} let a stranger through"


def test_payment_methods_are_not_readable_by_others(client: TestClient, cast):
    owner, outsider = cast["owner"], cast["outsider"]
    client.post(f"/users/{owner}/payment-methods/", json={"value": "8600 0000"})

    stolen = client.get(f"/users/{owner}/payment-methods/", headers=auth_headers(8002))
    assert stolen.status_code == 403

    own = client.get(f"/users/{outsider}/payment-methods/", headers=auth_headers(8002))
    assert own.status_code == 200 and own.json() == []


def test_bill_of_a_stranger_stays_invisible(client: TestClient, cast):
    response = client.get(f"/bills/{cast['bill']['id']}", headers=auth_headers(8002))
    assert response.status_code == 403


def test_a_stranger_cannot_seat_themselves_by_bill_id(client: TestClient, cast):
    """Bill and seat ids are sequential, so knowing them lets nobody in — the
    invite link's token does. A seat would hand over the bill and its card."""
    owner, outsider = cast["owner"], cast["outsider"]
    bill = client.post(
        "/bills/",
        json={
            "owner_id": owner, "total_sum": 100, "include_owner": True,
            "expected_people": 2, "payment_details": "8600 1234",
        },
    ).json()
    seat = next(
        p for p in client.get(f"/bills/{bill['id']}?user_id={owner}").json()["participants"]
        if p["user_id"] is None
    )
    stranger = auth_headers(8002)
    claim = f"/bills/{bill['id']}/seats/{seat['id']}/claim"

    added = client.post(
        f"/bills/{bill['id']}/participants", json={"user_id": outsider}, headers=stranger
    )
    assert added.status_code == 403
    for token in (None, "guessed"):
        taken = client.post(claim, json={"user_id": outsider, "token": token}, headers=stranger)
        assert taken.status_code == 403
    assert client.get(f"/bills/{bill['id']}", headers=stranger).status_code == 403

    invited = client.post(
        claim, json={"user_id": outsider, "token": bill["public_token"]}, headers=stranger
    )
    assert invited.status_code == 200


# --- init data signature ------------------------------------------------


def _signed_headers(telegram_id: int, token: str, **user) -> dict[str, str]:
    values = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": telegram_id, **user}, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(values.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"X-Telegram-Init-Data": urlencode(values)}


def test_unsigned_init_data_is_refused_unless_explicitly_allowed(
    client: TestClient, cast, monkeypatch
):
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.setenv("TG_TOKEN", "test-token")

    unsigned = client.get(f"/users/{cast['owner']}", headers=auth_headers(8001))
    assert unsigned.status_code == 401

    signed = client.get(
        f"/users/{cast['owner']}", headers=_signed_headers(8001, "test-token")
    )
    assert signed.status_code == 200


def test_missing_bot_token_fails_closed(client: TestClient, cast, monkeypatch):
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.delenv("TG_TOKEN", raising=False)
    response = client.get(f"/users/{cast['owner']}", headers=auth_headers(8001))
    assert response.status_code == 503


def test_own_signature_cannot_update_somebody_elses_profile(
    client: TestClient, cast, monkeypatch
):
    """POST /users/ names the account in its body. The signed init data is who
    is actually calling, and the two have to agree."""
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.setenv("TG_TOKEN", "test-token")
    mine = _signed_headers(8002, "test-token")["X-Telegram-Init-Data"]

    forged = client.post(
        "/users/",
        json={"telegram_id": 8001, "username": "pwned", "init_data": mine},
        headers=ANONYMOUS,
    )
    assert forged.status_code == 403
    owner = client.get(f"/users/{cast['owner']}", headers=_signed_headers(8001, "test-token"))
    assert owner.json()["username"] == "u8001"

    unsigned = client.post(
        "/users/", json={"telegram_id": 8001, "username": "pwned"}, headers=ANONYMOUS
    )
    assert unsigned.status_code == 401

    own = client.post(
        "/users/",
        json={"telegram_id": 8002, "username": "me", "init_data": mine},
        headers=ANONYMOUS,
    )
    assert own.status_code == 200 and own.json()["id"] == cast["outsider"]


def test_a_second_user_in_front_of_the_signed_one_is_refused(client: TestClient, cast, monkeypatch):
    """The signature covers one «user». Another put in front of it named the
    caller: anyone could act as anyone, read their cards and their bills."""
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.setenv("TG_TOKEN", "test-token")
    mine = _signed_headers(8002, "test-token")["X-Telegram-Init-Data"]
    forged = urlencode({"user": json.dumps({"id": 8001})}) + "&" + mine

    response = client.get(f"/users/{cast['owner']}/payment-methods/", headers={"X-Telegram-Init-Data": forged})

    assert response.status_code == 401


def test_the_handle_and_photo_come_from_the_signed_data(client: TestClient, cast, monkeypatch):
    """From the body, anyone could take a friend's @name and be found and seated
    in their place."""
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.setenv("TG_TOKEN", "test-token")
    mine = _signed_headers(8002, "test-token", username="outsider", photo_url="https://t.me/i/me.jpg")["X-Telegram-Init-Data"]

    saved = client.post(
        "/users/",
        json={"telegram_id": 8002, "username": "u8001", "avatar_url": "https://evil/x.jpg", "init_data": mine},
        headers=ANONYMOUS,
    ).json()

    assert (saved["username"], saved["avatar_url"]) == ("outsider", "https://t.me/i/me.jpg")


def test_someone_off_the_bill_cannot_touch_its_split(client: TestClient, cast):
    """An empty hand-out from a stranger turned the bill into a split by dishes
    and wiped every share before anything said no."""
    bill_id = cast["bill"]["id"]

    response = client.post(f"/bills/{bill_id}/items/assign-batch", json={}, headers=auth_headers(8002))

    assert response.status_code == 403
    assert client.get(f"/bills/{bill_id}", headers=auth_headers(8001)).json()["split_type"] == cast["bill"]["split_type"]


def test_seating_any_account_by_id_is_a_developer_tool_only(client: TestClient, cast, monkeypatch):
    monkeypatch.delenv("ALLOW_UNSIGNED_INIT_DATA", raising=False)
    monkeypatch.setenv("TG_TOKEN", "test-token")

    response = client.post(
        f"/bills/{cast['bill']['id']}/participants",
        json={"user_id": cast["outsider"]},
        headers=_signed_headers(8001, "test-token"),
    )

    assert response.status_code == 404


# --- streams ------------------------------------------------------------


def test_bill_stream_needs_a_ticket(client: TestClient, cast):
    bill_id = cast["bill"]["id"]
    assert client.get(f"/bills/{bill_id}/events", headers=ANONYMOUS).status_code == 401
    assert (
        client.get(f"/bills/{bill_id}/events?ticket=made-up", headers=ANONYMOUS).status_code
        == 401
    )


def test_a_ticket_is_bound_to_one_resource_and_one_use(client: TestClient, cast):
    from app.services.sse_ticket_service import resource_key, sse_tickets

    bill_id = cast["bill"]["id"]
    ticket = client.post(
        "/auth/sse-ticket",
        json={"resource_type": "bill", "resource_id": bill_id},
        headers=auth_headers(8001),
    ).json()["ticket"]

    assert sse_tickets.redeem(ticket, resource_key("bill", bill_id + 1)) is None
    assert sse_tickets.redeem(ticket, resource_key("bill", bill_id)) == cast["owner"]
    assert sse_tickets.redeem(ticket, resource_key("bill", bill_id)) is None


def test_a_stranger_cannot_stream_someone_elses_bill(client: TestClient, cast):
    bill_id = cast["bill"]["id"]
    ticket = client.post(
        "/auth/sse-ticket",
        json={"resource_type": "bill", "resource_id": bill_id},
        headers=auth_headers(8002),
    ).json()["ticket"]

    response = client.get(f"/bills/{bill_id}/events?ticket={ticket}", headers=ANONYMOUS)
    assert response.status_code == 403


def test_the_invite_cover_stays_public(client: TestClient, cast):
    """Telegram's servers fetch it to render the invite — no identity to send."""
    response = client.get(
        f"/bills/public/{cast['bill']['public_token']}/receipt", headers=ANONYMOUS
    )
    assert response.status_code == 404  # no photo on this bill, but not 401
