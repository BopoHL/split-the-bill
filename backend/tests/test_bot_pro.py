"""Pro and reminders in the bot's chat: the offer with a payment per plan, and
the owner reminding the people who owe from a bill's card. Telegram is stubbed."""
import threading
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import app.services.bot_pro as bot_pro
from app.models import AppSetting, Bill, BillUser, ManualReminder, ProGrant, ProSource, User
from app.services.app_settings import PRO_WAS_PRICE_KEYS
from app.services.pro import ProService, read_payload

OWNER = 42


@pytest.fixture
def telegram(bot_chat, monkeypatch):
    def invoice_link(invoice):
        plan, user_id = read_payload(invoice["payload"])
        return f"https://t.me/$invoice-{plan.value}-{user_id}"

    monkeypatch.setattr(bot_pro, "create_invoice_link", invoice_link)
    return bot_chat


@pytest.fixture
def owner(session: Session) -> User:
    user = User(telegram_id=OWNER, name="Leo", settings={"language": "ru", "onboarding_completed": True})
    session.add(user)
    session.commit()
    return user


def _buttons(message) -> list[tuple[str, str]]:
    return [(button["text"], button.get("callback_data") or button.get("url")) for button in message.buttons()]


def _pro(session: Session, user: User, source: ProSource = ProSource.PROMO) -> None:
    now = datetime.utcnow()
    session.add(ProGrant(user_id=user.id, source=source.value, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=20)))
    session.commit()


def _bill_owed_by_two(session: Session, owner: User) -> Bill:
    bill = Bill(owner_id=owner.id, title="Ужин", currency="uzs", total_sum=9_000_000)
    session.add(bill)
    session.commit()
    ann = User(telegram_id=501, name="Ann")
    bob = User(telegram_id=502, username="bob")
    session.add_all([ann, bob])
    session.commit()
    session.add_all([
        BillUser(bill_id=bill.id, user_id=owner.id, seat_index=0, allocated_amount=3_000_000),
        BillUser(bill_id=bill.id, user_id=ann.id, seat_index=1, allocated_amount=2_500_000),
        BillUser(bill_id=bill.id, user_id=bob.id, seat_index=2, allocated_amount=2_000_000),
        BillUser(bill_id=bill.id, user_id=None, seat_index=3, allocated_amount=1_500_000),
    ])
    session.commit()
    return bill


def test_pro_offers_each_plan_with_its_payment(client: TestClient, session: Session, owner, telegram):
    session.add(AppSetting(key=PRO_WAS_PRICE_KEYS["year"], value="1200"))
    session.commit()

    telegram.say("/pro")

    offer = telegram.last()
    assert offer.text.startswith("⭐ <b>Split·Bill Pro</b>")
    assert "• напоминания должникам — всем сразу или по одному" in offer.text
    assert "<b>Сроки</b>\nМесяц — 100 ⭐ · продлевается сам\n6 месяцев — 500 ⭐ · ≈83 ⭐ в месяц\n" in offer.text
    assert "Год — <s>1200</s> 900 ⭐ · ≈75 ⭐ в месяц" in offer.text
    assert _buttons(offer) == [
        ("Месяц · 100 ⭐", f"https://t.me/$invoice-month-{owner.id}"),
        ("6 месяцев · 500 ⭐", f"https://t.me/$invoice-half_year-{owner.id}"),
        ("Год · 900 ⭐", f"https://t.me/$invoice-year-{owner.id}"),
        ("📱 Pro в приложении", "https://t.me/SplitTheBillsBot/app?startapp=pro"),
        ("← Меню", "menu:main"),
    ]


def test_the_bot_sells_at_the_running_offer(client: TestClient, session: Session, owner, telegram):
    ProService(session).start_offer(owner.id, datetime.utcnow())

    telegram.say("/pro")

    offer = telegram.last()
    assert "Месяц — 100 ⭐ · продлевается сам" in offer.text
    assert "Год — <s>900</s> 540 ⭐ · ≈45 ⭐ в месяц" in offer.text
    assert ("Год · 540 ⭐", f"https://t.me/$invoice-year-{owner.id}") in _buttons(offer)


def test_the_menu_leads_to_the_same_offer(client: TestClient, session: Session, owner, telegram):
    telegram.say("/menu")
    assert ("⭐ Pro", "pro:offer") in _buttons(telegram.last())

    telegram.tap("pro:offer")

    assert telegram.last().text.startswith("⭐ <b>Split·Bill Pro</b>")


def test_someone_on_a_subscription_is_told_until_when_and_not_sold_a_second_one(
    client: TestClient, session: Session, owner, telegram
):
    _pro(session, owner, ProSource.SUBSCRIPTION)

    telegram.say("/pro")

    offer = telegram.last()
    assert offer.text.startswith("⭐ <b>Pro включён до ")
    assert "подписка продлевается сама" in offer.text
    assert "Месяц" not in offer.text
    assert [text for text, _ in _buttons(offer)] == ["6 месяцев · 500 ⭐", "Год · 900 ⭐", "📱 Pro в приложении", "← Меню"]


