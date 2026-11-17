import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image

from app.services.bill_summary import BillSummary, SummaryLine, SummarySeat
from app.services.drawing import PALETTES, printable, text_width
from app.services.share_card import (
    AVATAR, HARD_SHADOW, MARGIN, MAX_HEIGHT, NAME_X, PAD, PAID_MARK, WIDTH, _avatar, _dish, _listing, _meta, _name,
    render_card,
)

NOW = datetime(2026, 9, 26, 9, 32, tzinfo=timezone.utc)
ZONE = ZoneInfo("Asia/Tashkent")


def _summary(seats=(), unassigned=(), **overrides) -> BillSummary:
    values = dict(
        title="Dinner", created_at=datetime(2026, 9, 25, 14, 0), currency="uzs", total=3_280_000,
        seats=tuple(seats), unassigned=tuple(unassigned),
        unassigned_total=sum(line.amount for line in unassigned), to_collect=1_420_000, collected=320_000,
        payment_details=None, is_closed=False,
    )
    values.update(overrides)
    return BillSummary(**values)


def _seat(index: int, dishes: int = 3, **overrides) -> SummarySeat:
    values = dict(
        participant_id=index, name=f"Person {index}", seat_index=index, amount=100_000 * index,
        is_owner=False, is_paid=False,
        lines=tuple(SummaryLine(f"Dish {n}", 1, 30_000) for n in range(dishes)),
    )
    values.update(overrides)
    return SummarySeat(**values)


def _size(png: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(png)).size


def test_a_small_bill_draws_a_short_card_at_full_width():
    png = render_card(_summary([_seat(1), _seat(2, is_owner=True)], [SummaryLine("Bread", 3, 90_000)]), "ru", NOW, ZONE)

    width, height = _size(png)
    assert png.startswith(b"\x89PNG")
    assert width == WIDTH
    assert 600 < height < MAX_HEIGHT


def test_a_crowded_bill_still_fits_a_phone_screen():
    seats = [_seat(index, dishes=6, is_paid=index % 2 == 0) for index in range(1, 16)]

    assert _size(render_card(_summary(seats, [SummaryLine("Tea", 8, 80_000)]), "uz", NOW, ZONE))[1] <= MAX_HEIGHT


def test_a_bill_nobody_has_touched_and_a_closed_one_both_draw():
    empty = render_card(_summary(total=0, to_collect=0, collected=0, title=None), "en", NOW, ZONE)
    closed = render_card(_summary([_seat(1, is_paid=True)], is_closed=True), "ru", NOW, ZONE)

    assert _size(empty)[1] < _size(closed)[1] <= MAX_HEIGHT


def _reds(png: bytes) -> int:
    pixels = Image.open(io.BytesIO(png)).convert("RGB").tobytes()
    return sum(
        1 for i in range(0, len(pixels), 3) if pixels[i] > 200 and pixels[i + 1] < 60 and pixels[i + 2] < 60
    )


def test_people_are_drawn_with_their_photo_or_their_initial():
    seats = [_seat(1, telegram_id=11), _seat(2, telegram_id=22), _seat(3, name=None)]
    red = Image.new("RGB", (160, 160), (230, 20, 20))

    with_photo = render_card(_summary(seats), "ru", NOW, ZONE, {11: red})
    without = render_card(_summary(seats), "ru", NOW, ZONE)

    # About one avatar's worth of red: what its rounded outline frames, not the whole photo.
    assert AVATAR * AVATAR / 2 < _reds(with_photo) < AVATAR * AVATAR
    assert _reds(without) == 0


def _greens(png: bytes) -> int:
    pixels = Image.open(io.BytesIO(png)).convert("RGB").tobytes()
    return sum(
        1 for i in range(0, len(pixels), 3)
        if abs(pixels[i] - 0x2F) < 12 and abs(pixels[i + 1] - 0x7D) < 12 and abs(pixels[i + 2] - 0x4F) < 12
    )


def test_a_paid_person_gets_a_green_coin_after_their_name():
    # Nothing left to collect, so no progress bar to be green as well.
    paid = render_card(_summary([_seat(1, is_paid=True)], to_collect=0, collected=0), "ru", NOW, ZONE)
    unpaid = render_card(_summary([_seat(1)], to_collect=0, collected=0), "ru", NOW, ZONE)

    assert _greens(unpaid) == 0
    assert PAID_MARK * PAID_MARK / 2 < _greens(paid) < PAID_MARK * PAID_MARK


