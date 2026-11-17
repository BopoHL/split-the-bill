"""Themes: light and dark for everyone, the rest with Pro — which can be chosen,
and which one someone sees."""
from datetime import datetime, timedelta
from typing import get_args

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import ProSource
from app.schemas.admin_schemas import AdminUserSettingsUpdate
from app.services.drawing import PALETTES
from app.services.themes import FREE_THEMES, PRO_THEMES, shown_theme, theme_of
from tests.pro_world import NOW, grant

ALL_THEMES = {*FREE_THEMES, *PRO_THEMES}


def test_every_theme_has_its_colours_and_the_admin_can_set_any():
    choosable, _none = get_args(AdminUserSettingsUpdate.model_fields["theme"].annotation)

    assert set(PALETTES) == ALL_THEMES
    assert set(get_args(choosable)) == ALL_THEMES


def test_without_pro_a_pro_theme_gives_way_to_its_own_lightness():
    assert shown_theme("nord", pro=True) == "nord"
    assert [shown_theme(theme, pro=False) for theme in ("nord", "nord_frost", "sakura", "midnight")] == [
        "dark", "light", "light", "dark",
    ]
    assert shown_theme("dark", pro=False) == "dark"
    assert shown_theme("neon", pro=True) == "light"
    assert shown_theme(None, pro=False) == "light"


def test_the_theme_someone_sees_follows_their_pro(session: Session, people):
    leo, _ = people
    leo.settings = {**leo.settings, "theme": "midnight"}
    session.add(leo)
    session.commit()

    assert theme_of(session, leo, NOW) == "dark"
    grant(session, leo, ProSource.PROMO, NOW - timedelta(days=1), 30)
    assert theme_of(session, leo, NOW) == "midnight"
    assert theme_of(session, leo, NOW + timedelta(days=30)) == "dark"


def test_a_pro_theme_is_chosen_with_pro_only(client: TestClient, session: Session, people):
    leo, _ = people
    client.act_as(leo.telegram_id)

    assert client.patch(f"/users/{leo.id}/settings", json={"theme": "dark"}).json()["settings"]["theme"] == "dark"
    refused = client.patch(f"/users/{leo.id}/settings", json={"theme": "nord"})
    assert (refused.status_code, refused.json()["detail"]) == (402, {"code": "PRO_REQUIRED", "feature": "themes"})
    assert client.patch(f"/users/{leo.id}/settings", json={"theme": "neon"}).status_code == 400

    grant(session, leo, ProSource.TRIAL, datetime.utcnow() - timedelta(days=1), 7)
    chosen = client.patch(f"/users/{leo.id}/settings", json={"theme": "nord_frost"})
    assert chosen.json()["settings"]["theme"] == "nord_frost"