def test_a_plan_telegram_would_not_bill_is_left_out(client: TestClient, session: Session, owner, telegram, monkeypatch):
    def refused(invoice):
        if read_payload(invoice["payload"])[0].value == "month":
            raise RuntimeError("Telegram error: SUBSCRIPTION_PERIOD_INVALID")
        return "https://t.me/$invoice"

    monkeypatch.setattr(bot_pro, "create_invoice_link", refused)

    telegram.say("/pro")

    assert [text for text, _ in _buttons(telegram.last())][:2] == ["6 месяцев · 500 ⭐", "Год · 900 ⭐"]


def test_the_plans_links_are_asked_for_side_by_side(client: TestClient, session: Session, owner, telegram, monkeypatch):
    # Each link waits for the other two: asked one after another, none would come.
    together = threading.Barrier(3, timeout=5)

    def invoice_link(invoice):
        together.wait()
        return f"https://t.me/$invoice-{read_payload(invoice['payload'])[0].value}"

    monkeypatch.setattr(bot_pro, "create_invoice_link", invoice_link)

    telegram.say("/pro")

    links = [url for _, url in _buttons(telegram.last())][:3]
    assert links == ["https://t.me/$invoice-month", "https://t.me/$invoice-half_year", "https://t.me/$invoice-year"]


def test_the_owners_card_without_pro_says_who_owes_and_offers_pro_to_remind_them(
    client: TestClient, session: Session, owner, telegram
):
    bill = _bill_owed_by_two(session, owner)

    telegram.tap(f"card:{bill.public_token}")

    card = telegram.last()
    assert "<b>Ещё не оплатили</b>\n⏳ Ann — 25 000 сум\n⏳ @bob — 20 000 сум\n⏳ Гость 3 — 15 000 сум" in card.text
    assert _buttons(card)[0] == ("🔒 Напомнить всем — Pro", "pro:reminders")

    telegram.tap("pro:reminders")

    assert telegram.last().text.startswith("🔔 Напоминания должникам — в Pro.\n\n⭐ <b>Split·Bill Pro</b>")
    # The card turns into the offer where it stands.
    assert len(telegram.visible()) == 1
    assert session.exec(select(ManualReminder)).all() == []


def test_with_pro_the_owner_reminds_everyone_or_one_and_hears_how_it_went(
    client: TestClient, session: Session, owner, telegram
):
    _pro(session, owner)
    bill = _bill_owed_by_two(session, owner)
    ann, bob = session.exec(select(BillUser).where(BillUser.bill_id == bill.id, BillUser.seat_index.in_([1, 2])).order_by(BillUser.seat_index)).all()

    telegram.tap(f"card:{bill.public_token}")
    assert _buttons(telegram.last())[:3] == [
        ("🔔 Напомнить всем", f"remind:{bill.public_token}"),
        ("🔔 Ann", f"remind:{bill.public_token}:{ann.id}"),
        ("🔔 @bob", f"remind:{bill.public_token}:{bob.id}"),
    ]

    telegram.tap(f"remind:{bill.public_token}:{ann.id}")
    assert telegram.answers[-1] == ("Напоминание уходит: Ann", False)

    telegram.tap(f"remind:{bill.public_token}")
    assert telegram.answers[-1] == ("Напоминание уходит: @bob", False)

    telegram.tap(f"remind:{bill.public_token}")
    text, alert = telegram.answers[-1]
    assert text.startswith("Недавно уже напоминали. Следующее — после ") and alert
    assert sorted(reminder.participant_id for reminder in session.exec(select(ManualReminder)).all()) == [ann.id, bob.id]


def test_reminding_from_the_card_is_counted_as_the_app_counts_it(
    client: TestClient, session: Session, owner, telegram, product_events
):
    _pro(session, owner)
    bill = _bill_owed_by_two(session, owner)
    ann = session.exec(select(BillUser).where(BillUser.bill_id == bill.id, BillUser.seat_index == 1)).one()

    telegram.tap(f"remind:{bill.public_token}:{ann.id}")
    telegram.tap(f"remind:{bill.public_token}")
    telegram.tap(f"remind:{bill.public_token}")

    sent = [properties for event, _, properties in product_events if event == "reminders_sent"]
    common = {"surface": "bot", "bill_id": bill.id, "from": "bot"}
    assert sent == [
        {**common, "scope": "seat", "queued": 1},
        {**common, "scope": "bill", "queued": 1},
        # Nobody left to remind this soon: still counted, with nothing queued.
        {**common, "scope": "bill", "queued": 0},
    ]


def test_only_the_owner_sees_who_owes_and_may_remind(client: TestClient, session: Session, owner, telegram):
    stranger = User(telegram_id=777, settings={"language": "ru"})
    session.add(stranger)
    session.commit()
    bill = _bill_owed_by_two(session, stranger)
    session.add(BillUser(bill_id=bill.id, user_id=owner.id, seat_index=4, allocated_amount=1_000_000))
    session.commit()
    _pro(session, owner)

    telegram.tap(f"card:{bill.public_token}")
    assert "Ещё не оплатили" not in telegram.last().text
    assert [text for text, _ in _buttons(telegram.last())] == ["📱 Открыть счёт в приложении", "← К счетам"]

    telegram.tap(f"remind:{bill.public_token}")
    assert telegram.answers[-1] == ("Счёт не найден.", True)
    assert session.exec(select(ManualReminder)).all() == []
