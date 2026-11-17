"""A bill said out loud: new lines added, the said ones handed out, Pro only."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Bill, ProSource, User
from tests.conftest import auth_headers
from tests.pro_world import grant


def _table(client: TestClient, session: Session, people: int = 3, pro: bool = True):
    owner = client.post("/users/", json={"telegram_id": 1, "username": "o", "name": "Leo"}).json()["id"]
    if pro:
        grant(session, session.get(User, owner), ProSource.PROMO, datetime.utcnow() - timedelta(days=1), 30)
    bid = client.post(
        "/bills/",
        json={"owner_id": owner, "total_sum": 0, "include_owner": True, "expected_people": people, "currency": "uzs"},
    ).json()["id"]
    return owner, bid


def _seats(client, bid, owner):
    return client.get(f"/bills/{bid}?user_id={owner}").json()["participants"]


def _say(client, bid, text):
    return client.post(f"/bills/{bid}/voice", data={"text": text})


def test_without_pro_the_bill_is_not_told(client: TestClient, session: Session, model):
    _owner, bid = _table(client, session, pro=False)

    refused = _say(client, bid, "кола 15")

    assert (refused.status_code, refused.json()["detail"]) == (402, {"code": "PRO_REQUIRED", "feature": "voice"})
    assert model["chat"] is None


def test_said_lines_are_added_and_handed_out_to_the_people_named(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    me, first_guest, second_guest = (seat["id"] for seat in _seats(client, bid, owner))
    model["answer"] = {
        "items": [
            {"ref": "n1", "name": "Пицца", "count": 2, "amount": 160000, "is_shared_globally": False},
            {"ref": "n2", "name": "Кола", "count": 1, "amount": 15000, "is_shared_globally": False},
        ],
        "assign": [
            {"item": "n1", "people": [me, "Аня"], "portions": None, "everyone": False},
            {"item": "n2", "people": ["Борис"], "portions": None, "everyone": False},
        ],
    }

    told = _say(client, bid, "Две пиццы по 80 — я и Аня, кола 15 — Борис")

    assert told.status_code == 200
    body = told.json()
    assert (body["heard"], body["added"], body["assigned"]) == ("Две пиццы по 80 — я и Аня, кола 15 — Борис", 2, 2)
    bill = body["bill"]
    assert bill["total_sum"] == 175000
    assert bill["unallocated_sum"] == 0
    seats = {seat["id"]: seat for seat in bill["participants"]}
    # The named take the empty guest seats in table order.
    assert (seats[first_guest]["guest_name"], seats[second_guest]["guest_name"]) == ("Аня", "Борис")
    assert [seats[seat]["allocated_amount"] for seat in (me, first_guest, second_guest)] == [80000, 80000, 15000]
    # The model saw the people at the table and who of them is speaking.
    prompt = model["chat"]["messages"][1]["content"]
    assert f"{me}: the speaker" in prompt
    # An unnamed seat is called what the app shows it as, so «Гость 1» can be pointed at.
    assert f"{first_guest}: «Гость 1» / «Guest 1» / «1-mehmon», no name yet" in prompt
    assert "Две пиццы по 80" in prompt


def test_a_line_split_by_units_gives_each_their_own(client: TestClient, session: Session, model):
    owner, bid = _table(client, session, people=2)
    beer = client.post(f"/bills/{bid}/items", json={"name": "Пиво", "price": 30000, "count": 3}).json()
    me, guest = (seat["id"] for seat in _seats(client, bid, owner))
    model["answer"] = {"items": [], "assign": [
        {"item": beer["id"], "people": [me], "portions": 2, "everyone": False},
        {"item": str(beer["id"]), "people": [str(guest)], "portions": 1, "everyone": False},
    ]}

    bill = _say(client, bid, "два пива мне, одно гостю").json()["bill"]

    allocated = {seat["id"]: seat["allocated_amount"] for seat in bill["participants"]}
    assert (allocated[me], allocated[guest]) == (60000, 30000)


def test_a_line_for_the_whole_table_is_shared_and_replaces_who_had_it(client: TestClient, session: Session, model):
    owner, bid = _table(client, session, people=2)
    salad = client.post(f"/bills/{bid}/items", json={"name": "Салат", "price": 40000, "count": 1}).json()
    me, _guest = (seat["id"] for seat in _seats(client, bid, owner))
    client.post(
        f"/bills/{bid}/items/assign-batch?requester_id={owner}",
        json={"ops": [{"item_id": salad["id"], "participant_id": me, "is_assigned": True}]},
    )
    model["answer"] = {"items": [], "assign": [{"item": salad["id"], "people": [], "portions": None, "everyone": True}]}

    bill = _say(client, bid, "салат на всех").json()["bill"]

    line = next(item for item in bill["items"] if item["id"] == salad["id"])
    assert line["is_shared_globally"] is True
    assert line["assigned_participant_ids"] == []
    assert [seat["allocated_amount"] for seat in bill["participants"]] == [20000, 20000]


def test_more_people_than_seats_lay_another_place(client: TestClient, session: Session, model):
    owner, bid = _table(client, session, people=1)
    model["answer"] = {
        "items": [{"ref": "n1", "name": "Чай", "count": 1, "amount": 10000}],
        "assign": [{"item": "n1", "people": ["Дима"], "portions": None}],
    }

    bill = _say(client, bid, "чай 10 — Дима").json()["bill"]

    assert bill["expected_people"] == 2
    dima = next(seat for seat in bill["participants"] if seat["guest_name"] == "Дима")
    assert (dima["seat_index"], dima["allocated_amount"]) == (1, 10000)


def test_nothing_understood_changes_nothing(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    model["answer"] = {"items": [{"ref": "n1", "name": " "}], "assign": [{"item": 999, "people": ["Аня"]}]}

    refused = _say(client, bid, "э-э-э")

    assert refused.status_code == 422
    assert refused.json()["detail"] == {"code": "VOICE_NOTHING", "heard": "э-э-э"}
    assert all(seat["guest_name"] is None for seat in _seats(client, bid, owner))
    assert _say(client, bid, "   ").json()["detail"] == {"code": "VOICE_EMPTY"}


def _paid_guest(client, session, people=3):
    """A bill whose guest Ann has paid for her plov; a tea is still unpaid, or
    the bill would count as settled."""
    owner, bid = _table(client, session, people=people)
    ann = client.post("/users/", json={"telegram_id": 2, "username": "ann", "name": "Anna", "surname": "Petrova"}).json()["id"]
    plov = client.post(f"/bills/{bid}/items", json={"name": "Плов", "price": 50000, "count": 1}).json()
    tea = client.post(f"/bills/{bid}/items", json={"name": "Чай", "price": 5000, "count": 1}).json()
    me, seat, *rest = (s["id"] for s in _seats(client, bid, owner))
    client.post(f"/bills/{bid}/seats/{seat}/claim", json={"user_id": ann})
    client.post(
        f"/bills/{bid}/items/{plov['id']}/assign",
        json={"participant_id": seat, "is_assigned": True},
        headers=auth_headers(2),
    )
    assert client.post(f"/bills/{bid}/participants/{seat}/payment", json={"is_paid": True, "user_id": ann}).status_code == 200
    return owner, bid, me, seat, rest, plov, tea


def _line(client, bid, owner, item_id):
    return next(item for item in client.get(f"/bills/{bid}?user_id={owner}").json()["items"] if item["id"] == item_id)


def test_a_paid_share_stays_as_it_was_and_the_rest_is_done(client: TestClient, session: Session, model):
    owner, bid, me, seat, _rest, plov, tea = _paid_guest(client, session)
    model["answer"] = {"items": [], "assign": [
        {"item": plov["id"], "people": [me], "change": "set"},
        {"item": tea["id"], "people": [me], "change": "set"},
    ]}

    body = _say(client, bid, "плов мой, чай тоже мой").json()

    assert (body["assigned"], body["held"]) == (1, ["Плов"])
    assert _line(client, bid, owner, plov["id"])["assigned_participant_ids"] == [seat]
    assert _line(client, bid, owner, tea["id"])["assigned_participant_ids"] == [me]


def test_only_a_paid_line_said_is_explained_rather_than_refused(client: TestClient, session: Session, model):
    owner, bid, me, seat, _rest, plov, _tea = _paid_guest(client, session)
    model["answer"] = {"items": [], "assign": [{"item": plov["id"], "people": [me]}]}

    told = _say(client, bid, "плов мой")

    assert told.status_code == 200
    assert (told.json()["assigned"], told.json()["held"]) == (0, ["Плов"])
    assert _line(client, bid, owner, plov["id"])["assigned_participant_ids"] == [seat]


def test_a_new_service_charge_is_added_but_not_shared_over_a_paid_share(client: TestClient, session: Session, model):
    owner, bid, *_ = _paid_guest(client, session)
    model["answer"] = {"items": [{"ref": "n1", "name": "Обслуживание", "count": 1, "amount": 5500, "is_shared_globally": True}]}

    body = _say(client, bid, "обслуживание десять процентов").json()

    assert (body["added"], body["held"]) == (1, ["Обслуживание"])
    service = next(item for item in body["bill"]["items"] if item["name"] == "Обслуживание")
    assert service["is_shared_globally"] is False and service["assigned_participant_ids"] == []
    assert body["bill"]["total_sum"] == 60500


def test_a_paid_guest_is_found_by_their_first_name_and_not_seated_twice(client: TestClient, session: Session, model):
    owner, bid, me, seat, rest, _plov, tea = _paid_guest(client, session)
    model["answer"] = {"items": [], "assign": [{"item": tea["id"], "people": ["Anna"], "change": "add"}]}

    body = _say(client, bid, "Анна тоже пила чай").json()

    # Anna is the paid guest: adding the tea to her plate would move what she paid.
    assert body["held"] == ["Чай"] and body["unseated"] == []
    assert [s["guest_name"] for s in body["bill"]["participants"] if s["id"] in rest] == [None]


def test_no_seat_is_laid_when_it_would_move_a_paid_share_of_a_shared_line(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    ann = client.post("/users/", json={"telegram_id": 2, "username": "ann"}).json()["id"]
    plov = client.post(f"/bills/{bid}/items", json={"name": "Плов", "price": 50000, "count": 1}).json()
    tea = client.post(f"/bills/{bid}/items", json={"name": "Чай", "price": 6000, "count": 1}).json()
    me, seat, bob = (s["id"] for s in _seats(client, bid, owner))
    client.patch(f"/bills/{bid}/participants/{bob}", json={"user_id": owner, "guest_name": "Борис"})
    model["answer"] = {"items": [], "assign": [{"item": tea["id"], "everyone": True}]}
    assert _say(client, bid, "чай на всех").json()["assigned"] == 1
    client.post(f"/bills/{bid}/seats/{seat}/claim", json={"user_id": ann})
    client.post(f"/bills/{bid}/items/{plov['id']}/assign", json={"participant_id": seat, "is_assigned": True}, headers=auth_headers(2))
    assert client.post(f"/bills/{bid}/participants/{seat}/payment", json={"is_paid": True, "user_id": ann}).status_code == 200
    model["answer"] = {"items": [{"ref": "n1", "name": "Сок", "count": 1, "amount": 7000}], "assign": [{"item": "n1", "people": ["Дима"]}]}

    body = _say(client, bid, "сок Диме").json()

    # Every seat is taken, and a fourth would cut the shared tea four ways.
    assert (body["added"], body["assigned"], body["unseated"]) == (1, 0, ["Дима"])
    assert len(body["bill"]["participants"]) == 3


def test_also_keeps_who_had_it_and_did_not_takes_one_off(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    me, ann, bob = (seat["id"] for seat in _seats(client, bid, owner))
    pizza = client.post(f"/bills/{bid}/items", json={"name": "Пицца", "price": 90000, "count": 1}).json()
    model["answer"] = {"items": [], "assign": [{"item": pizza["id"], "people": [me]}]}
    _say(client, bid, "пицца моя")

    model["answer"] = {"items": [], "assign": [{"item": pizza["id"], "people": ["Аня", "Борис"], "change": "add"}]}
    assert sorted(_say(client, bid, "Аня и Борис тоже ели пиццу").json()["bill"]["items"][0]["assigned_participant_ids"]) == [me, ann, bob]

    model["answer"] = {"items": [], "assign": [{"item": pizza["id"], "people": ["Борис"], "change": "remove"}]}
    bill = _say(client, bid, "Борис не ел пиццу").json()["bill"]
    assert sorted(bill["items"][0]["assigned_participant_ids"]) == [me, ann]
    assert [s["allocated_amount"] for s in bill["participants"]] == [45000, 45000, 0]

    model["answer"] = {"items": [], "assign": [{"item": pizza["id"], "people": ["Борис"], "change": "set"}]}
    bill = _say(client, bid, "пиццу ел Борис").json()["bill"]
    assert bill["items"][0]["assigned_participant_ids"] == [bob]


def test_one_more_unit_goes_to_a_portion_nobody_has_yet(client: TestClient, session: Session, model):
    owner, bid = _table(client, session, people=2)
    me, guest = (seat["id"] for seat in _seats(client, bid, owner))
    beer = client.post(f"/bills/{bid}/items", json={"name": "Пиво", "price": 30000, "count": 3}).json()
    model["answer"] = {"items": [], "assign": [{"item": beer["id"], "people": [me], "portions": 2}]}
    _say(client, bid, "два пива мне")

    model["answer"] = {"items": [], "assign": [{"item": beer["id"], "people": [guest], "portions": 1, "change": "add"}]}
    bill = _say(client, bid, "ещё одно пиво гостю").json()["bill"]

    allocated = {seat["id"]: seat["allocated_amount"] for seat in bill["participants"]}
    assert (allocated[me], allocated[guest], bill["unallocated_sum"]) == (60000, 30000, 0)


def test_everyone_but_one_is_the_rest_of_the_table(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    me, ann, bob = (seat["id"] for seat in _seats(client, bid, owner))
    salad = client.post(f"/bills/{bid}/items", json={"name": "Салат", "price": 60000, "count": 1}).json()
    model["answer"] = {"items": [], "assign": [{"item": salad["id"], "people": [bob], "everyone": True, "change": "remove"}]}

    bill = _say(client, bid, "салат на всех, кроме Бориса").json()["bill"]

    line = bill["items"][0]
    assert line["is_shared_globally"] is False
    assert sorted(line["assigned_participant_ids"]) == [me, ann]


def test_a_name_said_twice_is_one_person_and_two_like_it_are_nobody(client: TestClient, session: Session, model):
    owner, bid = _table(client, session, people=4)
    me, first, second, third = (seat["id"] for seat in _seats(client, bid, owner))
    for seat, name in ((first, "Саша Иванов"), (second, "Саша Петров")):
        client.patch(f"/bills/{bid}/participants/{seat}", json={"user_id": owner, "guest_name": name})
    model["answer"] = {
        "items": [{"ref": "n1", "name": "Кола", "amount": 15000}, {"ref": "n2", "name": "Чай", "amount": 10000}, {"ref": "n3", "name": "Сок", "amount": 12000}],
        "assign": [
            {"item": "n1", "people": ["Аня"]},
            {"item": "n2", "people": ["аня"]},
            {"item": "n3", "people": ["Саша"]},
        ],
    }

    body = _say(client, bid, "кола и чай Ане, сок Саше").json()

    seats = {seat["id"]: seat for seat in body["bill"]["participants"]}
    assert seats[third]["guest_name"] == "Аня" and seats[third]["allocated_amount"] == 25000
    assert body["unseated"] == ["Саша"]
    assert len(seats) == 4


def test_a_bill_without_a_name_takes_the_one_said(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    client.patch(f"/bills/{bid}", json={"user_id": owner, "title": None})
    model["answer"] = {"title": "Ужин в Рыбе", "items": [{"ref": "n1", "name": "Рыба", "amount": 120000}]}
    assert _say(client, bid, "ужин в Рыбе, рыба 120").json()["bill"]["title"] == "Ужин в Рыбе"

    model["answer"] = {"title": "Обед", "items": [{"ref": "n1", "name": "Чай", "amount": 10000}]}
    assert _say(client, bid, "обед, чай 10").json()["bill"]["title"] == "Ужин в Рыбе"


def test_shares_set_by_hand_survive_lines_that_only_get_added(client: TestClient, session: Session, model):
    owner, bid = _table(client, session, people=2)
    client.post(f"/bills/{bid}/items", json={"name": "Плов", "price": 80000, "count": 1})
    me, guest = (seat["id"] for seat in _seats(client, bid, owner))
    assert client.post(
        f"/bills/{bid}/assign-amount", json={"participant_id": guest, "allocated_amount": 30000},
    ).status_code == 200
    model["answer"] = {"items": [{"ref": "n1", "name": "Чай", "amount": 10000}]}

    bill = _say(client, bid, "чай 10").json()["bill"]

    assert bill["split_type"] != "by_items"
    assert {seat["id"]: seat["allocated_amount"] for seat in bill["participants"]}[guest] == 30000
    assert bill["total_sum"] == 90000


def test_a_recording_is_transcribed_with_the_bill_s_names_as_a_hint(client: TestClient, session: Session, model):
    owner, bid = _table(client, session, people=1)
    client.post(f"/bills/{bid}/items", json={"name": "Манты", "price": 20000, "count": 1})
    model["heard"] = "кола 15"
    model["answer"] = {"items": [{"ref": "n1", "name": "Кола", "count": 1, "amount": 15000}], "assign": []}

    heard = client.post(
        f"/bills/{bid}/voice/hear", files={"audio": ("blob", b"\x1aE\xdf\xa3", "audio/webm;codecs=opus")},
    )

    # Heard first, so the app can show the words while the bill is filled from them.
    assert heard.json() == {"heard": "кола 15"}
    assert model["chat"] is None
    name, data = model["transcription"]["file"]
    assert (name, data) == ("voice.webm", b"\x1aE\xdf\xa3")
    assert "Манты" in model["transcription"]["prompt"]
    assert _say(client, bid, heard.json()["heard"]).json()["added"] == 1
    assert "кола 15" in model["chat"]["messages"][1]["content"]
    # Neither call may hold the request past what the app waits for it.
    assert model["options"] == [{"timeout": 40, "max_retries": 0}] * 2

    wrong = client.post(f"/bills/{bid}/voice/hear", files={"audio": ("x.txt", b"hi", "text/plain")})
    assert wrong.json()["detail"] == {"code": "VOICE_FORMAT"}
    model["heard"] = ""
    silence = client.post(f"/bills/{bid}/voice/hear", files={"audio": ("blob", b"\x00", "audio/webm")})
    assert silence.json()["detail"] == {"code": "VOICE_EMPTY"}


def test_only_the_owner_tells_the_bill(client: TestClient, session: Session, model):
    _owner, bid = _table(client, session)
    client.post("/users/", json={"telegram_id": 2, "username": "g"})

    refused = client.post(f"/bills/{bid}/voice", data={"text": "кола"}, headers=auth_headers(2))

    assert refused.status_code == 403


def test_a_guest_is_found_by_the_label_the_app_shows_them_under(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    me, first, second = (seat["id"] for seat in _seats(client, bid, owner))
    model["answer"] = {"items": [{"ref": "n1", "name": "Кола", "amount": 15000}], "assign": [{"item": "n1", "people": ["Гость 2"]}]}

    bill = _say(client, bid, "колу Гостю 2").json()["bill"]

    seats = {seat["id"]: seat for seat in bill["participants"]}
    assert (seats[second]["allocated_amount"], seats[second]["guest_name"]) == (15000, None)
    assert (seats[first]["allocated_amount"], seats[first]["guest_name"]) == (0, None)


def test_on_a_bill_split_by_hand_a_paid_share_holds_every_hand_out(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    ann = client.post("/users/", json={"telegram_id": 2, "username": "ann"}).json()["id"]
    client.post(f"/bills/{bid}/items", json={"name": "Плов", "price": 80000, "count": 1})
    me, seat, _empty = (s["id"] for s in _seats(client, bid, owner))
    client.post(f"/bills/{bid}/seats/{seat}/claim", json={"user_id": ann})
    assert client.post(f"/bills/{bid}/assign-amount", json={"participant_id": seat, "allocated_amount": 30000}).status_code == 200
    assert client.post(f"/bills/{bid}/participants/{seat}/payment", json={"is_paid": True, "user_id": ann}).status_code == 200
    model["answer"] = {"items": [{"ref": "n1", "name": "Чай", "amount": 10000}], "assign": [{"item": "n1", "people": [me]}]}

    told = _say(client, bid, "чай 10, мой")

    # Handing the tea out would split the bill by dishes and take Ann's paid 30 000 away.
    assert told.status_code == 200
    body = told.json()
    assert (body["added"], body["assigned"], body["held"]) == (1, 0, ["Чай"])
    assert body["bill"]["split_type"] != "by_items"
    assert {s["id"]: s["allocated_amount"] for s in body["bill"]["participants"]}[seat] == 30000


def test_a_place_said_becomes_the_bill_s_place(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    model["answer"] = {"place": "Рейхан", "items": [{"ref": "n1", "name": "Чай", "amount": 10000}]}

    body = _say(client, bid, "мы в кафе Рейхан, чай 10").json()

    assert body["bill"]["place"] == "Рейхан"
    bill = session.get(Bill, bid)
    session.refresh(bill)
    # Said by the owner: the labeling job will not guess over it.
    assert bill.place_by_owner is True

    model["answer"] = {"place": "Рейхан"}
    assert _say(client, bid, "мы в Рейхане").status_code == 200


def test_the_speaker_said_as_a_word_and_a_line_said_by_name_still_land(client: TestClient, session: Session, model):
    owner, bid = _table(client, session)
    me, first, _second = (seat["id"] for seat in _seats(client, bid, owner))
    # What a less careful model answers: no refs, «Я» for the speaker, lines by name.
    model["answer"] = {
        "items": [{"name": "Бургер", "count": 2, "amount": 90000}, {"name": "Кола", "count": 2, "amount": 24000}],
        "assign": [
            {"item": "бургер", "people": ["Я", "Парахатдин"]},
            {"item": "Кола", "people": ["я", "Парахатдин"]},
        ],
    }

    bill = _say(client, bid, "я и Парахатдин мы с ним пополам всё кушали").json()["bill"]

    seats = {seat["id"]: seat for seat in bill["participants"]}
    assert (seats[me]["allocated_amount"], seats[first]["allocated_amount"]) == (57000, 57000)
    assert seats[first]["guest_name"] == "Парахатдин"
    assert seats[me]["guest_name"] is None
