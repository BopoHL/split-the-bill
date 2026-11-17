from sqlmodel import Session, select

from app.models import BotPanel


class BotPanelRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_chat(self, chat_id: int) -> BotPanel | None:
        return self.session.exec(select(BotPanel).where(BotPanel.chat_id == chat_id)).first()

    def save(self, panel: BotPanel) -> BotPanel:
        self.session.add(panel)
        self.session.commit()
        self.session.refresh(panel)
        return panel

    def delete(self, panel: BotPanel) -> None:
        self.session.delete(panel)
        self.session.commit()
