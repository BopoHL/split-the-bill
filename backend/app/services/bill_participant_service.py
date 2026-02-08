import logging
from fastapi import HTTPException
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import BillUser, SplitType
from app.utils.currency import to_tiins, from_tiins
from app.schemas.bill_schemas import BillParticipantCreate, BillParticipantResponse, BillParticipantPaymentUpdate, BillDetailResponse, BillItemResponse
from app.services.validator import BillValidator
from app.notifier import notifier

logger = logging.getLogger(__name__)

class BillParticipantService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository, split_service=None):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)
        self.split_service = split_service

    def add_bill_participant(self, bill_id: int, participant_data: BillParticipantCreate) -> list[BillParticipantResponse]:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        
        if participant_data.user_id:
            user = self.user_repo.get_by_id(participant_data.user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
        
        if not participant_data.user_id and not participant_data.guest_name:
            raise HTTPException(status_code=400, detail="Must provide either user_id or guest_name")
        
        participant = BillUser(
            bill_id=bill_id,
            user_id=participant_data.user_id,
            guest_name=participant_data.guest_name,
            allocated_amount=0
        )
        
        created_participant = self.bill_repo.add_participant(participant)
        
        if bill.split_type == SplitType.EQUALLY:
            if self.split_service:
                result = self.split_service.split_bill_equally(bill_id)
                notifier.broadcast(bill_id, "REFRESH")
                return result
        
        # Default behavior: switch to manual if it wasn't equal (already set by default or manually)
        # and return all participants
        bill.split_type = SplitType.MANUAL
        self.bill_repo.session.add(bill)
        self.bill_repo.session.commit()
        
        notifier.broadcast(bill_id, "REFRESH")
        
        all_participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        return [self.map_to_response(p) for p in all_participants]

    def update_payment_status(self, bill_id: int, participant_id: int, payment_data: BillParticipantPaymentUpdate) -> BillParticipantResponse:
        bill = self.validator.get_bill_or_404(bill_id)
        participant = self.validator.get_participant_or_404(participant_id, bill_id)

        if participant.is_paid == payment_data.is_paid:
            return self.map_to_response(participant)

        is_owner = (bill.owner_id == payment_data.user_id)
        is_self = (participant.user_id == payment_data.user_id)

        if not (is_owner or is_self):
            raise HTTPException(status_code=403, detail="Not authorized to change payment status")

        if is_self and not is_owner and not payment_data.is_paid:
            raise HTTPException(status_code=403, detail="Participants can only mark themselves as paid, only owner can cancel payment")

        if payment_data.is_paid and participant.allocated_amount <= 0:
            raise HTTPException(status_code=400, detail="Cannot confirm payment for zero or negative amount")

        participant.is_paid = payment_data.is_paid
        self.bill_repo.session.add(participant)
        self.bill_repo.session.commit()
        self.bill_repo.session.refresh(participant)

        notifier.broadcast(bill_id, "REFRESH")

        return self.map_to_response(participant)

    def delete_bill_participant(self, bill_id: int, participant_id: int, requester_id: int) -> BillDetailResponse:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        
        participant = self.validator.get_participant_or_404(participant_id, bill_id)
        
        # Authorization: owner can remove anyone, or participant can remove themselves
        is_owner = (bill.owner_id == requester_id)
        is_self = (participant.user_id == requester_id)
        
        if not (is_owner or is_self):
            raise HTTPException(status_code=403, detail="Not authorized to remove this participant")
            
        # 1. Unassign items
        if participant.user_id:
            items = self.bill_repo.get_items_by_bill_id_and_participant(bill_id, participant.user_id)
            for item in items:
                item.assigned_to_user_id = None
                self.bill_repo.session.add(item)
        
        # 2. Return amount to unallocated if manual
        if bill.split_type == SplitType.MANUAL:
            bill.unallocated_sum += participant.allocated_amount
            self.bill_repo.session.add(bill)
        
        # 3. Delete participant
        self.bill_repo.delete_participant(participant)
        
        # 4. Handle re-split if equal
        if bill.split_type == SplitType.EQUALLY:
            if self.split_service:
                self.split_service.split_bill_equally(bill_id)
        
        self.bill_repo.session.commit()
        
        notifier.broadcast(bill_id, "REFRESH")
        
        return self._get_bill_details_response(bill_id)

    def join_bill(self, bill_id: int, user_id: int) -> BillParticipantResponse:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        existing_participant = self.bill_repo.get_participant_by_bill_and_user(bill_id, user_id)
        if existing_participant:
            return self.map_to_response(existing_participant)
            
        participant = BillUser(
            bill_id=bill_id,
            user_id=user_id,
            allocated_amount=0
        )
        
        created_participant = self.bill_repo.add_participant(participant)
        
        if bill.split_type == SplitType.EQUALLY:
            if self.split_service:
                self.split_service.split_bill_equally(bill_id)
        else:
            bill.split_type = SplitType.MANUAL
            self.bill_repo.session.add(bill)
            
        self.bill_repo.session.commit()
        self.bill_repo.session.refresh(created_participant)
        
        notifier.broadcast(bill_id, "REFRESH")
        
        # Ensure user relationship is loaded for the response
        if created_participant.user_id and not created_participant.user:
            created_participant.user = self.user_repo.get_by_id(created_participant.user_id)
            
        return self.map_to_response(created_participant)

    def _get_bill_details_response(self, bill_id: int) -> BillDetailResponse:
        bill = self.validator.get_bill_or_404(bill_id)
        items = self.bill_repo.get_items_by_bill_id(bill_id)
        participants = self.bill_repo.get_participants_by_bill_id(bill_id)
        
        return BillDetailResponse(
            id=bill.id,
            owner_id=bill.owner_id,
            total_sum=from_tiins(bill.total_sum),
            title=bill.title,
            payment_details=bill.payment_details,
            is_closed=bill.is_closed,
            split_type=bill.split_type,
            unallocated_sum=from_tiins(bill.unallocated_sum),
            created_at=bill.created_at,
            items=[BillItemResponse(
                id=item.id,
                bill_id=item.bill_id,
                name=item.name,
                price=from_tiins(item.price),
                count=item.count,
                item_sum=from_tiins(item.item_sum),
                assigned_to_user_id=item.assigned_to_user_id
            ) for item in items],
            participants=[self.map_to_response(p) for p in participants]
        )

    @staticmethod
    def map_to_response(p: BillUser) -> BillParticipantResponse:
        username = p.guest_name
        avatar_url = None
        
        if hasattr(p, "user") and p.user:
            username = p.user.username
            avatar_url = p.user.avatar_url
            
        return BillParticipantResponse(
            id=p.id,
            bill_id=p.bill_id,
            user_id=p.user_id,
            guest_name=p.guest_name,
            username=username,
            avatar_url=avatar_url,
            allocated_amount=from_tiins(p.allocated_amount),
            is_paid=p.is_paid
        )
