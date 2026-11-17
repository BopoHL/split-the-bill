"""Who brought whom, and through which channel.

A bill's public_token is one value shared by everyone at the table, so it can
never answer "who did the sharing". These tests pin the answer down at both
levels: once per account (first touch) and once per seat.
"""
from fastapi.testclient import TestClient

from app.models import BillUser, Invite, User


def _user(client: TestClient, telegram_id: int) -> int:
    return client.post(
        "/users/", json={"telegram_id": telegram_id, "username": f"u{telegram_id}"}
    ).json()["id"]


def _bill(client: TestClient, owner_id: int, expected: int | None = None) -> dict:
    return client.post(
        "/bills/",
        json={
            "owner_id": owner_id,
            "total_sum": 100,
            "include_owner": True,
            "expected_people": expected,
        },
    ).json()


def _invite(client: TestClient, bill_id: int, channel: str = "link", seat: int | None = None) -> dict:
    return client.post(
        f"/bills/{bill_id}/invites",
        json={"channel": channel, "seat_participant_id": seat},
    ).json()


def test_an_invite_carries_the_sharer_and_the_channel(client: TestClient, session):
    owner = _user(client, 601)
    bill = _bill(client, owner)

    invite = _invite(client, bill["id"], channel="qr")

    assert invite["deep_link"].endswith(f"startapp=inv_{invite['code']}")
    stored = session.exec(Invite.__table__.select()).all()  # noqa: SLF001
    assert len(stored) == 1
    row = session.get(Invite, stored[0].id)
    assert row.inviter_user_id == owner and row.channel == "qr"


def test_a_participant_may_share_but_a_stranger_may_not(client: TestClient):
    owner = _user(client, 602)
    stranger = _user(client, 603)
    bill = _bill(client, owner)

    refused = client.post(
        f"/bills/{bill['id']}/invites",
        json={"channel": "link"},
        headers={"X-Telegram-Init-Data": _init_data(603)},
    )
    assert refused.status_code == 403

    joined = client.post(
        "/bills/join-by-token", json={"token": bill["public_token"], "user_id": stranger}
    )
    assert joined.status_code == 200

    allowed = client.post(
        f"/bills/{bill['id']}/invites",
        json={"channel": "link"},
        headers={"X-Telegram-Init-Data": _init_data(603)},
    )
    assert allowed.status_code == 200


def _init_data(telegram_id: int) -> str:
    from tests.conftest import init_data_for

    return init_data_for(telegram_id)


def test_joining_by_token_credits_the_inviter(client: TestClient, session):
    owner = _user(client, 604)
    newcomer = _user(client, 605)
    bill = _bill(client, owner)
    invite = _invite(client, bill["id"])

    client.post(
        "/bills/join-by-token",
        json={
            "token": bill["public_token"],
            "user_id": newcomer,
            "invite_code": invite["code"],
        },
    )

    seat = _seat_of(session, bill["id"], newcomer)
    assert seat.invited_by_user_id == owner


def test_a_code_from_another_bill_is_ignored(client: TestClient, session):
    owner = _user(client, 606)
    newcomer = _user(client, 607)
    bill = _bill(client, owner)
    other = _bill(client, owner)
    foreign_code = _invite(client, other["id"])["code"]

    client.post(
        "/bills/join-by-token",
        json={
            "token": bill["public_token"],
            "user_id": newcomer,
            "invite_code": foreign_code,
        },
    )

    assert _seat_of(session, bill["id"], newcomer).invited_by_user_id is None