def test_a_seat_nobody_sits_on_is_a_silhouette_that_casts_no_shadow():
    free = _avatar(PALETTES["light"], _seat(1, name=None, is_free=True), None, "1")
    taken = _avatar(PALETTES["light"], _seat(2), None, "P")

    assert free.size == (AVATAR, AVATAR)
    assert taken.size == (AVATAR + HARD_SHADOW[0], AVATAR + HARD_SHADOW[1])


def _pixel(png: bytes, x: int, y: int) -> tuple[int, int, int]:
    return Image.open(io.BytesIO(png)).convert("RGB").getpixel((x, y))


def test_the_card_takes_the_colours_of_the_sharers_theme():
    summary = _summary([_seat(1, is_paid=True)])

    light = render_card(summary, "ru", NOW, ZONE, theme="light")
    dark = render_card(summary, "ru", NOW, ZONE, theme="dark")

    # The page round the ticket, and the ticket itself.
    assert _pixel(light, 4, 4) == (0xEF, 0xE7, 0xD8)
    assert _pixel(dark, 4, 4) == (0x22, 0x20, 0x1C)
    assert _pixel(dark, WIDTH // 2, 60) == (0x2A, 0x27, 0x23)
    # A theme it does not know draws the light one.
    assert render_card(summary, "ru", NOW, ZONE, theme="neon") == light


def test_each_theme_draws_its_own_card():
    summary = _summary([_seat(1, is_paid=True)])
    pages = {theme: _pixel(render_card(summary, "ru", NOW, ZONE, theme=theme), 4, 4) for theme in PALETTES}

    assert pages["nord"] == (0x2E, 0x34, 0x40)
    assert pages["sakura"] == (0xF4, 0xE6, 0xE6)
    assert len(set(pages.values())) == len(PALETTES)


def _hex(colour: str) -> tuple[int, int, int]:
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def _close(pixel: tuple[int, int, int], colour: tuple[int, int, int]) -> bool:
    """Near enough to allow for the smoothing along a letter's edge."""
    return sum(abs(a - b) for a, b in zip(pixel, colour)) <= 30


def test_a_name_is_centred_on_its_face_and_a_name_with_dishes_fills_it():
    # One name with dishes running on to a second line, one with none; the
    # title is kept short so that nothing but the names is inked over them.
    palette = PALETTES["dark"]
    seats = [_seat(1, dishes=6, name="Нина"), _seat(2, dishes=0, name="Нина")]
    png = render_card(_summary(seats, title="Ok"), "ru", NOW, ZONE, theme="dark")
    image = Image.open(io.BytesIO(png)).convert("RGB")
    left = MARGIN + PAD
    face_column = left + AVATAR // 2
    name_columns = range(left + NAME_X, left + NAME_X + text_width("Нина", _name()))
    outline, ink = _hex(palette.outline), _hex(palette.ink)

    def inked(y: int) -> bool:
        return any(_close(image.getpixel((x, y)), ink) for x in name_columns)

    face_tops = [
        y for y in range(1, image.height)
        if image.getpixel((face_column, y)) == outline and image.getpixel((face_column, y - 1)) != outline
    ]
    # The first two runs of ink there are the names; the total comes later.
    names = []
    for y in range(1, image.height):
        if inked(y) and not inked(y - 1):
            names.append([y, y])
        elif inked(y):
            names[-1][1] = y
    (wrapped_top, _), (alone_top, alone_bottom) = names[:2]

    def face_of(top: int) -> int:
        return max(face for face in face_tops if face <= top + 1)

    assert abs(wrapped_top - face_of(wrapped_top)) <= 1
    assert abs((alone_top + alone_bottom) / 2 - (face_of(alone_top) + AVATAR / 2)) <= 1.5


def _more(hidden: int) -> str:
    return f"ещё +{hidden}"


def test_dishes_run_on_with_commas_while_they_fit():
    dishes = [["Плов"], ["Самса", "×3"], ["Чай"]]

    assert _listing(dishes, _more, _dish(), 900, 2) == ["Плов, Самса ×3, Чай"]


def test_dishes_past_the_last_line_are_counted_instead():
    dishes = [[f"Блюдо{n}"] for n in range(40)]

    lines = _listing(dishes, _more, _dish(), 600, 2)

    assert len(lines) == 2
    shown = sum(line.count("Блюдо") for line in lines)
    assert lines[-1].endswith(f", ещё +{40 - shown}")


def test_a_dishs_count_never_starts_a_line():
    dishes = [["Шашлык", "из", "баранины ×2"], ["Чай"]]

    lines = _listing(dishes, _more, _dish(), 260, 3)

    assert not any(line.startswith("×") for line in lines)
    assert "баранины ×2," in " ".join(lines)


def test_dishes_start_on_the_line_of_the_name_and_run_on_below_it():
    dishes = [["Плов"], ["Самса", "×3"], ["Чай"], ["Лепёшка"]]
    room = text_width("Плов, Самса ×3,", _dish()) + 4

    lines = _listing(dishes, _more, _dish(), 900, 2, first=room)

    assert lines == ["Плов, Самса ×3,", "Чай, Лепёшка"]


def test_a_dish_that_fits_a_line_is_never_split_across_two():
    dishes = [["Малина", "и", "Лемонграсс ×2"], ["Чай"]]
    room = text_width("Малина и", _dish()) + 20

    assert _listing(dishes, _more, _dish(), 900, 2, first=room) == ["", "Малина и Лемонграсс ×2, Чай"]


def test_a_name_that_leaves_no_room_sends_the_dishes_below_it():
    assert _listing([["Шашлык"], ["Чай"]], _more, _dish(), 900, 2, first=20) == ["", "Шашлык, Чай"]


def test_a_dish_too_long_for_its_line_is_cut_and_the_rest_still_counted():
    dishes = [["Шашлык", "из", "молодой", "баранины", "на", "углях"], ["Чай"], ["Хлеб"]]

    [line] = _listing(dishes, _more, _dish(), 900, 1, first=320)

    assert line.startswith("Шашлык") and line.endswith("…, ещё +2")
    assert text_width(line, _dish()) <= 320
    # Too little room to show any of it: nothing, rather than «…, ещё +2».
    assert _listing(dishes, _more, _dish(), 900, 1, first=200) == []


def test_the_date_and_time_are_figures_only():
    assert _meta(_summary(), "ru", NOW, ZONE) == "25.09.2026 · 14:32"
    assert _meta(_summary(is_closed=True), "ru", NOW, ZONE) == "Счёт закрыт"


def test_characters_the_fonts_cannot_draw_are_left_out():
    assert printable("Бобур 🍕  Karimov") == "Бобур Karimov"
    assert printable("Oʻtkir G‘ulom №2 × «Plov»") == "Oʻtkir G‘ulom №2 × «Plov»"
    assert printable("🎉🎉") == ""


def test_the_card_is_served_by_the_bills_public_token(client: TestClient):
    owner = client.post("/users/", json={"telegram_id": 501, "username": "owner"}).json()["id"]
    bill = client.post("/bills/", json={"owner_id": owner, "total_sum": 0, "include_owner": True, "title": "Tea"}).json()
    client.post(f"/bills/{bill['id']}/items", json={"name": "Tea", "price": 8000, "count": 2})
    token = client.get(f"/bills/{bill['id']}?user_id={owner}").json()["public_token"]

    client.act_as(None)
    response = client.get(f"/bills/public/{token}/card.png", params={"lang": "uz", "v": "abc"})

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert _size(response.content)[0] == WIDTH
    assert client.get("/bills/public/nope/card.png").status_code == 404


def test_the_card_asks_for_the_photos_of_the_people_on_it(client: TestClient, monkeypatch):
    import app.routers.bills as bills_router

    asked = []
    red = Image.new("RGB", (160, 160), (230, 20, 20))

    class _Photos:
        def for_people(self, telegram_ids):
            asked.extend(telegram_ids)
            return {502: red}

    monkeypatch.setattr(bills_router, "profile_photos", _Photos())
    owner = client.post("/users/", json={"telegram_id": 502, "username": "owner"}).json()["id"]
    bill = client.post("/bills/", json={"owner_id": owner, "total_sum": 0, "include_owner": True, "title": "Tea"}).json()
    item = client.post(f"/bills/{bill['id']}/items", json={"name": "Tea", "price": 8000, "count": 1}).json()
    detail = client.get(f"/bills/{bill['id']}?user_id={owner}").json()
    seat = next(p["id"] for p in detail["participants"] if p["user_id"] == owner)
    client.post(f"/bills/{bill['id']}/items/{item['id']}/assign?requester_id={owner}", json={"participant_id": seat, "is_assigned": True})

    client.act_as(None)
    response = client.get(f"/bills/public/{detail['public_token']}/card.png")

    assert response.status_code == 200, response.text
    assert asked == [502]
    assert _reds(response.content) > 1500
