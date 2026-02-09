from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from app.database import get_session
from app.schemas.bill_schemas import (
    BillCreate, BillResponse, BillItemCreate, BillItemResponse,
    BillParticipantCreate, BillParticipantResponse, BillDetailResponse,
    BillParticipantAssign, BillParticipantPaymentUpdate, BillParticipantRemove,
    BillSplitRemainder, ReactionCreate
)
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.services.bill_core_service import BillCoreService
from app.services.bill_item_service import BillItemService
from app.services.bill_participant_service import BillParticipantService
from app.services.bill_split_service import BillSplitService
from app.notifier import notifier

router = APIRouter(prefix="/bills", tags=["bills"])

def get_bill_core_service(session: Session = Depends(get_session)) -> BillCoreService:
    return BillCoreService(BillRepository(session), UserRepository(session))

def get_bill_item_service(session: Session = Depends(get_session)) -> BillItemService:
    return BillItemService(BillRepository(session), UserRepository(session))

def get_bill_participant_service(session: Session = Depends(get_session)) -> BillParticipantService:
    repo = BillRepository(session)
    user_repo = UserRepository(session)
    split_service = BillSplitService(repo, user_repo)
    return BillParticipantService(repo, user_repo, split_service)

def get_bill_split_service(session: Session = Depends(get_session)) -> BillSplitService:
    return BillSplitService(BillRepository(session), UserRepository(session))


@router.post("/", response_model=BillResponse)
def create_bill(
    bill_data: BillCreate, 
    service: BillCoreService = Depends(get_bill_core_service)
):
    """Create a new bill"""
    return service.create_bill(bill_data)

@router.get("/{bill_id}", response_model=BillDetailResponse)
def get_bill(
    bill_id: int, 
    service: BillCoreService = Depends(get_bill_core_service)
):
    """Get bill details with items and participants"""
    return service.get_bill_details(bill_id)

@router.post("/{bill_id}/items", response_model=BillItemResponse)
def add_bill_item(
    bill_id: int, 
    item_data: BillItemCreate, 
    service: BillItemService = Depends(get_bill_item_service)
):
    """Add an item to a bill"""
    return service.add_bill_item(bill_id, item_data)

@router.delete("/{bill_id}/items/{item_id}", status_code=204)
def delete_bill_item(
    bill_id: int,
    item_id: int,
    service: BillItemService = Depends(get_bill_item_service)
):
    """Delete an item from a bill"""
    service.delete_bill_item(bill_id, item_id)
    return None

@router.post("/{bill_id}/participants", response_model=list[BillParticipantResponse])
def add_bill_participant(
    bill_id: int, 
    participant_data: BillParticipantCreate, 
    service: BillParticipantService = Depends(get_bill_participant_service)
):
    """Add a participant to a bill"""
    return service.add_bill_participant(bill_id, participant_data)

@router.post("/{bill_id}/split-equally", response_model=list[BillParticipantResponse])
def split_bill_equally(
    bill_id: int, 
    service: BillSplitService = Depends(get_bill_split_service)
):
    """Distribute bill total sum equally among participants"""
    return service.split_bill_equally(bill_id)

@router.post("/{bill_id}/split-remainder", response_model=list[BillParticipantResponse])
def split_bill_remainder(
    bill_id: int,
    split_data: BillSplitRemainder,
    service: BillSplitService = Depends(get_bill_split_service)
):
    """Distribute remaining unallocated sum equally among selected participants"""
    return service.split_bill_remainder(bill_id, split_data.participant_ids)

@router.post("/{bill_id}/assign-amount", response_model=BillParticipantResponse)
def assign_participant_amount(
    bill_id: int,
    assign_data: BillParticipantAssign,
    service: BillSplitService = Depends(get_bill_split_service)
):
    """Manually assign amount to a participant"""
    return service.assign_amount(bill_id, assign_data)

@router.post("/{bill_id}/participants/{participant_id}/payment", response_model=BillParticipantResponse)
def update_payment_status(
    bill_id: int,
    participant_id: int,
    payment_data: BillParticipantPaymentUpdate,
    service: BillParticipantService = Depends(get_bill_participant_service)
):
    """Update participant's payment status"""
    return service.update_payment_status(bill_id, participant_id, payment_data)

@router.delete("/{bill_id}/participants/{participant_id}", response_model=BillDetailResponse)
def remove_bill_participant(
    bill_id: int,
    participant_id: int,
    remove_data: BillParticipantRemove,
    service: BillParticipantService = Depends(get_bill_participant_service)
):
    """Remove a participant from the bill"""
    return service.delete_bill_participant(bill_id, participant_id, remove_data.user_id)

@router.post("/{bill_id}/join", response_model=BillParticipantResponse)
def join_bill(
    bill_id: int,
    join_data: BillParticipantRemove, # Reusing same schema as it just has user_id
    service: BillParticipantService = Depends(get_bill_participant_service)
):
    """Join a bill as current user"""
    return service.join_bill(bill_id, join_data.user_id)

@router.get("/{bill_id}/events")
async def bill_events(bill_id: int):
    """Subscribe to real-time updates for a specific bill"""
    async def event_generator():
        async for message in notifier.subscribe(bill_id):
            yield f"data: {message}\n\n"
            
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

def send_reaction(bill_id: int, reaction: ReactionCreate):
    """Broadcast a reaction to all bill participants"""
    notifier.broadcast(bill_id, f"REACTION:{reaction.user_id}:{reaction.emoji}")
    return {"status": "ok"}

@router.post("/{bill_id}/close", response_model=BillDetailResponse)
def confirm_and_close_bill(
    bill_id: int,
    close_data: BillParticipantRemove,
    service: BillParticipantService = Depends(get_bill_participant_service)
):
    """Finalize payments and close the bill (Owner only)"""
    return service.confirm_and_close_bill(bill_id, close_data.user_id)
