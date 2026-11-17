"""A bill's news reaches the app screens watching it, whichever thread it
comes from."""
import asyncio

import pytest

from app.notifier import Notifier


@pytest.mark.asyncio
async def test_news_from_another_thread_reaches_the_screen_watching_the_bill():
    notifier = Notifier()
    stream = notifier.subscribe(7)
    first = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)

    await asyncio.to_thread(notifier.broadcast, 7, "REFRESH")

    assert await asyncio.wait_for(first, timeout=1) == "REFRESH"
    await stream.aclose()
    assert notifier.connections == {}


def test_news_of_a_bill_nobody_watches_goes_nowhere():
    Notifier().broadcast(7, "REFRESH")
