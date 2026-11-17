from datetime import datetime, timedelta

from sqlmodel import Session, and_, or_, select
from app.models import ReceiptTask, ReceiptTaskStatus
from typing import Optional, List

# Longer than any scan takes; past it, nobody is waiting for the result.
RESUME_WINDOW = timedelta(minutes=10)


class ReceiptRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_task(self, task: ReceiptTask) -> ReceiptTask:
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def get_task(self, task_id: int) -> Optional[ReceiptTask]:
        return self.session.get(ReceiptTask, task_id)

    def get_unfinished_tasks(self, now: datetime) -> List[ReceiptTask]:
        """Queued scans, and the ones a restart has just cut off mid-way.

        Only just: a scan left hanging by an older restart belongs to a bill its
        owner gave up on long ago, and reading it now would fill that bill and
        send the chat it came from a card for a dinner weeks past."""
        cut_off = now - RESUME_WINDOW
        statement = (
            select(ReceiptTask)
            .where(or_(
                ReceiptTask.status == ReceiptTaskStatus.PENDING,
                and_(
                    ReceiptTask.status.in_([ReceiptTaskStatus.PROCESSING, ReceiptTaskStatus.STRUCTURING]),
                    ReceiptTask.updated_at >= cut_off,
                ),
            ))
            .order_by(ReceiptTask.id)
        )
        return self.session.exec(statement).all()

    def list_tasks_by_bill(self, bill_id: int) -> List[ReceiptTask]:
        """Every scan attached to the bill, oldest first.

        A bill can hold several receipts — dinner plus the coffee afterwards —
        and each keeps its own items, so callers work with the whole set rather
        than guessing which one is "current".
        """
        statement = (
            select(ReceiptTask)
            .where(ReceiptTask.bill_id == bill_id)
            .order_by(ReceiptTask.id)
        )
        return self.session.exec(statement).all()

    def get_task_for_bill(self, bill_id: int, task_id: int) -> Optional[ReceiptTask]:
        statement = select(ReceiptTask).where(
            ReceiptTask.id == task_id, ReceiptTask.bill_id == bill_id
        )
        return self.session.exec(statement).first()
