"""A bill shared into a chat: what the post says, and how it is kept current.

Telegram is stubbed at the edges — the prepared message, the inline edit and the
callback answer — so these check what we send and when we send it.
"""
import io
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

import app.services.shared_bill_service as shared
from app.models import Bill, BillItem, BillStatus, BillUser, SenderAccount, SenderAccountStatus, SharedBillMessage, User
from app.services.shared_bill_service import Refresh, SharedBillService
from tests.telegram_world import next_update_id

OWNER = 7001


class _Faces:
    """Profile photos as Telegram would give them: only those in `known`."""

    def __init__(self):
        self.known: dict[int, Image.Image] = {}

    def for_people(self, telegram_ids):
        return {telegram_id: self.known[telegram_id] for telegram_id in telegram_ids if telegram_id in self.known}


@pytest.fixture
def telegram(monkeypatch):
    calls = {"prepared": [], "edits": [], "chat_edits": [], "answers": [], "alerts": [], "opened": [], "faces": _Faces()}

    def answer(callback_id, text=None, show_alert=False, url=None):
        (calls["alerts"] if show_alert else calls["answers"]).append(text)
        calls["opened"].append(url)

    monkeypatch.setattr(shared, "profile_photos", calls["faces"])
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz")
    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(shared, "save_prepared_text_message", lambda uid, **message: calls["prepared"].append((uid, message)) or "PREPARED")
    monkeypatch.setattr(shared, "edit_inline_message_text", lambda *args: calls["edits"].append(args))
    monkeypatch.setattr(shared, "edit_chat_message_text", lambda *args: calls["chat_edits"].append(args))
    monkeypatch.setattr(shared, "answer_callback_query", answer)
    return calls


def _bill(client: TestClient, people: int = 2) -> tuple[dict, dict]:
    owner = client.post("/users/", json={"telegram_id": OWNER, "username": "leo", "name": "Leonid"}).json()
    bill = client.post("/bills/", json={
        "owner_id": owner["id"], "total_sum": 0, "title": "Ужин", "include_owner": True,
        "expected_people": people, "payment_details": "8600 1234 5678 9012",
    }).json()
    client.post(f"/bills/{bill['id']}/items", json={"name": "Самса", "price": 12000, "count": 2})
    return owner, bill


def _share(client: TestClient, bill: dict, language: str | None = None) -> str:
    response = client.post(f"/bills/{bill['id']}/prepare-share", json={"lang": language} if language else {})
    assert response.status_code == 200, response.text
    return response.json()["prepared_message_id"]


def _tap(client: TestClient, data: str, telegram_id: int = 99, name: str = "Dana", *, inline_id: str | None = "INLINE-1", chat: dict | None = None) -> None:
    callback = {
        "id": "cb", "data": data, "chat_instance": "1",
        "from": {"id": telegram_id, "language_code": "en", "first_name": name},
    }
    if inline_id:
        callback["inline_message_id"] = inline_id
    if chat:
        callback["message"] = chat
    client.post("/telegram/webhook", json={"update_id": next_update_id(), "callback_query": callback})


def _press(client: TestClient, record_code: str, inline_id: str = "INLINE-1") -> None:
    _tap(client, f"share_refresh:{record_code}", inline_id=inline_id)


def _free_seats(session: Session, bill: dict) -> list[BillUser]:
    session.expire_all()
    return session.exec(
        select(BillUser).where(BillUser.bill_id == bill["id"], BillUser.user_id.is_(None)).order_by(BillUser.seat_index)
    ).all()


def _seat_of(session: Session, telegram_id: int) -> BillUser | None:
    session.expire_all()
    return session.exec(select(BillUser).join(User, BillUser.user_id == User.id).where(User.telegram_id == telegram_id)).first()


def _give_everything_to(client: TestClient, session: Session, bill: dict, seat_id: int) -> None:
    for item in session.exec(select(BillItem).where(BillItem.bill_id == bill["id"])).all():
        response = client.post(f"/bills/{bill['id']}/items/{item.id}/assign", json={"participant_id": seat_id, "is_assigned": True})
        assert response.status_code == 200, response.text


