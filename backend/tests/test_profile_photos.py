"""Profile photos for the shared bill's picture: fetched once, kept a while."""
import io

from PIL import Image

from app.services.profile_photos import (
    KEEP_FAILURE_SECONDS,
    KEEP_NO_PHOTO_SECONDS,
    KEEP_PHOTO_SECONDS,
    ProfilePhotos,
)


def _jpeg(colour: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (160, 160), colour).save(output, format="JPEG")
    return output.getvalue()


class _Telegram:
    def __init__(self, photos: dict[int, bytes | None], failing: set[int] = frozenset()):
        self.photos = photos
        self.failing = set(failing)
        self.asked: list[int] = []

    def __call__(self, telegram_id: int) -> bytes | None:
        self.asked.append(telegram_id)
        if telegram_id in self.failing:
            raise RuntimeError("Telegram request failed: timeout")
        return self.photos.get(telegram_id)


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_photos_come_back_decoded_and_are_not_fetched_twice():
    telegram, clock = _Telegram({1: _jpeg("red"), 2: None}), _Clock()
    photos = ProfilePhotos(telegram, clock)

    first = photos.for_people([1, 2, 1])
    again = photos.for_people([2, 1])

    assert list(first) == [1] and first[1].getpixel((80, 80))[0] > 200
    assert list(again) == [1]
    assert sorted(telegram.asked) == [1, 2]


def test_what_was_learnt_is_asked_again_once_it_goes_stale():
    telegram, clock = _Telegram({1: _jpeg("red"), 2: None}, failing={3}), _Clock()
    photos = ProfilePhotos(telegram, clock)
    photos.for_people([1, 2, 3])

    clock.now += KEEP_FAILURE_SECONDS + 1
    photos.for_people([1, 2, 3])
    assert telegram.asked.count(3) == 2 and telegram.asked.count(2) == 1

    clock.now += KEEP_NO_PHOTO_SECONDS
    photos.for_people([1, 2])
    assert telegram.asked.count(2) == 2 and telegram.asked.count(1) == 1

    clock.now += KEEP_PHOTO_SECONDS
    photos.for_people([1])
    assert telegram.asked.count(1) == 2


def test_a_failed_lookup_or_an_unreadable_photo_is_no_photo():
    telegram = _Telegram({2: b"not an image"}, failing={1})

    assert ProfilePhotos(telegram, _Clock()).for_people([1, 2]) == {}
