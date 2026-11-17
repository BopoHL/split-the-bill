from sqlmodel import Session, select

from app.models import Invite


class InviteRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, invite: Invite) -> Invite:
        self.session.add(invite)
        self.session.commit()
        self.session.refresh(invite)
        return invite

    def get_by_code(self, code: str) -> Invite | None:
        return self.session.exec(select(Invite).where(Invite.code == code)).first()
