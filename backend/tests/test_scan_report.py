"""What a chat gets back once its receipt has been read."""
import os

import pytest
from sqlmodel import Session

import app.services.scan_report as report
from app.models import BillItem, ReceiptTask, User
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.schemas.bill_schemas import BillCreate
from app.services.bill_core_service import BillCoreService
from app.utils.bill_card import render_bill_card

CHAT_ID = 42


@pytest.fixture
def owner(session: Session) -> User:
    user = User(telegram_id=CHAT_ID, name="Lea", settings={"language": "ru"})
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def bill(session: Session, owner: User):
    created = BillCoreService(BillRepository(session), UserRepository(session)).create_bill(
        BillCreate(owner_id=owner.id, total_sum=0, title="Ужин", expected_people=2, include_owner=True)
    )
    stored = BillRepository(session).get_by_id(created.id)
    session.add(BillItem(bill_id=stored.id, name="Лагман", price=6000000, count=2, item_sum=12000000))
    stored.total_sum = 12000000
    session.add(stored)
    session.commit()
    session.refresh(stored)
    return stored


@pytest.fixture
def sent(monkeypatch):
    calls = {"photos": [], "messages": []}
    monkeypatch.setattr(
        report, "send_photo",
        lambda chat_id, photo=None, caption=None, reply_markup=None, photo_path=None, **k:
            calls["photos"].append({"chat_id": chat_id, "path": photo_path,
                                    "caption": caption, "markup": reply_markup}),
    )
    monkeypatch.setattr(
        report, "send_message",
        lambda chat_id, text, reply_markup=None, **k:
            calls["messages"].append({"chat_id": chat_id, "text": text, "markup": reply_markup}),
    )
    monkeypatch.setenv("TG_BOT_USERNAME", "SplitTheBillsBot")
    return calls


def _task(session: Session, bill, filename=None, notify=CHAT_ID) -> ReceiptTask:
    task = ReceiptTask(bill_id=bill.id, filename=filename, notify_chat_id=notify)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def test_a_scan_from_the_app_is_not_reported(session: Session, bill, sent):
    report.report_scan(session, _task(session, bill, notify=None), bill)

    assert sent["photos"] == [] and sent["messages"] == []


def test_the_receipt_comes_back_as_a_photo_with_the_bill_on_it(
    session: Session, bill, sent, monkeypatch, tmp_path
):
    image = tmp_path / "receipt.jpg"
    image.write_bytes(b"jpeg")
    monkeypatch.setattr(report, "STORAGE_DIR", str(tmp_path))

    report.report_scan(session, _task(session, bill, filename="receipt.jpg"), bill)

    photo = sent["photos"][0]
    assert photo["chat_id"] == CHAT_ID
    assert photo["path"] == str(image)
    assert "Лагман" in photo["caption"]
    assert "Итого" in photo["caption"]
    labels = [row[0]["text"] for row in photo["markup"]["inline_keyboard"]]
    assert labels == ["👥 Пригласить участников", "📱 Открыть счёт в приложении"]


def test_a_qr_import_has_no_photo_and_still_reports(session: Session, bill, sent):
    report.report_scan(session, _task(session, bill), bill)

    assert sent["photos"] == []
    assert "Лагман" in sent["messages"][0]["text"]


def test_a_telegram_failure_does_not_escape_the_worker(session: Session, bill, sent, monkeypatch):
    monkeypatch.setattr(
        report, "send_message",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Telegram error: blocked")),
    )

    report.report_scan(session, _task(session, bill), bill)


def test_the_card_lists_people_and_trims_a_long_receipt(session: Session, bill):
    detail = BillCoreService(
        BillRepository(session), UserRepository(session)
    ).get_bill_details(bill.id, requester_id=bill.owner_id)
    detail.items = detail.items * 12

    card = render_bill_card(detail, "ru")

    assert card.count("• ") == 10
    assert "…и ещё 2" in card
    assert "Участники" in card
