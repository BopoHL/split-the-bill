from fastapi import HTTPException
from app.repositories.bill_repo import BillRepository
from app.models import Bill, BillUser

class BillValidator:
    def __init__(self, bill_repo: BillRepository):
        self.bill_repo = bill_repo

    def get_bill_or_404(self, bill_id: int) -> Bill:
        bill = self.bill_repo.get_by_id(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        return bill

    def ensure_bill_open(self, bill: Bill):
        from app.models import BillStatus
        if bill.status != BillStatus.OPEN:
            raise HTTPException(status_code=400, detail="Action not allowed on this bill state")

    def ensure_owner(self, bill: Bill, user_id: int):
        if bill.owner_id != user_id:
            raise HTTPException(status_code=403, detail="Only the bill owner can perform this action")

    def get_participant_or_404(self, participant_id: int, bill_id: int) -> BillUser:
        participant = self.bill_repo.get_participant_by_id(participant_id)
        if not participant or participant.bill_id != bill_id:
            raise HTTPException(status_code=404, detail="Participant not found for this bill")
        return participant
