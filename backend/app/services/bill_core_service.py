from fastapi import HTTPException
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import Bill, BillUser
from app.utils.currency import to_tiins, from_tiins
from app.schemas.bill_schemas import BillCreate, BillResponse, BillDetailResponse, BillItemResponse, BillParticipantResponse
from app.services.validator import BillValidator

class BillCoreService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    def create_bill(self, bill_data: BillCreate) -> BillResponse:
        owner = self.user_repo.get_by_id(bill_data.owner_id)
        if not owner:
            raise HTTPException(status_code=404, detail="Owner user not found")
        
        bill = Bill(
            owner_id=bill_data.owner_id,
            total_sum=to_tiins(bill_data.total_sum),
            unallocated_sum=to_tiins(bill_data.total_sum),
            title=bill_data.title,
            payment_details=bill_data.payment_details
        )
        created_bill = self.bill_repo.create(bill)

        participants_count = 0
        if bill_data.include_owner:
            owner_participant = BillUser(
                bill_id=created_bill.id,
                user_id=created_bill.owner_id,
                allocated_amount=0
            )
            self.bill_repo.add_participant(owner_participant)
            participants_count = 1

        return BillResponse(
            id=created_bill.id,
            owner_id=created_bill.owner_id,
            total_sum=from_tiins(created_bill.total_sum),
            title=created_bill.title,
            payment_details=created_bill.payment_details,
            is_closed=created_bill.is_closed,
            split_type=created_bill.split_type,
            unallocated_sum=from_tiins(created_bill.unallocated_sum),
            created_at=created_bill.created_at,
            participants_count=participants_count
        )

    def get_bill_details(self, bill_id: int) -> BillDetailResponse:
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
            participants=[BillParticipantResponse(
                id=p.id,
                bill_id=p.bill_id,
                user_id=p.user_id,
                guest_name=p.guest_name,
                allocated_amount=from_tiins(p.allocated_amount),
                is_paid=p.is_paid
            ) for p in participants]
        )

    def get_user_bills(self, user_id: int, offset: int = 0, limit: int = 10) -> list[BillResponse]:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        results = self.bill_repo.get_user_bills(user_id, offset=offset, limit=limit)
        
        return [
            BillResponse(
                id=bill.id,
                owner_id=bill.owner_id,
                total_sum=from_tiins(bill.total_sum),
                title=bill.title,
                payment_details=bill.payment_details,
                is_closed=bill.is_closed,
                split_type=bill.split_type,
                unallocated_sum=from_tiins(bill.unallocated_sum),
                created_at=bill.created_at,
                participants_count=participants_count
            )
            for bill, participants_count in results
        ]