def _callbacks(markup: dict, prefix: str) -> list[str]:
    return [button["callback_data"] for row in markup["inline_keyboard"] for button in row if button.get("callback_data", "").startswith(prefix)]


def _record(session: Session) -> SharedBillMessage:
    session.expire_all()
    return session.exec(select(SharedBillMessage)).one()


def test_sharing_prepares_a_text_post_with_the_ticket_picture_above(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)

    assert _share(client, bill, "uz") == "PREPARED"

    record = _record(session)
    uid, message = telegram["prepared"][0]
    assert uid == OWNER
    assert message["result_id"] == f"share:{record.invite_code}"
    assert message["text_html"].startswith("👥 <b>Ishtirokchilar</b>\n\n")
    assert message["link_preview_options"] == {
        "url": f"https://split-the-bill.uz/api/bills/public/{bill['public_token']}/card.png?lang=uz&theme=light&v={record.fingerprint}",
        "prefer_large_media": True,
        "show_above_text": True,
    }
    [guest] = _free_seats(session, bill)
    take, paid, [open_button, refresh] = message["reply_markup"]["inline_keyboard"]
    assert take == [{"text": "👥 1-mehmon – olish", "callback_data": f"share_seat:{record.invite_code}:{guest.id}"}]
    assert paid == [
        {"text": "💳 Karta", "copy_text": {"text": "8600123456789012"}},
        {"text": "✅ To‘ladim", "callback_data": f"share_paid:{record.invite_code}"},
    ]
    assert open_button == {"text": "🧾 Ochish", "url": open_button["url"]}
    assert open_button["url"].endswith(f"startapp=inv_{record.invite_code}")
    assert refresh == {"text": "🔄 Yangilash", "callback_data": f"share_refresh:{record.invite_code}"}
    assert (record.language, record.inline_message_id) == ("uz", None)


def test_the_picture_is_drawn_in_the_sharers_theme_and_keeps_it(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)
    client.patch(f"/users/{owner['id']}/settings", json={"theme": "dark"})

    _share(client, bill)

    record = _record(session)
    assert record.theme == "dark"
    assert "&theme=dark&" in telegram["prepared"][0][1]["link_preview_options"]["url"]
    # Switching back later does not repaint a post already sent.
    client.patch(f"/users/{owner['id']}/settings", json={"theme": "light"})
    client.post(f"/bills/{bill['id']}/items", json={"name": "Чай", "price": 8000, "count": 1})
    SharedBillService(session).remember(record.invite_code, "INLINE-1")
    SharedBillService(session).refresh(_record(session), datetime.utcnow())
    assert "&theme=dark&" in telegram["edits"][-1][2]["url"]


def test_the_card_is_served_in_the_theme_it_is_linked_with(client: TestClient):
    _, bill = _bill(client)

    client.act_as(None)
    dark = client.get(f"/bills/public/{bill['public_token']}/card.png", params={"theme": "dark"})
    light = client.get(f"/bills/public/{bill['public_token']}/card.png")

    assert dark.status_code == light.status_code == 200
    assert Image.open(io.BytesIO(dark.content)).convert("RGB").getpixel((4, 4)) == (0x22, 0x20, 0x1C)
    assert Image.open(io.BytesIO(light.content)).convert("RGB").getpixel((4, 4)) == (0xEF, 0xE7, 0xD8)


def test_the_post_speaks_the_sharers_saved_language_when_none_is_given(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)
    client.patch(f"/users/{owner['id']}/settings", json={"language": "en"})

    _share(client, bill)

    assert _record(session).language == "en"
    assert telegram["prepared"][0][1]["text_html"].startswith("👥 <b>Participants</b>")


def test_a_chosen_share_is_remembered_by_the_message_it_became(client: TestClient, session: Session, telegram):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code

    client.post("/telegram/webhook", json={"update_id": next_update_id(), "chosen_inline_result": {
        "result_id": f"share:{code}", "inline_message_id": "INLINE-9", "from": {"id": OWNER}, "query": "",
    }})

    assert _record(session).inline_message_id == "INLINE-9"


