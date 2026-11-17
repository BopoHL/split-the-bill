"""Profile photos of the people on a bill, for the picture drawn of it.

They come from the Bot API by Telegram id — the one source the server can
trust, where the avatar URL a client reports is not — and are kept in the
process for a while, so a picture Telegram fetches again, or the next state of
the same bill, costs no new calls. Someone with no photo a bot may see is
remembered as having none; a failed lookup is retried sooner.
"""
import io
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from app.utils.telegram import profile_photo

logger = logging.getLogger(__name__)

PHOTO_SIDE = 160
FETCH_TIMEOUT_SECONDS = 3.0
KEEP_PHOTO_SECONDS = 12 * 3600
KEEP_NO_PHOTO_SECONDS = 3600
KEEP_FAILURE_SECONDS = 300
MAX_PEOPLE = 512
PARALLEL_FETCHES = 6


def _fetch_from_telegram(telegram_id: int) -> bytes | None:
    return profile_photo(telegram_id, PHOTO_SIDE, FETCH_TIMEOUT_SECONDS)


class ProfilePhotos:
    def __init__(
        self,
        fetch: Callable[[int], bytes | None] = _fetch_from_telegram,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self._clock = clock
        self._kept: OrderedDict[int, tuple[float, Image.Image | None]] = OrderedDict()
        self._lock = threading.Lock()

    def for_people(self, telegram_ids: Iterable[int]) -> dict[int, Image.Image]:
        """The photos of those who have one, by Telegram id; the lookups
        nobody has made lately run side by side."""
        wanted = list(dict.fromkeys(telegram_ids))
        photos: dict[int, Image.Image] = {}
        unknown = []
        for telegram_id in wanted:
            known, photo = self._recall(telegram_id)
            if not known:
                unknown.append(telegram_id)
            elif photo is not None:
                photos[telegram_id] = photo
        if unknown:
            with ThreadPoolExecutor(max_workers=min(PARALLEL_FETCHES, len(unknown))) as pool:
                for telegram_id, photo in zip(unknown, pool.map(self._look_up, unknown)):
                    if photo is not None:
                        photos[telegram_id] = photo
        return photos

    def _recall(self, telegram_id: int) -> tuple[bool, Image.Image | None]:
        with self._lock:
            kept = self._kept.get(telegram_id)
            if kept is None or kept[0] <= self._clock():
                return False, None
            self._kept.move_to_end(telegram_id)
            return True, kept[1]

    def _remember(self, telegram_id: int, photo: Image.Image | None, seconds: float) -> None:
        with self._lock:
            self._kept[telegram_id] = (self._clock() + seconds, photo)
            self._kept.move_to_end(telegram_id)
            while len(self._kept) > MAX_PEOPLE:
                self._kept.popitem(last=False)

    def _look_up(self, telegram_id: int) -> Image.Image | None:
        try:
            data = self._fetch(telegram_id)
            photo = Image.open(io.BytesIO(data)).convert("RGB") if data else None
        except Exception as error:
            logger.warning("Profile photo of %s not fetched: %s", telegram_id, error)
            self._remember(telegram_id, None, KEEP_FAILURE_SECONDS)
            return None
        self._remember(telegram_id, photo, KEEP_PHOTO_SECONDS if photo else KEEP_NO_PHOTO_SECONDS)
        return photo


profile_photos = ProfilePhotos()
