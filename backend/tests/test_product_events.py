import pytest

import app.services.product_events as product_events_module
from app.services.product_events import ProductEvent, Surface, capture, set_person

# Taken before the autouse fixture stands a recorder in for it.
REAL_CLIENT = product_events_module._client


@pytest.fixture
def real_client(monkeypatch):
    REAL_CLIENT.cache_clear()
    monkeypatch.setattr(product_events_module, "_client", REAL_CLIENT)
    yield REAL_CLIENT
    REAL_CLIENT.cache_clear()


def test_nothing_is_sent_without_a_key(real_client, monkeypatch):
    monkeypatch.delenv("POSTHOG_KEY", raising=False)

    assert real_client() is None
    capture(1, ProductEvent.BOT_COMMAND, Surface.BOT, command="start")


def test_person_properties_need_a_key_too(real_client, monkeypatch):
    monkeypatch.delenv("POSTHOG_KEY", raising=False)

    set_person(1, internal=True)


def test_the_key_and_host_come_from_the_environment(real_client, monkeypatch):
    monkeypatch.setenv("POSTHOG_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_HOST", "https://ph.example")

    client = real_client()

    assert (client.api_key, client.host) == ("phc_test", "https://ph.example")
    client.shutdown()


def test_a_failure_to_send_stays_out_of_the_way(monkeypatch):
    class Broken:
        def capture(self, *args, **kwargs):
            raise RuntimeError("down")

    monkeypatch.setattr(product_events_module, "_client", Broken)

    capture(1, ProductEvent.PRO_PURCHASED, Surface.SERVER, plan="year")