def test_the_refresh_button_edits_the_post_only_when_the_bill_has_changed(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code

    _press(client, code)
    assert telegram["edits"] == []
    assert telegram["answers"] == ["Уже актуально"]

    client.post(f"/bills/{bill['id']}/items", json={"name": "Чай", "price": 8000, "count": 1})
    _press(client, code)

    inline_id, text, preview, markup = telegram["edits"][0]
    record = _record(session)
    assert inline_id == "INLINE-1"
    assert "Чай — 8 000 сум" in text
    assert preview["url"].endswith(f"v={record.fingerprint}")
    assert _callbacks(markup, "share_refresh:") == [f"share_refresh:{code}"]
    assert telegram["answers"][-1] == "Обновлено"

    client.post(f"/bills/{bill['id']}/items", json={"name": "Хлеб", "price": 2000, "count": 1})
    _press(client, code)
    assert len(telegram["edits"]) == 1
    assert telegram["answers"][-1] == "Уже актуально"


def test_a_refresh_is_counted_for_people_the_app_knows(client: TestClient, session: Session, telegram, product_events):
    owner, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code

    _tap(client, f"share_refresh:{code}", telegram_id=OWNER, name="Leonid")
    client.post(f"/bills/{bill['id']}/items", json={"name": "Чай", "price": 5000, "count": 1})
    _tap(client, f"share_refresh:{code}", telegram_id=OWNER, name="Leonid")
    _tap(client, f"share_refresh:{code}", telegram_id=OWNER, name="Leonid")
    # A stranger in the chat: answered, but not made an account to count it.
    _tap(client, f"share_refresh:{code}", telegram_id=555, name="Stranger")

    outcomes = [
        (distinct_id, properties["outcome"])
        for event, distinct_id, properties in product_events
        if event == "post_refreshed" and properties["bill_id"] == bill["id"]
    ]
    assert outcomes == [(str(owner["id"]), "unchanged"), (str(owner["id"]), "edited"), (str(owner["id"]), "cooldown")]
    assert session.exec(select(User).where(User.telegram_id == 555)).first() is None


def test_a_button_nobody_knows_says_the_bill_is_gone(client: TestClient, telegram):
    _press(client, "not-a-share")

    assert telegram["answers"] == ["This bill is no longer available"]


def test_a_deleted_message_is_forgotten(client: TestClient, session: Session, telegram, monkeypatch):
    _, bill = _bill(client)
    _share(client, bill)
    record = SharedBillService(session).remember(_record(session).invite_code, "INLINE-1")
    client.post(f"/bills/{bill['id']}/items", json={"name": "Чай", "price": 8000, "count": 1})
    monkeypatch.setattr(shared, "edit_inline_message_text", lambda *args: (_ for _ in ()).throw(
        RuntimeError("Telegram error: Bad Request: MESSAGE_ID_INVALID")
    ))

    assert SharedBillService(session).refresh(record, datetime.utcnow()) == Refresh.GONE
    assert _record(session).is_gone is True


def test_live_posts_follow_the_bill_until_it_closes(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)
    _share(client, bill)
    service = SharedBillService(session)
    service.remember(_record(session).invite_code, "INLINE-1")
    now = datetime.utcnow()

    assert service.refresh_due(now, limit=10) == 0

    client.post(f"/bills/{bill['id']}/items", json={"name": "Чай", "price": 8000, "count": 1})
    assert service.refresh_due(now, limit=10) == 1
    assert service.refresh_due(now, limit=10) == 0

    stored = session.get(Bill, bill["id"])
    stored.status = BillStatus.CLOSED
    session.add(stored)
    session.commit()
    assert service.refresh_due(now, limit=10) == 1
    final = telegram["edits"][-1]
    assert "🔒" in final[1]
    assert final[3]["inline_keyboard"] == [final[3]["inline_keyboard"][0]]
    assert _record(session).is_final is True
    assert service.refresh_due(now + timedelta(minutes=5), limit=10) == 0


def test_a_busy_tick_edits_no_more_than_its_share(client: TestClient, session: Session, telegram):
    _, bill = _bill(client)
    for _ in range(3):
        _share(client, bill)
    service = SharedBillService(session)
    for index, record in enumerate(session.exec(select(SharedBillMessage)).all()):
        service.remember(record.invite_code, f"INLINE-{index}")
    client.post(f"/bills/{bill['id']}/items", json={"name": "Чай", "price": 8000, "count": 1})

    assert service.refresh_due(datetime.utcnow(), limit=2) == 2
    assert service.refresh_due(datetime.utcnow(), limit=2) == 1


def test_between_full_passes_a_tick_rewrites_only_the_bills_that_changed(client: TestClient, session: Session, telegram, monkeypatch):
    from app.jobs import share_refresh
    from app.notifier import notifier

    _, quiet = _bill(client)
    _share(client, quiet)
    _, busy = _bill(client)
    _share(client, busy)
    service = SharedBillService(session)
    for record in session.exec(select(SharedBillMessage)).all():
        service.remember(record.invite_code, f"INLINE-{record.bill_id}")
    now = datetime.utcnow()
    monkeypatch.setattr(share_refresh, "_full_pass_at", None)
    assert share_refresh.run(session, now) == 0
    notifier.take_changed()

    # Closed behind the app's back: nothing announces it.
    stored = session.get(Bill, quiet["id"])
    stored.status = BillStatus.CLOSED
    session.add(stored)
    session.commit()
    client.post(f"/bills/{busy['id']}/items", json={"name": "Чай", "price": 8000, "count": 1})

    assert share_refresh.run(session, now + timedelta(seconds=30)) == 1
    assert telegram["edits"][-1][0] == f"INLINE-{busy['id']}"
    # The next full pass catches what nobody announced.
    assert share_refresh.run(session, now + share_refresh.FULL_PASS_EVERY) == 1
    assert telegram["edits"][-1][0] == f"INLINE-{quiet['id']}"


def test_a_face_that_loads_later_puts_a_new_picture_in_the_post(client: TestClient, session: Session, telegram):
    """A photo Telegram would not give the first time — a timeout, say — must
    not stay missing: the picture of that state is cached by its URL for good."""
    _, bill = _bill(client)
    _share(client, bill)
    record = _record(session)
    faceless = record.fingerprint
    _press(client, record.invite_code)
    assert telegram["edits"] == []

    telegram["faces"].known[OWNER] = Image.new("RGB", (8, 8))
    _press(client, record.invite_code)

    [(_, _, preview, _)] = telegram["edits"]
    assert _record(session).fingerprint != faceless
    assert preview["url"].endswith(f"v={_record(session).fingerprint}")


def test_a_free_seat_under_the_post_goes_to_whoever_taps_it(client: TestClient, session: Session, telegram):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)

    _tap(client, f"share_seat:{code}:{guest.id}")

    assert telegram["answers"] == ["Guest 1 is your seat now"]
    assert _seat_of(session, 99).id == guest.id
    # Dana never started the bot: the answer opens its chat, so it can remind her.
    assert telegram["opened"] == [f"https://t.me/SplitTheBillsBot?start=post_{code}"]
    # Everyone in the chat sees it at once: the post names her, and the seat
    # is no longer on offer.
    _, text, _, markup = telegram["edits"][-1]
    assert "<b>Dana</b>" in text
    assert _callbacks(markup, "share_seat:") == []
    assert _record(session).inline_message_id == "INLINE-1"