def test_claiming_a_seat_credits_the_inviter_and_a_move_keeps_them(
    client: TestClient, session
):
    owner_tg = 608
    owner = _user(client, owner_tg)
    newcomer = _user(client, 609)
    bill = _bill(client, owner, expected=3)
    seats = client.get(
        f"/bills/public/{bill['public_token']}/seats",
        headers={"X-Telegram-Init-Data": _init_data(owner_tg)},
    ).json()["seats"]
    free = [s for s in seats if not s["is_taken"]]
    invite = _invite(client, bill["id"], channel="seat", seat=free[0]["id"])

    client.post(
        f"/bills/{bill['id']}/seats/{free[0]['id']}/claim",
        json={"user_id": newcomer, "invite_code": invite["code"]},
    )
    assert _seat_of(session, bill["id"], newcomer).invited_by_user_id == owner

    # Moving to another seat is the same person at the same table.
    client.post(
        f"/bills/{bill['id']}/seats/{free[1]['id']}/claim", json={"user_id": newcomer}
    )
    session.expire_all()
    assert _seat_of(session, bill["id"], newcomer).invited_by_user_id == owner


def test_only_the_owner_invites_to_a_named_seat(client: TestClient):
    owner_tg = 610
    owner = _user(client, owner_tg)
    guest = _user(client, 611)
    bill = _bill(client, owner, expected=3)
    seats = client.get(
        f"/bills/public/{bill['public_token']}/seats",
        headers={"X-Telegram-Init-Data": _init_data(owner_tg)},
    ).json()["seats"]
    free = next(s for s in seats if not s["is_taken"])
    client.post(
        "/bills/join-by-token", json={"token": bill["public_token"], "user_id": guest}
    )

    refused = client.post(
        f"/bills/{bill['id']}/invites",
        json={"channel": "seat", "seat_participant_id": free["id"]},
        headers={"X-Telegram-Init-Data": _init_data(611)},
    )
    assert refused.status_code == 403


def test_first_touch_is_recorded_once_and_never_rewritten(client: TestClient, session):
    owner = _user(client, 612)
    poacher = _user(client, 613)
    bill = _bill(client, owner)
    invite = _invite(client, bill["id"])

    newcomer = client.post(
        "/users/",
        json={"telegram_id": 614, "username": "new", "invite_code": invite["code"]},
    ).json()["id"]
    assert session.get(User, newcomer).invited_by_user_id == owner

    poached = client.post(
        f"/bills/{bill['id']}/invites",
        json={"channel": "link"},
        headers={"X-Telegram-Init-Data": _init_data(613)},
    )
    assert poached.status_code == 403  # not a member — but the point is below

    second_bill = _bill(client, poacher)
    later = _invite_as(client, second_bill["id"], 613)
    client.post(
        "/users/",
        json={"telegram_id": 614, "username": "new", "invite_code": later["code"]},
    )
    session.expire_all()
    assert session.get(User, newcomer).invited_by_user_id == owner


def test_an_unknown_invite_code_is_harmless(client: TestClient, session):
    joined = client.post(
        "/users/", json={"telegram_id": 615, "username": "x", "invite_code": "nope"}
    )
    assert joined.status_code == 200
    assert session.get(User, joined.json()["id"]).invited_by_user_id is None


def test_resolving_an_invite_says_where_it_leads(client: TestClient):
    owner = _user(client, 616)
    bill = _bill(client, owner)
    invite = _invite(client, bill["id"])

    resolved = client.get(
        f"/invites/{invite['code']}", headers={"X-Telegram-Init-Data": _init_data(616)}
    ).json()
    assert resolved["bill_id"] == bill["id"]
    assert resolved["public_token"] == bill["public_token"]
    assert resolved["inviter_user_id"] == owner
    assert resolved["seat_participant_id"] is None


def _invite_as(client: TestClient, bill_id: int, telegram_id: int) -> dict:
    return client.post(
        f"/bills/{bill_id}/invites",
        json={"channel": "link"},
        headers={"X-Telegram-Init-Data": _init_data(telegram_id)},
    ).json()


def _seat_of(session, bill_id: int, user_id: int) -> BillUser:
    from sqlmodel import select

    return session.exec(
        select(BillUser).where(BillUser.bill_id == bill_id, BillUser.user_id == user_id)
    ).first()
