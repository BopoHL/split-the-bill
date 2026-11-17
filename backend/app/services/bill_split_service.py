from fastapi import HTTPException
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import Bill, BillUser, SplitType
from app.utils.currency import to_tiins, from_tiins
from app.schemas.bill_schemas import BillParticipantResponse, BillParticipantAssign
from app.services.validator import BillValidator
from app.services.bill_participant_service import BillParticipantService
from app.services.item_split import TableSplit
from app.notifier import notifier

class BillSplitService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    def _locked_open(self, bill_id: int) -> Bill:
        """The bill, its row held until commit: two amounts set at once both
        read the same remainder and could hand it out twice."""
        bill = self.bill_repo.get_by_id_for_update(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        self.validator.ensure_bill_open(bill)
        return bill

    @staticmethod
    def spread_remainder(bill: Bill, selected: list[BillUser]) -> None:
        """Share the unallocated sum out among `selected`; the caller commits."""
        # Only to people who have not paid yet: a paid share stays as it was.
        # The owner never pays themselves, so they take what nobody else can —
        # a leftover on a bill everyone else has paid.
        targets = [p for p in selected if not p.is_paid] or [p for p in selected if p.user_id == bill.owner_id]
        if not targets:
            raise HTTPException(
                status_code=409,
                detail={"code": "PAID_ALLOCATION_LOCKED", "message": "Undo payment before changing an affected allocation"},
            )
        shares = TableSplit.of(bill, targets).split_evenly(bill.unallocated_sum, [p.id for p in targets])
        for p in targets:
            p.allocated_amount += shares[p.id]

        bill.unallocated_sum = 0
        bill.split_type = SplitType.MANUAL # Becomes manual as it's a specific allocation

    def split_bill_remainder(self, bill_id: int, p_ids: list[int]) -> list[BillParticipantResponse]:
        bill = self._locked_open(bill_id)

        if not p_ids:
            raise HTTPException(status_code=400, detail="No participants selected for remainder split")

        all_participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        selected_participants = [p for p in all_participants if p.id in p_ids]

        if not selected_participants:
            raise HTTPException(status_code=400, detail="Selected participants not found in this bill")
        
        if len(selected_participants) != len(p_ids):
             raise HTTPException(status_code=400, detail="Some selected participants were not found")

        self.spread_remainder(bill, selected_participants)
        self.bill_repo.session.add(bill)
        self.bill_repo.session.commit()
        
        notifier.broadcast(bill_id, "REFRESH")

        return [BillParticipantService.map_to_response(p) for p in all_participants]

    def assign_amount(self, bill_id: int, assign_data: BillParticipantAssign) -> BillParticipantResponse:
        bill = self._locked_open(bill_id)
        participant = self.validator.get_participant_or_404(assign_data.participant_id, bill_id)
        allocated_amount_tiins = to_tiins(assign_data.allocated_amount)
        if participant.is_paid and participant.user_id != bill.owner_id and allocated_amount_tiins != participant.allocated_amount:
            self.bill_repo.session.rollback()
            raise HTTPException(
                status_code=409,
                detail={"code": "PAID_ALLOCATION_LOCKED", "message": "Undo payment before changing an affected allocation"},
            )
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
        
        notifier.broadcast(bill_id, "REFRESH")
        
        return BillParticipantService.map_to_response(participant)

