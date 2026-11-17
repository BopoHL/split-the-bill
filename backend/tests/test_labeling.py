"""The labeling job: what each receipt line is, and where each bill was run up.

The model is stubbed: the job's part is asking about each wording once, in
batches, picking up where it stopped, and keeping what it was told — what came
after labeling began on its own, the history before only when asked to.
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.jobs import labeling
from app.models import Bill, BillItem, DishGroup, DishKind, DishLabel, Place, ReceiptTask
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.services.labeling import DishAnswer, KindNames
from app.services.labeling_control import HistoryState, LabelingControl
from app.services.places import set_place
from app.worker import _enrich_bill

BEGAN = datetime.utcnow() - timedelta(hours=1)
LATER = datetime.utcnow() + timedelta(minutes=5)


@pytest.fixture(autouse=True)
def labeling_began(session: Session):
    """Before the bills each test makes: they are new data, labeled on their own."""
    LabelingControl(session).since(BEGAN)


@pytest.fixture
def model(monkeypatch):
    asked = {"dishes": [], "places": []}

    def label_dishes(names, model):
        asked["dishes"].append(list(names))
        return [
            DishAnswer(DishGroup.FOOD, "burger", KindNames("Бургер", "Burger", "Burger"))
            if "burger" in name.lower()
            else DishAnswer(DishGroup.DRINK, "cappuccino", KindNames("Капучино", "Kapuchino", "Cappuccino"))
            if "cappuccino" in name.lower()
            else DishAnswer(DishGroup.FEE, None, None)
            for name in names
        ]

    def name_places(questions, model):
        asked["places"].append(questions)
        return ["Caffeine" if question.scanned else ("Evos" if "Evos" in (question.title or "") else None) for question in questions]

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(labeling, "label_dishes", label_dishes)
    monkeypatch.setattr(labeling, "name_places", name_places)
    return asked


def _bill(session: Session, title: str | None, lines: list[str], owner_id: int = 1) -> Bill:
    bill = Bill(owner_id=owner_id, title=title, created_at=datetime.utcnow())
    session.add(bill)
    session.commit()
    for name in lines:
        session.add(BillItem(bill_id=bill.id, name=name, price=100, item_sum=100))
    session.commit()
    return bill


@pytest.fixture
def owner(client: TestClient) -> int:
    return client.post("/users/", json={"telegram_id": 990, "username": "owner"}).json()["id"]


def test_each_wording_is_labeled_once_and_its_kind_named(session: Session, model, owner):
    _bill(session, "Обед", ["Burger Double", "Cappuccino 0,4", "Обслуживание 10%"], owner)
    _bill(session, "Ужин", ["burger double ", "Cappuccino 0,4"], owner)

    labeling.run(session, LATER)
    labeling.run(session, LATER)

    assert model["dishes"] == [["Burger Double", "Cappuccino 0,4", "Обслуживание 10%"]]
    labels = {label.name_key: (label.group, label.kind) for label in session.exec(select(DishLabel)).all()}
    assert labels == {
        "burger double": ("food", "burger"),
        "cappuccino 0,4": ("drink", "cappuccino"),
        "обслуживание 10%": ("fee", None),
    }
    assert session.get(DishKind, "cappuccino").ru == "Капучино"


def test_a_long_backlog_goes_a_batch_at_a_time(session: Session, model, owner, monkeypatch):
    monkeypatch.setattr(labeling, "DISHES_PER_CALL", 2)
    _bill(session, None, ["Burger A", "Burger B", "Burger C"], owner)

    labeling.run(session, LATER)
    labeling.run(session, LATER)

    assert model["dishes"] == [["Burger A", "Burger B"], ["Burger C"]]


def test_a_renamed_line_is_labeled_under_its_new_name(session: Session, model, owner):
    bill = _bill(session, None, ["Burger"], owner)
    labeling.run(session, LATER)

    line = session.exec(select(BillItem).where(BillItem.bill_id == bill.id)).one()
    line.name = "Cappuccino"
    line.updated_at = datetime.utcnow() + timedelta(seconds=1)
    session.add(line)
    session.commit()
    labeling.run(session, LATER)

    assert model["dishes"][-1] == ["Cappuccino"]


def test_a_line_committed_after_a_later_one_is_not_stepped_over(session: Session, model, owner):
    bill = _bill(session, None, ["Burger"], owner)
    labeling.run(session, datetime.utcnow())

    # Stamped as it was written, before the burger; committed only after it.
    session.add(BillItem(
        bill_id=bill.id, name="Cappuccino", price=100, item_sum=100, updated_at=datetime.utcnow() - timedelta(seconds=30),
    ))
    session.commit()
    labeling.run(session, LATER)

    assert model["dishes"] == [["Cappuccino", "Burger"]]


def test_places_come_from_the_receipt_or_a_title_that_names_one(session: Session, model, owner):
    scanned = _bill(session, "Ужин", [], owner)
    session.add(ReceiptTask(bill_id=scanned.id, llm_response=json.dumps({"title": "CAFFEINE Ц-1 ООО", "items": []})))
    named = _bill(session, "Evos с командой", [], owner)
    again = _bill(session, "Кофе", [], owner)
    session.add(ReceiptTask(bill_id=again.id, llm_response=json.dumps({"place": "Caffeine", "title": "Caffeine", "items": []})))
    nowhere = _bill(session, None, [], owner)
    session.commit()

    labeling.run(session, LATER)

    session.expire_all()
    places = {place.id: place.name for place in session.exec(select(Place)).all()}
    assert sorted(places.values()) == ["Caffeine", "Evos"]
    assert places[session.get(Bill, scanned.id).place_id] == "Caffeine"
    assert session.get(Bill, again.id).place_id == session.get(Bill, scanned.id).place_id
    assert places[session.get(Bill, named.id).place_id] == "Evos"
    assert session.get(Bill, nowhere.id).place_id is None
    assert session.get(Bill, nowhere.id).place_checked_at is not None
    asked_titles = [question.title for question in model["places"][0]]
    assert None not in asked_titles


def test_a_line_the_model_left_out_is_asked_again_when_it_turns_up(session: Session, model, owner, monkeypatch):
    _bill(session, None, ["Burger", "Хинкали"], owner)
    monkeypatch.setattr(labeling, "label_dishes", lambda names, model: [
        DishAnswer(DishGroup.FOOD, "burger", KindNames("Бургер", "Burger", "Burger")), None,
    ])

    labeling.run(session, LATER)

    assert [label.name_key for label in session.exec(select(DishLabel)).all()] == ["burger"]


def test_the_place_the_owner_gave_while_the_model_was_asked_stands(
    client: TestClient, session: Session, model, owner, monkeypatch
):
    bill = _bill(session, "Evos с командой", [], owner)
    bill.created_at = datetime.utcnow() - timedelta(minutes=5)
    session.add(bill)
    session.commit()

    def owner_speaks_meanwhile(questions, model):
        with Session(session.get_bind()) as elsewhere:
            set_place(elsewhere, elsewhere.get(Bill, bill.id), owner, "Плов Центр", datetime.utcnow())
        return ["Evos"]

    monkeypatch.setattr(labeling, "name_places", owner_speaks_meanwhile)
    labeling.run(session)

    session.expire_all()
    assert session.get(Place, session.get(Bill, bill.id).place_id).name == "Плов Центр"


def test_a_new_scan_does_not_ask_again_where_the_owner_said_the_bill_was(session: Session, owner):
    bill = _bill(session, "Ужин", [], owner)
    set_place(session, bill, owner, "Плов Центр", datetime.utcnow())
    task = ReceiptTask(bill_id=bill.id)
    session.add(task)
    session.commit()

    _enrich_bill(session, BillRepository(session), UserRepository(session), task, bill, {"items": []})

    session.expire_all()
    assert session.get(Bill, bill.id).place_checked_at is not None


def test_a_new_title_asks_again_where_the_bill_was(client: TestClient, session: Session, model, owner):
    bill = _bill(session, "Ужин", [], owner)
    labeling.run(session, LATER)

    assert client.patch(f"/bills/{bill.id}", json={"title": "Evos с командой", "user_id": owner}).status_code == 200
    labeling.run(session, LATER)

    session.expire_all()
    assert session.get(Place, session.get(Bill, bill.id).place_id).name == "Evos"


def test_a_new_title_does_not_ask_again_where_the_owner_said_the_bill_was(client: TestClient, session: Session, owner):
    bill = _bill(session, "Ужин", [], owner)
    set_place(session, bill, owner, "Плов Центр", datetime.utcnow())

    assert client.patch(f"/bills/{bill.id}", json={"title": "Evos с командой", "user_id": owner}).status_code == 200

    session.expire_all()
    assert session.get(Bill, bill.id).place_checked_at is not None


def test_a_bill_just_made_waits_for_its_receipt(session: Session, model, owner):
    _bill(session, "Evos", [], owner)

    labeling.run(session, datetime.utcnow())

    assert model["places"] == []


def test_nothing_is_asked_without_a_model_key(session: Session, model, owner, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    _bill(session, "Evos", ["Burger"], owner)

    assert labeling.run(session, LATER) == 0
    assert model["dishes"] == [] and model["places"] == []


def test_the_owner_says_where_the_bill_was(client: TestClient, session: Session):
    owner = client.post("/users/", json={"telegram_id": 991, "username": "leo"}).json()["id"]
    guest = client.post("/users/", json={"telegram_id": 992, "username": "bob"}).json()["id"]
    bill_id = client.post("/bills/", json={"owner_id": owner, "total_sum": 100, "include_owner": True}).json()["id"]

    client.act_as(992)
    assert client.put(f"/bills/{bill_id}/place", json={"name": "Evos"}).status_code == 403
    client.act_as(991)
    assert client.put(f"/bills/{bill_id}/place", json={"name": "  Плов   Центр "}).json() == {"place": "Плов Центр"}
    assert client.get(f"/bills/{bill_id}?user_id={owner}").json()["place"] == "Плов Центр"
    assert client.put(f"/bills/{bill_id}/place", json={"name": ""}).json() == {"place": None}
    client.act_as(None)

    session.expire_all()
    assert session.get(Bill, bill_id).place_checked_at is not None
    assert guest


def test_the_places_i_have_been_come_back_latest_first(client: TestClient, session: Session):
    me = client.post("/users/", json={"telegram_id": 993, "username": "me"}).json()["id"]
    first = client.post("/bills/", json={"owner_id": me, "total_sum": 100, "include_owner": True}).json()["id"]
    second = client.post("/bills/", json={"owner_id": me, "total_sum": 100, "include_owner": True}).json()["id"]
    client.act_as(993)
    client.put(f"/bills/{first}/place", json={"name": "Evos"})
    client.put(f"/bills/{second}/place", json={"name": "Caffeine"})
    session.expire_all()
    older = session.get(Bill, first)
    older.created_at = datetime.utcnow() - timedelta(days=3)
    session.add(older)
    session.commit()

    assert client.get(f"/users/{me}/places").json() == ["Caffeine", "Evos"]
    client.act_as(None)


def _from_before(session: Session, bill: Bill) -> Bill:
    """Moved back to before labeling began: part of the history."""
    long_ago = BEGAN - timedelta(days=30)
    for line in session.exec(select(BillItem).where(BillItem.bill_id == bill.id)).all():
        line.updated_at = long_ago
        session.add(line)
    bill.created_at = bill.updated_at = long_ago
    session.add(bill)
    session.commit()
    return bill


def test_the_history_waits_until_the_admin_starts_it(session: Session, model, owner):
    old = _from_before(session, _bill(session, "Evos с командой", ["Burger Old"], owner))
    _bill(session, "Обед", ["Cappuccino"], owner)

    labeling.run(session, LATER)

    assert model["dishes"] == [["Cappuccino"]]
    assert [question.title for question in model["places"][0]] == ["Обед"]
    session.expire_all()
    assert session.get(Bill, old.id).place_checked_at is None
    assert LabelingControl(session).history() is None


def test_the_history_goes_a_batch_a_tick_and_says_how_far_it_got(session: Session, model, owner, monkeypatch):
    monkeypatch.setattr(labeling, "DISHES_PER_CALL", 1)
    _from_before(session, _bill(session, "Evos с командой", ["Burger A", "Burger B"], owner))
    _from_before(session, _bill(session, None, [], owner))
    control = LabelingControl(session)

    started = control.start_history(LATER)
    assert (started.lines_total, started.bills_total) == (2, 2)

    labeling.run(session, LATER)
    halfway = control.history()
    assert (halfway.state, halfway.lines_done, halfway.bills_done) == (HistoryState.RUNNING, 1, 2)

    labeling.run(session, LATER)
    labeling.run(session, LATER)
    done = control.history()
    assert (done.state, done.lines_done, done.finished_at) == (HistoryState.DONE, 2, LATER)
    assert model["dishes"] == [["Burger A"], ["Burger B"]]
    session.expire_all()
    assert all(bill.place_checked_at for bill in session.exec(select(Bill)).all())


def test_a_paused_history_resumes_where_it_stopped(session: Session, model, owner, monkeypatch):
    monkeypatch.setattr(labeling, "DISHES_PER_CALL", 1)
    _from_before(session, _bill(session, None, ["Burger A", "Burger B"], owner))
    control = LabelingControl(session)
    control.start_history(LATER)
    labeling.run(session, LATER)

    control.pause_history()
    labeling.run(session, LATER)
    assert model["dishes"] == [["Burger A"]]

    resumed = control.start_history(LATER)
    labeling.run(session, LATER)
    assert (resumed.state, resumed.lines_done) == (HistoryState.RUNNING, 1)
    assert model["dishes"] == [["Burger A"], ["Burger B"]]


def test_what_went_wrong_is_kept_for_the_admin_until_it_works_again(session: Session, model, owner, monkeypatch):
    _bill(session, None, ["Burger"], owner)
    working = labeling.label_dishes

    def refused(names, model):
        raise RuntimeError("The model `gpt-x` does not exist")

    monkeypatch.setattr(labeling, "label_dishes", refused)
    with pytest.raises(RuntimeError):
        labeling.run(session, LATER)
    failed = LabelingControl(session).status()
    assert (failed.last_error, failed.last_error_at, failed.last_labeled_at) == (
        "The model `gpt-x` does not exist", LATER, None,
    )

    monkeypatch.setattr(labeling, "label_dishes", working)
    labeling.run(session, LATER)
    recovered = LabelingControl(session).status()
    assert (recovered.last_error, recovered.last_labeled_at) == (None, LATER)
