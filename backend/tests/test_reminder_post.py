"""The reminder post: one person's dishes, share and card, with «I've paid».

It goes out from the bot, or — for someone who blocked the bot — prepared for a
sender account to send as the bot's post. Either way its buttons act and it is
redrawn from the bill as it is now.
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.services.bot_panel as panel
import app.services.shared_bill_service as shared
from app.models import BillItem, BillUser, Invite, InviteChannel, SharedBillMessage, User
from app.services.shared_bill_service import SharedBillService
from app.utils.currency import format_amount
from tests.telegram_world import next_update_id

OWNER = 7001
DEBTOR = 99


@pytest.fixture
def telegram(monkeypatch):
    calls = {"sent": [], "prepared": [], "edits": [], "chat_edits": [], "answers": [], "alerts": [], "opened": []}

    class _NoFaces:
        @staticmethod
        def for_people(telegram_ids):
            return {}

    def answer(callback_id, text=None, show_alert=False, url=None):
        (calls["alerts"] if show_alert else calls["answers"]).append(text)
        calls["opened"].append(url)

    monkeypatch.setattr(shared, "profile_photos", _NoFaces())
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://split-the-bill.uz")
    monkeypatch.delenv("TG_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(shared, "send_message", lambda chat_id, text, markup, **kw: calls["sent"].append((chat_id, text, markup, kw)) or {"message_id": 5})
    monkeypatch.setattr(shared, "save_prepared_text_message", lambda uid, **message: calls["prepared"].append((uid, message)) or "PREPARED")
    monkeypatch.setattr(shared, "edit_inline_message_text", lambda *args: calls["edits"].append(args))
    monkeypatch.setattr(shared, "edit_chat_message_text", lambda *args: calls["chat_edits"].append(args))
    monkeypatch.setattr(shared, "answer_callback_query", answer)
    return calls


def _tap(client: TestClient, data: str, telegram_id: int = DEBTOR, *, inline_id: str | None = None, chat: dict | None = None):
    callback = {"id": "cb", "data": data, "chat_instance": "1", "from": {"id": telegram_id, "language_code": "en", "first_name": "Dana"}}
    if inline_id:
        callback["inline_message_id"] = inline_id
    if chat:
        callback["message"] = chat
    client.post("/telegram/webhook", json={"update_id": next_update_id(), "callback_query": callback})


def _bill_with_debtor(client: TestClient, session: Session, telegram, language: str = "ru"):
    """Two seats; the guest one taken by the debtor, who had both samsas."""
    owner = client.post("/users/", json={"telegram_id": OWNER, "username": "leo", "name": "Leonid"}).json()
    bill = client.post("/bills/", json={
        "owner_id": owner["id"], "total_sum": 0, "title": "Ужин", "include_owner": True,
        "expected_people": 2, "payment_details": "8600 1234 5678 9012",
    }).json()
    client.post(f"/bills/{bill['id']}/items", json={"name": "Самса", "price": 12000, "count": 2})
    client.post(f"/bills/{bill['id']}/prepare-share", json={})
    code = session.exec(select(SharedBillMessage)).one().invite_code
    guest = session.exec(select(BillUser).where(BillUser.bill_id == bill["id"], BillUser.user_id.is_(None))).one()
    _tap(client, f"share_seat:{code}:{guest.id}", inline_id="SHARED")

    debtor = session.exec(select(User).where(User.telegram_id == DEBTOR)).one()
    debtor.settings = {"language": language}
    session.add(debtor)
    session.commit()
    for item in session.exec(select(BillItem).where(BillItem.bill_id == bill["id"])).all():
        client.post(f"/bills/{bill['id']}/items/{item.id}/assign", json={"participant_id": guest.id, "is_assigned": True})

    session.expire_all()
    invite = Invite(bill_id=bill["id"], inviter_user_id=owner["id"], seat_participant_id=guest.id, channel=InviteChannel.REMINDER)
    session.add(invite)
    session.commit()
    for calls in telegram.values():
        calls.clear()
    return bill, guest, debtor, invite.code


def _buttons(markup: dict) -> list[str]:
    return [button.get("callback_data") or button.get("url") or button["text"] for row in markup["inline_keyboard"] for button in row]


def test_the_bot_reminds_someone_of_their_dishes_share_and_card(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    bill_row = SharedBillService(session).bills.get_by_id(bill["id"])

    SharedBillService(session).remind_by_bot(bill_row, code, debtor)

    chat_id, text, markup, extra = telegram["sent"][0]
    assert chat_id == DEBTOR
    assert text.startswith("🔔 <b>Напоминание об оплате</b>\nВы участник счёта «Ужин».")
    assert "🧾 <b>Ваши позиции</b>\n<blockquote>Самса ×2 — 24 000 сум</blockquote>" in text
    assert "💰 <b>Ваша доля:</b> <code>24000</code> сум" in text
    assert "💳 <b>Реквизиты</b>\n8600123456789012" in text
    assert text.endswith("Пожалуйста, оплатите свою долю и подтвердите оплату кнопкой ниже.")
    assert _buttons(markup) == [
        "💳 Карта", f"share_paid:{code}",
        f"https://t.me/SplitTheBillsBot/app?startapp=bill_{bill['public_token']}", f"share_refresh:{code}",
    ]
    assert extra["link_preview_options"]["url"].startswith(
        f"https://split-the-bill.uz/api/bills/public/{bill['public_token']}/card.png?lang=ru"
    )


def test_a_sender_account_gets_the_same_post_prepared_and_tracked(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram, language="en")
    service = SharedBillService(session)

    prepared = service.prepare_reminder(service.bills.get_by_id(bill["id"]), code, debtor, sender_telegram_id=555)

    assert prepared.id == "PREPARED"
    assert prepared.preview_url.startswith(f"https://split-the-bill.uz/api/bills/public/{bill['public_token']}/card.png")

    uid, message = telegram["prepared"][0]
    assert uid == 555
    assert message["result_id"] == f"share:{code}"
    assert message["private_chats_only"] is True
    assert message["text_html"].startswith("🔔 <b>Payment reminder</b>\nYou are on the bill «Ужин».")
    assert message["description"] == f"Your share: {format_amount(2_400_000, 'uzs', 'en')}"
    record = session.exec(select(SharedBillMessage).where(SharedBillMessage.invite_code == code)).one()
    assert (record.language, record.inline_message_id) == ("en", None)


def test_a_reminder_is_drawn_in_the_owners_theme_whoever_reads_it(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    owner = session.exec(select(User).where(User.telegram_id == OWNER)).one()
    owner.settings = {**(owner.settings or {}), "theme": "dark"}
    debtor.settings = {**debtor.settings, "theme": "light"}
    session.add_all([owner, debtor])
    session.commit()
    service = SharedBillService(session)
    bill_row = service.bills.get_by_id(bill["id"])

    service.remind_by_bot(bill_row, code, debtor)
    prepared = service.prepare_reminder(bill_row, code, debtor, sender_telegram_id=555)
    _tap(client, f"share_refresh:{code}", chat={"message_id": 5, "chat": {"id": DEBTOR}})

    assert "&theme=dark&" in telegram["sent"][-1][3]["link_preview_options"]["url"]
    assert "&theme=dark&" in prepared.preview_url
    assert session.exec(select(SharedBillMessage).where(SharedBillMessage.invite_code == code)).one().theme == "dark"
    assert "&theme=dark&" in telegram["chat_edits"][-1][3]["url"]


def test_i_paid_under_a_reminder_marks_the_payment_and_says_so_in_the_post(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    service = SharedBillService(session)
    service.prepare_reminder(service.bills.get_by_id(bill["id"]), code, debtor, sender_telegram_id=555)

    _tap(client, f"share_paid:{code}", inline_id="REMINDER-1")

    session.expire_all()
    assert session.get(BillUser, guest.id).is_paid is True
    inline_id, text, preview, markup = telegram["edits"][-1]
    assert inline_id == "REMINDER-1"
    assert "✅ Оплата отмечена — спасибо!" in text
    assert "Реквизиты" not in text
    assert _buttons(markup) == [
        f"https://t.me/SplitTheBillsBot/app?startapp=bill_{bill['public_token']}", f"share_refresh:{code}",
    ]
    # The bot cannot write to them — the reminder came from an account — so
    # the tap opens its chat, where Start lets it.
    assert telegram["opened"] == [f"https://t.me/SplitTheBillsBot?start=post_{code}"]


def test_refresh_under_a_reminder_from_the_bot_writes_it_again(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)

    _tap(client, f"share_refresh:{code}", chat={"message_id": 5, "chat": {"id": DEBTOR}})

    chat_id, message_id, text, preview, markup = telegram["chat_edits"][-1]
    assert (chat_id, message_id) == (DEBTOR, 5)
    assert "Ваша доля" in text
    assert telegram["answers"][-1] == "Обновлено"


def test_a_refresh_under_a_reminder_is_counted_for_whoever_pressed_it(
    client: TestClient, session: Session, telegram, product_events
):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)

    _tap(client, f"share_refresh:{code}", chat={"message_id": 5, "chat": {"id": DEBTOR}})

    assert [
        (distinct_id, properties) for event, distinct_id, properties in product_events if event == "post_refreshed"
    ] == [(str(debtor.id), {"surface": "bot", "bill_id": bill["id"], "outcome": "edited"})]


def test_refresh_under_a_post_that_is_not_a_reminder_is_not_answered_with_one(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    shared_code = session.exec(select(Invite).where(Invite.channel != InviteChannel.REMINDER)).first().code

    _tap(client, f"share_refresh:{shared_code}", chat={"message_id": 5, "chat": {"id": DEBTOR}})

    assert telegram["chat_edits"] == []
    assert telegram["answers"][-1] == "Этот счёт больше недоступен"


def test_a_long_list_of_dishes_is_cut_with_how_many_more(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    for n in range(120):
        response = client.post(f"/bills/{bill['id']}/items", json={"name": f"Очень длинное название блюда номер {n}", "price": 1000, "count": 1})
        client.post(f"/bills/{bill['id']}/items/{response.json()['id']}/assign", json={"participant_id": guest.id, "is_assigned": True})
    session.expire_all()

    SharedBillService(session).remind_by_bot(SharedBillService(session).bills.get_by_id(bill["id"]), code, debtor)

    text = telegram["sent"][-1][1]
    assert "+ ещё" in text
    assert "Ваша доля" in text and text.endswith("кнопкой ниже.")


def test_someone_the_bot_already_writes_to_is_not_sent_to_its_chat(client: TestClient, session: Session, telegram):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    debtor.settings = {**debtor.settings, "bot_blocked": False}
    session.add(debtor)
    session.commit()

    _tap(client, f"share_paid:{code}", inline_id="REMINDER-1")

    assert telegram["opened"] == [None]


def _start_from_post(client: TestClient, code: str, telegram_id: int = DEBTOR) -> None:
    client.post("/telegram/webhook", json={"update_id": next_update_id(), "message": {
        "message_id": 1, "chat": {"id": telegram_id, "type": "private"}, "text": f"/start post_{code}",
        "from": {"id": telegram_id, "first_name": "Dana", "language_code": "en"},
    }})


def test_start_from_the_post_says_where_they_stand_lets_the_bot_write_and_nothing_more(
    client: TestClient, session: Session, telegram, monkeypatch
):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    _tap(client, f"share_paid:{code}", inline_id="REMINDER-1")
    menu = []
    monkeypatch.setattr(panel, "send_message", lambda chat_id, text, reply_markup=None, **k: menu.append(text) or {"message_id": 1})
    monkeypatch.setattr(panel, "delete_message", lambda chat_id, message_id: None)

    _start_from_post(client, code)

    chat_id, text, markup, _ = telegram["sent"][-1]
    assert (chat_id, text) == (DEBTOR, "✅ Оплата по счёту «Ужин» отмечена.")
    assert _buttons(markup) == [f"https://t.me/SplitTheBillsBot/app?startapp=bill_{bill['public_token']}"]
    session.expire_all()
    assert session.get(User, debtor.id).settings["bot_blocked"] is False
    # What they came for is said; the bot's own greeting would bury it.
    assert menu == []


def test_i_have_paid_in_a_reminder_and_the_start_it_leads_to_are_counted(
    client: TestClient, session: Session, telegram, monkeypatch, product_events
):
    bill, guest, debtor, code = _bill_with_debtor(client, session, telegram)
    monkeypatch.setattr(panel, "send_message", lambda chat_id, text, reply_markup=None, **k: {"message_id": 1})
    monkeypatch.setattr(panel, "delete_message", lambda chat_id, message_id: None)
    product_events.clear()

    _tap(client, f"share_paid:{code}", inline_id="REMINDER-1")
    _start_from_post(client, code)

    assert [(event, properties) for event, distinct_id, properties in product_events if distinct_id == str(debtor.id)] == [
        ("payment_marked", {
            "surface": "bot", "bill_id": bill["id"], "paid": True, "by": "self", "channel": "reminder", "from": "post",
        }),
        ("bot_command", {"surface": "bot", "command": "start", "start": "post"}),
    ]


def test_start_from_a_post_of_a_bill_they_are_not_on_starts_as_ever(
    client: TestClient, session: Session, telegram, monkeypatch, product_events
):
    _, _, _, code = _bill_with_debtor(client, session, telegram)
    menu = []
    monkeypatch.setattr(panel, "send_message", lambda chat_id, text, reply_markup=None, **k: menu.append(text) or {"message_id": 1})
    monkeypatch.setattr(panel, "delete_message", lambda chat_id, message_id: None)
    product_events.clear()

    _start_from_post(client, code, telegram_id=555)

    assert telegram["sent"] == []
    assert menu
    # Counted as a start from a post, without the post's invite code.
    assert [properties for event, _, properties in product_events if event == "bot_command"] == [
        {"surface": "bot", "command": "start", "start": "post"},
    ]
