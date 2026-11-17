from fastapi.testclient import TestClient


def test_user_settings_default_and_merge(client: TestClient):
    u = client.post("/users/", json={"telegram_id": 1, "username": "u"}).json()
    uid = u["id"]
    # New users start with empty settings.
    assert u["settings"] == {}

    # First update stores both keys.
    r = client.patch(f"/users/{uid}/settings", json={"theme": "dark", "language": "ru"})
    assert r.status_code == 200
    assert r.json()["settings"] == {"theme": "dark", "language": "ru"}

    # Partial update merges (theme preserved, language changed).
    r = client.patch(f"/users/{uid}/settings", json={"language": "en"})
    assert r.json()["settings"] == {"theme": "dark", "language": "en"}

    # GET reflects the persisted settings.
    assert client.get(f"/users/{uid}").json()["settings"] == {
        "theme": "dark",
        "language": "en",
    }


def test_user_settings_onboarding_flag(client: TestClient):
    u = client.post("/users/", json={"telegram_id": 7, "username": "onb"}).json()
    uid = u["id"]
    # Flag is absent until the onboarding is completed.
    assert "onboarding_completed" not in u["settings"]

    r = client.patch(f"/users/{uid}/settings", json={"onboarding_completed": True})
    assert r.status_code == 200
    assert r.json()["settings"]["onboarding_completed"] is True

    # Merges alongside other prefs without clobbering them.
    r = client.patch(f"/users/{uid}/settings", json={"theme": "dark"})
    s = r.json()["settings"]
    assert s["onboarding_completed"] is True and s["theme"] == "dark"


def test_the_guest_tour_flag_is_kept_apart_from_onboarding(client: TestClient):
    uid = client.post("/users/", json={"telegram_id": 8, "username": "guest"}).json()["id"]

    r = client.patch(f"/users/{uid}/settings", json={"guest_tour_completed": True})

    assert r.json()["settings"] == {"guest_tour_completed": True}


def test_user_sync_tracks_telegram_write_access(client: TestClient):
    u = client.post(
        "/users/",
        json={
            "telegram_id": 8,
            "username": "reachable",
            "allows_write_to_pm": False,
        },
    ).json()
    assert u["settings"]["bot_blocked"] is True

    r = client.post(
        "/users/",
        json={
            "telegram_id": 8,
            "username": "reachable",
            "allows_write_to_pm": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["settings"]["bot_blocked"] is False

    r = client.post("/users/", json={"telegram_id": 8, "username": "reachable"})
    assert r.json()["settings"]["bot_blocked"] is False


def test_user_write_access_endpoint_marks_reachability(client: TestClient):
    u = client.post("/users/", json={"telegram_id": 9, "username": "writer"}).json()
    uid = u["id"]

    r = client.patch(f"/users/{uid}/write-access", json={"allows_write_to_pm": False})
    assert r.status_code == 200
    assert r.json()["settings"]["bot_blocked"] is True

    r = client.patch(f"/users/{uid}/write-access", json={"allows_write_to_pm": True})
    assert r.status_code == 200
    assert r.json()["settings"]["bot_blocked"] is False


def test_user_settings_unknown_user(client: TestClient):
    # Nobody can authenticate as a user that does not exist.
    r = client.patch("/users/99999/settings", json={"theme": "dark"})
    assert r.status_code == 401


def test_a_settings_change_keeps_what_was_written_meanwhile(client: TestClient, session):
    """The welcome DM stores `welcome_sent` while the language is being saved;
    merging into a stale copy of the row used to drop it."""
    from sqlmodel import Session

    from app.models import User
    from app.repositories.user_repo import UserRepository
    from app.schemas.user_schemas import UserSettingsUpdate
    from app.services.user_service import UserService

    uid = client.post("/users/", json={"telegram_id": 1, "username": "u"}).json()["id"]
    session.get(User, uid)  # this request's copy, read before the DM went out
    with Session(session.get_bind()) as elsewhere:
        other = elsewhere.get(User, uid)
        other.settings = {**(other.settings or {}), "welcome_sent": True}
        elsewhere.add(other)
        elsewhere.commit()

    saved = UserService(UserRepository(session)).update_settings(uid, UserSettingsUpdate(language="en"))

    assert saved.settings["welcome_sent"] is True
    assert saved.settings["language"] == "en"
