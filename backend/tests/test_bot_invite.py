"""Sharing a bill from the chat.

The invite button asks the bot to post the invite where the user can forward
it on — the same post the Mini App shares, written by the same service.
"""
import pytest
from sqlmodel import Session, select

import app.services.bot_flow_service as flow
from app.models import Bill, Invite, InviteChannel, User
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.schemas.bill_schemas import BillCreate
from app.services.bill_core_service import BillCoreService
from tests.bot_chat_world import CHAT_ID
from tests.telegram_world import next_update_id


@pytest.fixture
def owner(session: Session) -> User:
    user = User(telegram_id=CHAT_ID, name="Lea", settings={"language": "ru", "onboarding_completed": True})
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def bill(session: Session, owner: User):
    return BillCoreService(BillRepository(session), UserRepository(session)).create_bill(
        BillCreate(owner_id=owner.id, total_sum=0, title="Ужин", include_owner=True)
    )


def test_the_panel_says_what_to_do_and_the_invite_goes_under_it(bot_chat, session: Session, owner, monkeypatch):
    monkeypatch.setattr(flow.queue_manager, "submit", lambda task_id: None)
    bot_chat.say("/new")
    bot_chat.say("3")
    bot_chat.tap("pay:new")
    bot_chat.say("8600123412341234")
    bot_chat.say(photo=[{"file_id": "receipt"}])
    bill = session.exec(select(Bill)).one()

    bot_chat.tap(f"invite:{bill.public_token}")

    panel, post = bot_chat.visible()
    assert "Перешлите" in panel.text
    assert post.text.startswith("👥 <b>Участники</b>\n\n")
    # A forwarded copy is not the bot's to edit, so it has nothing to refresh.
    assert post.callbacks() == []
    # The button carries a minted invite, so a forward that lands somewhere
    # unexpected is still credited to the person who posted it.
    invite = session.exec(select(Invite).where(Invite.bill_id == bill.id)).one()
    assert invite.channel == InviteChannel.BOT
    assert invite.inviter_user_id == owner.id
    assert post.buttons()[0]["url"].endswith(f"startapp=inv_{invite.code}")


def test_an_invite_asked_for_under_a_message_of_its_own_gets_its_own_hint(bot_chat, bill, owner):
    report = bot_chat.send_message(CHAT_ID, "Чек распознан")["message_id"]

    bot_chat.tap(f"invite:{bill.public_token}", on=report)

    report, hint, post = bot_chat.visible()
    assert "Перешлите" in hint.text
    assert post.text.startswith("👥 <b>Участники</b>")


def test_an_invite_posted_for_forwarding_is_counted_as_shared(bot_chat, bill, owner, product_events):
    bot_chat.tap(f"invite:{bill.public_token}", on=1)

    assert product_events == [(
        "share_invite",
        str(owner.id),
        {"surface": "bot", "method": "message", "channel": "bot", "bill_id": bill.id},
    )]


def test_someone_elses_bill_is_not_posted(bot_chat, session: Session, bill):
    stranger = CHAT_ID + 1
    session.add(User(telegram_id=stranger, name="Stranger"))
    session.commit()
    bot_chat.client.post("/telegram/webhook", json={
        "update_id": next_update_id(),
        "callback_query": {
            "id": "cb", "data": f"invite:{bill.public_token}",
            "from": {"id": stranger, "language_code": "ru", "first_name": "Stranger"},
            "message": {"message_id": 1, "chat": {"id": stranger, "type": "private"}},
        },
    })

    assert [m.text for m in bot_chat.visible(stranger)] == ["Счёт не найден."]
