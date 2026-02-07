from fastapi import HTTPException
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import SplitType
from app.utils.currency import to_tiins, from_tiins
from app.schemas.bill_schemas import BillParticipantResponse, BillParticipantAssign
from app.services.validator import BillValidator

class BillSplitService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    def split_bill_equally(self, bill_id: int) -> list[BillParticipantResponse]:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
            
        all_participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        unpaid_participants = [p for p in all_participants if not p.is_paid]

        if not unpaid_participants:
            raise HTTPException(status_code=400, detail="No unpaid participants to assign amounts to")
            
        # Amount to split is total_sum - (sum of amounts already paid/fixed)
        paid_sum = sum(p.allocated_amount for p in all_participants if p.is_paid)
        sum_to_split = bill.total_sum - paid_sum
        
        if sum_to_split < 0:
             raise HTTPException(status_code=400, detail="Sum of paid amounts exceeds bill total")

        count = len(unpaid_participants)
        base_amount = sum_to_split // count
        remainder = sum_to_split % count
        
        # Decide who gets the remainder (priority: owner if unpaid, else first unpaid)
        recipient_idx = 0
        for i, p in enumerate(unpaid_participants):
            if p.user_id == bill.owner_id:
                recipient_idx = i
                break
        
        for i, p in enumerate(unpaid_participants):
            amount = base_amount
            if i == recipient_idx:
                amount += remainder
            p.allocated_amount = amount
            self.bill_repo.session.add(p)
            
        bill.split_type = SplitType.EQUALLY
        bill.unallocated_sum = 0
        self.bill_repo.session.add(bill)
        self.bill_repo.session.commit()
            
        return [self._to_response(p) for p in all_participants]

    def split_bill_remainder(self, bill_id: int, p_ids: list[int]) -> list[BillParticipantResponse]:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)

        if not p_ids:
            raise HTTPException(status_code=400, detail="No participants selected for remainder split")

        all_participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        selected_participants = [p for p in all_participants if p.id in p_ids]

        if not selected_participants:
            raise HTTPException(status_code=400, detail="Selected participants not found in this bill")
        
        if len(selected_participants) != len(p_ids):
             raise HTTPException(status_code=400, detail="Some selected participants were not found")

        # Filter out those who already paid
        unpaid_selected = [p for p in selected_participants if not p.is_paid]
        if not unpaid_selected:
            raise HTTPException(status_code=400, detail="All selected participants have already paid. No one to split the remainder with.")

        count = len(unpaid_selected)
        base_remainder = bill.unallocated_sum // count
        extra_tiins = bill.unallocated_sum % count

        # Determine who gets the extra tiins
        recipient_idx = 0
        for i, p in enumerate(unpaid_selected):
            if p.user_id == bill.owner_id:
                recipient_idx = i
                break
        
        for i, p in enumerate(unpaid_selected):
            amount_to_add = base_remainder
            if i == recipient_idx:
                amount_to_add += extra_tiins
            
            p.allocated_amount += amount_to_add
            self.bill_repo.session.add(p)

        bill.unallocated_sum = 0
        bill.split_type = SplitType.MANUAL # Becomes manual as it's a specific allocation
        self.bill_repo.session.add(bill)
        self.bill_repo.session.commit()

        return [self._to_response(p) for p in all_participants]

    def assign_amount(self, bill_id: int, assign_data: BillParticipantAssign) -> BillParticipantResponse:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
            
        participant = self.validator.get_participant_or_404(assign_data.participant_id, bill_id)
            
        allocated_amount_tiins = to_tiins(assign_data.allocated_amount)
        diff = allocated_amount_tiins - participant.allocated_amount
        
        if diff > bill.unallocated_sum:
            raise HTTPException(
                status_code=400, 
                detail=f"Amount exceeds unallocated sum. Max available: {from_tiins(bill.unallocated_sum + participant.allocated_amount)}"
            )
            
        participant.allocated_amount = allocated_amount_tiins
        bill.unallocated_sum -= diff
        bill.split_type = SplitType.MANUAL
        
        self.bill_repo.session.add(bill)
        self.bill_repo.session.commit()
        self.bill_repo.session.refresh(participant)
        
        return self._to_response(participant)

    def _to_response(self, p) -> BillParticipantResponse:
        return BillParticipantResponse(
            id=p.id,
            bill_id=p.bill_id,
            user_id=p.user_id,
            guest_name=p.guest_name,
            allocated_amount=from_tiins(p.allocated_amount),
            is_paid=p.is_paid
        )
