from datetime import datetime

from sqlmodel import Session, select
from app.models import PaymentMethod


class PaymentMethodRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_user(self, user_id: int) -> list[PaymentMethod]:
        """Cards the user can still pick. Hidden ones stay readable by id, so
        bills that reference them keep showing their number."""
        statement = (
            select(PaymentMethod)
            .where(PaymentMethod.user_id == user_id, PaymentMethod.deleted_at.is_(None))
            .order_by(PaymentMethod.created_at)
        )
        return list(self.session.exec(statement).all())

    def get_by_id(self, method_id: int) -> PaymentMethod | None:
        return self.session.get(PaymentMethod, method_id)

    def create(self, method: PaymentMethod) -> PaymentMethod:
        self.session.add(method)
        self.session.commit()
        self.session.refresh(method)
        return method

    def hide(self, method: PaymentMethod) -> None:
        method.deleted_at = datetime.utcnow()
        self.session.add(method)
        self.session.commit()