def test_a_sender_account_taking_a_seat_is_not_sent_to_the_bot_it_never_hears(
    client: TestClient, session: Session, telegram
):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)
    session.add(SenderAccount(phone="+998900000009", telegram_id=99, status=SenderAccountStatus.ACTIVE))
    session.commit()

    _tap(client, f"share_seat:{code}:{guest.id}")

    assert telegram["answers"] == ["Guest 1 is your seat now"]
    assert telegram["opened"] == [None]


def test_a_seat_is_taken_once_and_by_someone_without_one(client: TestClient, session: Session, telegram):
    _, bill = _bill(client, people=3)
    _share(client, bill)
    code = _record(session).invite_code
    first, second = _free_seats(session, bill)
    _tap(client, f"share_seat:{code}:{first.id}")

    _tap(client, f"share_seat:{code}:{first.id}")
    assert telegram["answers"][-1] == "This seat is already yours"

    _tap(client, f"share_seat:{code}:{first.id}", telegram_id=100, name="Eve")
    # Moving leaves the dishes behind, which is asked in the app, not here.
    _tap(client, f"share_seat:{code}:{second.id}")
    _tap(client, f"share_seat:{code}:{second.id}", telegram_id=OWNER, name="Leonid")
    assert telegram["alerts"] == [
        "Someone has already taken this seat",
        "You already have a seat on this bill. You can change seats in the app",
        "You already have a seat on this bill. You can change seats in the app",
    ]
    assert _seat_of(session, 100) is None
    assert [seat.id for seat in _free_seats(session, bill)] == [second.id]


