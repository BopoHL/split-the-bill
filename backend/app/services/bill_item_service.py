from fastapi import HTTPException
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import BillItem
from app.utils.currency import to_tiins, from_tiins
from app.schemas.bill_schemas import BillItemCreate, BillItemResponse
from app.services.validator import BillValidator

class BillItemService:
    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.user_repo = user_repo
        self.validator = BillValidator(bill_repo)

    def add_bill_item(self, bill_id: int, item_data: BillItemCreate) -> BillItemResponse:
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)
        
        if item_data.assigned_to_user_id:
            user = self.user_repo.get_by_id(item_data.assigned_to_user_id)
            if not user:
                raise HTTPException(status_code=404, detail="Assigned user not found")
        
        price_tiins = to_tiins(item_data.price)
        item_sum_tiins = price_tiins * item_data.count

        item = BillItem(
            bill_id=bill_id,
            name=item_data.name,
            price=price_tiins,
            count=item_data.count,
            item_sum=item_sum_tiins,
            assigned_to_user_id=item_data.assigned_to_user_id
        )
        created_item = self.bill_repo.add_item(item)
        return BillItemResponse(
            id=created_item.id,
            bill_id=created_item.bill_id,
            name=created_item.name,
            price=from_tiins(created_item.price),
            count=created_item.count,
            item_sum=from_tiins(created_item.item_sum),
            assigned_to_user_id=created_item.assigned_to_user_id
        )

    def delete_bill_item(self, bill_id: int, item_id: int):
        bill = self.validator.get_bill_or_404(bill_id)
        self.validator.ensure_bill_open(bill)

        item = self.bill_repo.get_item_by_id(item_id)
        if not item or item.bill_id != bill_id:
            raise HTTPException(status_code=404, detail="Item not found for this bill")

        self.bill_repo.delete_item(item)
