from app.models import BotDialog, BotDialogStep
from app.repositories.bot_dialog_repo import BotDialogRepository


def test_dialog_survives_as_a_row_and_is_found_by_chat(session):
    repo = BotDialogRepository(session)

    repo.save(
        BotDialog(
            chat_id=4242,
            step=BotDialogStep.BILL_HEADCOUNT,
            draft={"currency": "uzs"},
        )
    )

    stored = repo.get_by_chat(4242)
    assert stored is not None
    assert stored.step == BotDialogStep.BILL_HEADCOUNT
    assert stored.draft == {"currency": "uzs"}


def test_one_dialog_per_chat_is_advanced_in_place(session):
    repo = BotDialogRepository(session)
    dialog = repo.save(BotDialog(chat_id=7, step=BotDialogStep.BILL_HEADCOUNT))

    dialog.step = BotDialogStep.BILL_PAYMENT
    dialog.draft = {"headcount": 3}
    repo.save(dialog)

    stored = repo.get_by_chat(7)
    assert stored.id == dialog.id
    assert stored.step == BotDialogStep.BILL_PAYMENT
    assert stored.draft == {"headcount": 3}


def test_clearing_a_finished_flow_leaves_nothing_behind(session):
    repo = BotDialogRepository(session)
    repo.save(BotDialog(chat_id=9, step=BotDialogStep.BILL_RECEIPT))

    repo.clear(9)

    assert repo.get_by_chat(9) is None


def test_clearing_an_unknown_chat_is_a_no_op(session):
    BotDialogRepository(session).clear(123456)
