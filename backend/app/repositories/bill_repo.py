from sqlmodel import Session, select, or_, func
from sqlalchemy import exists, select as sa_select
from sqlalchemy.orm import selectinload
from app.models import Bill, BillItem, BillUser

class BillRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, bill: Bill) -> Bill:
        self.session.add(bill)
        self.session.commit()
        self.session.refresh(bill)
        return bill

    def get_by_id(self, bill_id: int) -> Bill | None:
        return self.session.get(Bill, bill_id)

    def get_user_bills(self, user_id: int, offset: int = 0, limit: int = 10) -> list[tuple[Bill, int]]:
        from sqlmodel import and_
        
        # Subquery for participant count, correlated to the outer Bill
        count_stmt = (
            sa_select(func.count(BillUser.id))
            .where(BillUser.bill_id == Bill.id)
            .correlate(Bill)
            .scalar_subquery()
        )

        statement = (
            select(Bill, count_stmt.label("participants_count"))
            .where(
                or_(
                    Bill.owner_id == user_id,
                    exists().where(
                        and_(BillUser.bill_id == Bill.id, BillUser.user_id == user_id)
                    )
                )
            )
            .order_by(Bill.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        # Each row is (Bill, participants_count)
        return self.session.exec(statement).all()

    def add_item(self, item: BillItem) -> BillItem:
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def add_participant(self, participant: BillUser) -> BillUser:
        self.session.add(participant)
        self.session.commit()
        self.session.refresh(participant)
        return participant

    def get_items_by_bill_id(self, bill_id: int) -> list[BillItem]:
        statement = select(BillItem).where(BillItem.bill_id == bill_id)
        return self.session.exec(statement).all()

    def get_participants_by_bill_id(self, bill_id: int) -> list[BillUser]:
        statement = select(BillUser).where(BillUser.bill_id == bill_id).options(selectinload(BillUser.user))
        return self.session.exec(statement).all()

    def get_participant_by_id(self, participant_id: int) -> BillUser | None:
        return self.session.get(BillUser, participant_id)

    def get_item_by_id(self, item_id: int) -> BillItem | None:
        return self.session.get(BillItem, item_id)

    def delete_item(self, item: BillItem):
        self.session.delete(item)
        self.session.commit()

    def delete_participant(self, participant: BillUser):
        self.session.delete(participant)
        self.session.commit()

    def get_items_by_bill_id_and_participant(self, bill_id: int, user_id: int) -> list[BillItem]:
        statement = select(BillItem).where(BillItem.bill_id == bill_id, BillItem.assigned_to_user_id == user_id)
        return self.session.exec(statement).all()

    def get_participant_by_bill_and_user(self, bill_id: int, user_id: int) -> BillUser | None:
        statement = select(BillUser).where(BillUser.bill_id == bill_id, BillUser.user_id == user_id).options(selectinload(BillUser.user))
        return self.session.exec(statement).first()