def test_i_have_paid_marks_the_seat_of_whoever_taps(client: TestClient, session: Session, telegram):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)
    _tap(client, f"share_seat:{code}:{guest.id}")
    _give_everything_to(client, session, bill, guest.id)

    _tap(client, f"share_paid:{code}")

    assert telegram["answers"][-1] == "Marked: you paid 24 000 uzs"
    assert _seat_of(session, 99).is_paid is True
    # Nothing is owed any more, so the button goes.
    assert _callbacks(telegram["edits"][-1][3], "share_paid:") == []

    _tap(client, f"share_paid:{code}")
    assert telegram["answers"][-1] == "Your payment is already marked"


def test_i_have_paid_is_refused_to_whoever_it_cannot_be_for(client: TestClient, session: Session, telegram):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)

    _tap(client, f"share_paid:{code}")
    _tap(client, f"share_paid:{code}", telegram_id=OWNER, name="Leonid")
    _tap(client, f"share_seat:{code}:{guest.id}")
    _tap(client, f"share_paid:{code}")

    assert telegram["alerts"] == [
        "Take your seat first — with a button above or in the app",
        "This is your bill — there’s no payment for you to mark",
        "Nothing is on your seat yet",
    ]


def _counted(product_events, *names: str) -> list[tuple[str, str, dict]]:
    return [(event, distinct_id, properties) for event, distinct_id, properties in product_events if event in names]


def test_a_seat_and_a_payment_under_the_post_are_counted_for_whoever_tapped(
    client: TestClient, session: Session, telegram, product_events
):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)
    _tap(client, f"share_seat:{code}:{guest.id}")
    _give_everything_to(client, session, bill, guest.id)
    _tap(client, f"share_paid:{code}")
    # Already marked: nothing more happened.
    _tap(client, f"share_paid:{code}")

    dana = str(_seat_of(session, 99).user_id)
    assert _counted(product_events, "participant_joined", "payment_marked") == [
        ("participant_joined", dana, {"surface": "bot", "via": "post", "channel": "prepared", "bill_id": bill["id"]}),
        ("payment_marked", dana, {
            "surface": "bot", "bill_id": bill["id"], "paid": True, "by": "self", "channel": "prepared", "from": "post",
        }),
    ]


def test_someone_new_who_taps_under_a_post_is_kept_as_come_from_it(
    client: TestClient, session: Session, telegram, product_events
):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)
    _tap(client, f"share_seat:{code}:{guest.id}")
    _tap(client, f"share_paid:{code}")

    dana = str(_seat_of(session, 99).user_id)
    assert [sent for sent in _counted(product_events, "$set_once") if sent[1] == dana] == [
        ("$set_once", dana, {"first_start": "post"}),
    ]


