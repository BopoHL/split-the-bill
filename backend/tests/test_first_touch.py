"""How someone first came in, kept on their PostHog person by the server
when the account is made, and never written again."""
from fastapi.testclient import TestClient


def _first_touches(product_events) -> list[tuple[str, dict]]:
    return [(distinct_id, properties) for event, distinct_id, properties in product_events if event == "$set_once"]


def test_the_open_that_makes_the_account_is_kept_as_its_first_touch(client: TestClient, product_events):
    user = client.post("/users/", json={"telegram_id": 7, "start": "source", "source": "tiktok"}).json()

    assert _first_touches(product_events) == [(str(user["id"]), {"first_start": "source", "first_source": "tiktok"})]


def test_a_later_open_leaves_the_first_touch_as_it_was(client: TestClient, product_events):
    client.post("/users/", json={"telegram_id": 7, "start": "invite"})
    product_events.clear()

    client.post("/users/", json={"telegram_id": 7, "start": "source", "source": "tiktok"})

    assert _first_touches(product_events) == []


def test_an_open_that_says_nothing_of_where_it_came_from_is_kept_as_none(client: TestClient, product_events):
    user = client.post("/users/", json={"telegram_id": 7}).json()

    assert _first_touches(product_events) == [(str(user["id"]), {"first_start": "none"})]


def test_labels_that_are_not_labels_are_dropped_and_the_account_still_made(client: TestClient, product_events):
    response = client.post("/users/", json={"telegram_id": 7, "start": "Not a label!", "source": "x" * 65})

    assert response.status_code == 200
    assert _first_touches(product_events) == [(str(response.json()["id"]), {"first_start": "none"})]
