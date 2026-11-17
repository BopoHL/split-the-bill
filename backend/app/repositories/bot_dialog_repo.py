from sqlmodel import Session, select

from app.models import BotDialog


class BotDialogRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_chat(self, chat_id: int) -> BotDialog | None:
        statement = select(BotDialog).where(BotDialog.chat_id == chat_id)
        return self.session.exec(statement).first()

    def save(self, dialog: BotDialog) -> BotDialog:
        self.session.add(dialog)
        self.session.commit()
        self.session.refresh(dialog)
        return dialog

    def clear(self, chat_id: int) -> None:
        """Drop the chat's dialog once a flow finishes or is abandoned. The row
        carries no history worth keeping — the bill it produced does."""
        dialog = self.get_by_chat(chat_id)
        if dialog is None:
            return
        self.session.delete(dialog)
        self.session.commit()