def test_a_refused_tap_under_the_post_is_counted_with_why(client: TestClient, session: Session, telegram, product_events):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)
    _tap(client, f"share_paid:{code}")
    _tap(client, f"share_seat:{code}:{guest.id}", telegram_id=100, name="Eve")
    _tap(client, f"share_seat:{code}:{guest.id}")

    refused = [properties for event, _, properties in _counted(product_events, "post_action_refused")]
    assert refused == [
        {"surface": "bot", "bill_id": bill["id"], "action": "paid", "reason": "paid_seat_first"},
        {"surface": "bot", "bill_id": bill["id"], "action": "seat", "reason": "seat_gone"},
    ]


def test_a_closed_bill_takes_no_seats_and_no_payments(client: TestClient, session: Session, telegram):
    _, bill = _bill(client)
    _share(client, bill)
    code = _record(session).invite_code
    [guest] = _free_seats(session, bill)
    stored = session.get(Bill, bill["id"])
    stored.status = BillStatus.CLOSED
    session.add(stored)
    session.commit()

    _tap(client, f"share_seat:{code}:{guest.id}")
    _tap(client, f"share_paid:{code}")
    _tap(client, f"share_seat:{code}:not-a-seat")

    assert telegram["alerts"] == ["Bill closed", "Bill closed", "This bill is no longer available"]
    assert _seat_of(session, 99) is None


def test_i_have_paid_in_a_personal_invite_sits_its_reader_on_that_seat(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)
    [guest] = _free_seats(session, bill)
    _give_everything_to(client, session, bill, guest.id)
    SharedBillService(session).prepare(session.get(Bill, bill["id"]), session.get(User, owner["id"]), "en", seat=guest)
    record = _record(session)
    # The seat is known already, so the post offers none to take.
    assert _callbacks(telegram["prepared"][0][1]["reply_markup"], "share_seat:") == []

    _tap(client, f"share_paid:{record.invite_code}")

    seat = _seat_of(session, 99)
    assert (seat.id, seat.is_paid) == (guest.id, True)
    assert telegram["answers"] == ["Marked: you paid 24 000 uzs"]


def test_i_have_paid_in_a_personal_invite_counts_the_seat_taken_and_the_payment(
    client: TestClient, session: Session, telegram, product_events
):
    owner, bill = _bill(client)
    [guest] = _free_seats(session, bill)
    _give_everything_to(client, session, bill, guest.id)
    SharedBillService(session).prepare(session.get(Bill, bill["id"]), session.get(User, owner["id"]), "en", seat=guest)

    _tap(client, f"share_paid:{_record(session).invite_code}")

    counted = _counted(product_events, "participant_joined", "payment_marked")
    assert [(event, properties["channel"]) for event, _, properties in counted] == [
        ("participant_joined", "seat"),
        ("payment_marked", "seat"),
    ]


def test_a_personal_invite_to_a_seat_with_nothing_on_it_just_sits_its_reader(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)
    [guest] = _free_seats(session, bill)
    SharedBillService(session).prepare(session.get(Bill, bill["id"]), session.get(User, owner["id"]), "en", seat=guest)

    _tap(client, f"share_paid:{_record(session).invite_code}")

    assert telegram["answers"] == ["Guest 1 is your seat now. Nothing to pay yet"]
    assert _seat_of(session, 99).is_paid is False


def test_a_post_the_bot_sent_is_redrawn_where_it_was_tapped(client: TestClient, session: Session, telegram):
    owner, bill = _bill(client)
    [guest] = _free_seats(session, bill)
    _give_everything_to(client, session, bill, guest.id)
    code = SharedBillService(session).invites.create(bill["id"], owner["id"], "bot").code
    _tap(client, f"share_seat:{code}:{guest.id}", inline_id=None, chat={"chat": {"id": 99}, "message_id": 5})

    _tap(client, f"share_paid:{code}", inline_id=None, chat={"chat": {"id": 99}, "message_id": 5})

    chat_id, message_id, text, _, markup = telegram["chat_edits"][-1]
    assert (chat_id, message_id) == (99, 5)
    assert "<b>Dana</b> ✅" in text
    assert _callbacks(markup, "share_paid:") == []
    assert telegram["edits"] == []
