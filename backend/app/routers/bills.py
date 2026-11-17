from datetime import datetime, timezone
from typing import Literal
import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, FileResponse, Response
from sqlmodel import Session
from app.database import engine, get_session
from app.repositories.file_repo import FileAssetRepository
from app.repositories.receipt_repo import ReceiptRepository
from app.services.receipt_service import ReceiptService
from app.schemas.bill_schemas import (
    BillCreate, BillUpdate, BillResponse, BillItemCreate, BillItemResponse,
    BillParticipantCreate, BillParticipantResponse, BillDetailResponse,
    BillParticipantAssign, BillParticipantPaymentUpdate, BillParticipantRemove, BillClose,
    BillSplitRemainder, BillItemAssign, BillItemAssignBatch, BillJoinByToken, BillItemUpdate,
    ScanFeedback, BillShareRequest, BillPersonalSeatInviteRequest, BillJoinWelcome,
    BillParticipantRename, SeatClaim, BillSeatsResponse, ReceiptDeleteImpact,
    BillSeatAssign, BillAssignableUser, BillPlaceUpdate, BillPlaceResponse, VoiceBillResponse, VoiceHeardResponse
)
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.models import BillStatus, ReceiptSource, User
from app.dependencies import (
    ensure_self,
    get_authenticated_user,
    unsigned_init_data_allowed,
    require_bill_member,
    require_bill_owner,
)
from app.services.sse_ticket_service import resource_key, sse_tickets
from app.services.bill_core_service import BillCoreService
from app.services.bill_item_service import BillItemService
from app.services.bill_participant_service import BillParticipantService
from app.services.bill_split_service import BillSplitService
from app.services.bill_summary import summary_for
from app.services.profile_photos import profile_photos
from app.services.drawing import resolve_theme
from app.services.share_card import render_card
from app.utils.local_time import local_zone
from app.utils.bot_copy import resolve_language
from app.services.invite_service import InviteService
from app.repositories.invite_repo import InviteRepository
from app.schemas.invite_schemas import InviteCreate, InviteResponse
from app.notifier import notifier
from app.schemas.reminder_schemas import ReminderRequest, ReminderRequestResponse
from app.services.reminder_service import ReminderService
from app.services.places import set_place
from app.services.pro import require_pro
from app.services.voice_bill import VoiceBillService, recording, refused

# Every bill route needs to know who is calling. The exceptions live on
# public_router: the pictures Telegram fetches by token, and the SSE stream,
# which cannot carry a header and uses a ticket instead.
router = APIRouter(
    prefix="/bills", tags=["bills"], dependencies=[Depends(get_authenticated_user)]
)
public_router = APIRouter(prefix="/bills", tags=["bills"])

def get_bill_core_service(session: Session = Depends(get_session)) -> BillCoreService:
    return BillCoreService(BillRepository(session), UserRepository(session))

def get_bill_item_service(session: Session = Depends(get_session)) -> BillItemService:
    return BillItemService(BillRepository(session), UserRepository(session))

def get_bill_participant_service(session: Session = Depends(get_session)) -> BillParticipantService:
    repo = BillRepository(session)
    user_repo = UserRepository(session)
    return BillParticipantService(repo, user_repo)

def get_bill_split_service(session: Session = Depends(get_session)) -> BillSplitService:
    return BillSplitService(BillRepository(session), UserRepository(session))

def get_invite_service(session: Session = Depends(get_session)) -> InviteService:
    return InviteService(
        InviteRepository(session), BillRepository(session), UserRepository(session)
    )


@router.post("/{bill_id}/invites", response_model=InviteResponse)
def create_invite(
    bill_id: int,
    payload: InviteCreate,
    current_user: User = Depends(get_authenticated_user),
    service: InviteService = Depends(get_invite_service),
):
    """Mint a share of this bill, so whoever follows it is credited to the
    person who shared it and to the channel they used."""
    return service.create_response(
        bill_id, current_user.id, payload.channel, payload.seat_participant_id
    )


@router.post("/", response_model=BillResponse)
def create_bill(
    bill_data: BillCreate,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    ensure_self(current_user, bill_data.owner_id)
    """Create a new bill"""
    return service.create_bill(bill_data)

@router.delete("/{bill_id}", status_code=204)
def delete_bill(
    bill_id: int,
    user_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service)
):
    """Delete a bill (owner only)."""
    ensure_self(current_user, user_id)
    service.delete_bill(bill_id, current_user.id)
    return None

@router.post("/{bill_id}/prepare-share")
def prepare_share(
    bill_id: int,
    payload: BillShareRequest,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Register a clean invite post with Telegram and return its
    prepared_message_id for WebApp.shareMessage (Bot API 8.0)."""
    prepared_id = service.prepare_share_message(bill_id, current_user.id, payload.lang)
    return {"prepared_message_id": prepared_id}


@router.post("/{bill_id}/seats/{participant_id}/prepare-invite")
def prepare_personal_seat_invite(
    bill_id: int,
    participant_id: int,
    payload: BillPersonalSeatInviteRequest,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Register a one-seat invite whose CTA opens the bill and claims the guest seat."""
    prepared_id = service.prepare_personal_seat_invite(
        bill_id, participant_id, current_user.id, payload.lang
    )
    return {"prepared_message_id": prepared_id}

def get_reminder_service(session: Session = Depends(get_session)) -> ReminderService:
    return ReminderService(session)


@router.post("/{bill_id}/reminders", response_model=ReminderRequestResponse)
def send_reminders(
    bill_id: int,
    payload: ReminderRequest,
    current_user: User = Depends(get_authenticated_user),
    service: ReminderService = Depends(get_reminder_service),
):
    """Owner only, with Pro: remind one seat, or everyone who still owes. They
    go out within seconds — from the bot, or from a sender account when the bot
    is blocked; the seat's `reminder` in the bill says how it went."""
    requested = service.request_for_bill(bill_id, current_user.id, payload.participant_id, datetime.utcnow())
    return ReminderRequestResponse.of(len(requested.queued), requested.skipped)


@router.put("/{bill_id}/place", response_model=BillPlaceResponse)
def set_bill_place(
    bill_id: int,
    payload: BillPlaceUpdate,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """Owner only: where the bill was. Open or closed — a place is about the
    evening, not the money, and it is what analytics count visits by."""
    bill = BillRepository(session).get_by_id(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    place = set_place(session, bill, current_user.id, payload.name, datetime.utcnow())
    notifier.broadcast(bill_id, "REFRESH")
    return BillPlaceResponse(place=place)


@router.get("/{bill_id}/assignable-users", response_model=list[BillAssignableUser])
def list_assignable_users(
    bill_id: int,
    q: str | None = None,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """People the owner can put on a guest seat: those they have shared a bill
    with or brought into the app, or — with `q` — a username lookup."""
    return [
        BillAssignableUser(
            user_id=user.id,
            username=user.username,
            name=user.name,
            surname=user.surname,
            avatar_url=user.avatar_url,
        )
        for user in service.list_assignable_users(bill_id, current_user.id, q)
    ]


@router.post("/{bill_id}/seats/{participant_id}/assign", response_model=BillDetailResponse)
def assign_seat_user(
    bill_id: int,
    participant_id: int,
    payload: BillSeatAssign,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Seat someone on a guest seat and send them the invite in the bot. Owner
    only. The seat stays free if the bot cannot reach them."""
    return service.assign_seat_user(
        bill_id, participant_id, current_user.id, payload.target_user_id, payload.lang
    )


@router.get("/{bill_id}", response_model=BillDetailResponse)
def get_bill(
    bill_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Get bill details — owner or participant only, so bills cannot be
    enumerated by id."""
    return service.get_bill_details(bill_id, requester_id=current_user.id)

@router.get("/{bill_id}/receipt")
def get_bill_receipt(
    bill_id: int,
    current_user: User = Depends(require_bill_member),
    session: Session = Depends(get_session),
):
    """Serve the receipt photo attached to a bill (owner/participant only)."""
    asset = FileAssetRepository(session).get_first_by_bill_id(bill_id)
    if not asset or not os.path.exists(asset.path):
        raise HTTPException(status_code=404, detail="No receipt for this bill")
    return FileResponse(asset.path, media_type=asset.mime_type)

@public_router.get("/public/{public_token}/receipt")
def get_public_bill_receipt(
    public_token: str,
    session: Session = Depends(get_session),
):
    """Serve a bill's receipt by its unguessable public token, WITHOUT auth, so
    Telegram can fetch it for the prepared invite message. Access is gated by
    the token (same as the invite link itself)."""
    bill_repo = BillRepository(session)
    bill = bill_repo.get_by_token(public_token)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    asset = FileAssetRepository(session).get_first_by_bill_id(bill.id)
    if not asset or not os.path.exists(asset.path):
        raise HTTPException(status_code=404, detail="No receipt for this bill")
    return FileResponse(asset.path, media_type=asset.mime_type)

@public_router.get("/public/{public_token}/card.png")
def get_public_bill_card(
    public_token: str,
    lang: str | None = None,
    theme: str | None = None,
    session: Session = Depends(get_session),
):
    """The picture Telegram shows above a shared bill, drawn from its current
    state. Unauthenticated for the same reason as the receipt: Telegram fetches
    it, and the token is the one the invite link already carries. The `v` query
    parameter it is linked with only tells Telegram's cache states apart."""
    bill = BillRepository(session).get_by_token(public_token)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    summary = summary_for(session, bill)
    picture = render_card(
        summary,
        resolve_language(lang),
        datetime.now(timezone.utc),
        local_zone(),
        profile_photos.for_people(seat.telegram_id for seat in summary.seats if seat.telegram_id),
        resolve_theme(theme),
    )
    return Response(picture, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})

@router.post("/{bill_id}/receipt", status_code=201)
async def attach_bill_receipt(
    bill_id: int,
    file: UploadFile = File(...),
    user_id: int = Form(...),
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """Attach a receipt photo to an existing bill (owner only).

    No AI parsing — the image is stored and linked to the bill so it shows on
    the bill page. Used for manually created bills.
    """
    ensure_self(current_user, user_id)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    bill_repo = BillRepository(session)
    bill = bill_repo.get_by_id(bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.owner_id != user_id:
        raise HTTPException(
            status_code=403, detail="Only the owner can attach a receipt"
        )
    if bill.status != BillStatus.OPEN:
        raise HTTPException(status_code=409, detail="Only open bills can attach a receipt")
    service = ReceiptService(ReceiptRepository(session), FileAssetRepository(session))
    await service.attach_to_bill(file, bill_id, user_id)
    return {"status": "ok"}

@router.post("/{bill_id}/receipts/{task_id}/feedback")
def submit_scan_feedback(
    bill_id: int,
    task_id: int,
    feedback: ScanFeedback,
    current_user: User = Depends(get_authenticated_user),
    session: Session = Depends(get_session),
):
    """Rate ONE receipt's scan 1-5 (owner only).

    A bill can hold several receipts scanned with wildly different quality, so a
    single rating for the whole bill said nothing useful. Receipts the user
    attached without recognition have nothing to rate.
    """
    ensure_self(current_user, feedback.user_id)
    if feedback.rating < 1 or feedback.rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    bill_repo = BillRepository(session)
    bill = bill_repo.get_by_id(bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.owner_id != feedback.user_id:
        raise HTTPException(status_code=403, detail="Only the owner can rate the scan")

    task = ReceiptRepository(session).get_task_for_bill(bill_id, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Receipt not found for this bill")
    if task.source == ReceiptSource.MANUAL_PHOTO:
        raise HTTPException(status_code=400, detail="This receipt was not scanned")

    task.scan_quality = feedback.rating
    session.add(task)
    session.commit()
    return {"status": "ok", "scan_quality": feedback.rating}

@router.patch("/{bill_id}", response_model=BillDetailResponse)
def update_bill(
    bill_id: int,
    update_data: BillUpdate,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Update bill fields (e.g. payment details)"""
    ensure_self(current_user, update_data.user_id)
    return service.update_bill(bill_id, update_data)

@router.post("/{bill_id}/items", response_model=BillItemResponse)
def add_bill_item(
    bill_id: int, 
    item_data: BillItemCreate,
    current_user: User = Depends(require_bill_owner),
    service: BillItemService = Depends(get_bill_item_service),
):
    """Add an item to a bill (owner only)."""
    return service.add_bill_item(bill_id, item_data)

@router.delete("/{bill_id}/items/{item_id}", status_code=204)
def delete_bill_item(
    bill_id: int,
    item_id: int,
    portion_index: int | None = Query(default=None, ge=0),
    expected_count: int | None = Query(default=None, ge=1),
    current_user: User = Depends(require_bill_owner),
    service: BillItemService = Depends(get_bill_item_service),
):
    """Delete an item from a bill (owner only)."""
    service.delete_bill_item(
        bill_id,
        item_id,
        portion_index=portion_index,
        expected_count=expected_count,
    )
    return None

@router.patch("/{bill_id}/items/{item_id}", response_model=BillItemResponse)
def update_bill_item(
    bill_id: int,
    item_id: int,
    item_data: BillItemUpdate,
    portion_index: int | None = Query(default=None, ge=0),
    expected_count: int | None = Query(default=None, ge=1),
    current_user: User = Depends(require_bill_owner),
    service: BillItemService = Depends(get_bill_item_service),
):
    """Edit an item's name/price/count (or its shared flag). Owner only."""
    return service.update_bill_item(
        bill_id,
        item_id,
        item_data,
        portion_index=portion_index,
        expected_count=expected_count,
    )

@router.post("/{bill_id}/items/{item_id}/assign")
def assign_bill_item(
    bill_id: int,
    item_id: int,
    assign_data: BillItemAssign,
    current_user: User = Depends(get_authenticated_user),
    service: BillItemService = Depends(get_bill_item_service),
):
    """Assign or unassign a user to a specific item"""
    return service.assign_item(bill_id, item_id, assign_data, current_user.id)

@router.post("/{bill_id}/items/assign-batch", response_model=BillDetailResponse)
def assign_bill_items_batch(
    bill_id: int,
    batch: BillItemAssignBatch,
    current_user: User = Depends(require_bill_member),
    service: BillItemService = Depends(get_bill_item_service),
    core: BillCoreService = Depends(get_bill_core_service),
):
    """Apply a whole multi-select of assign/unassign ops in one atomic request and
    return the updated bill, so the client never fans out into N refetches."""
    service.assign_items_batch(bill_id, batch, current_user.id)
    return core.get_bill_details(bill_id, current_user.id)

@router.post("/{bill_id}/voice/hear", response_model=VoiceHeardResponse)
def hear_bill(
    bill_id: int,
    audio: UploadFile = File(...),
    current_user: User = Depends(require_bill_owner),
    session: Session = Depends(get_session),
):
    """The words of a recording, before anything is done with them: the app
    shows them while the bill is filled from them. Pro only."""
    require_pro(session, current_user, "voice", datetime.utcnow())
    heard = VoiceBillService(BillRepository(session), UserRepository(session)).hear(bill_id, *recording(audio))
    if not heard:
        raise refused(422, "VOICE_EMPTY")
    return VoiceHeardResponse(heard=heard)


@router.post("/{bill_id}/voice", response_model=VoiceBillResponse)
def tell_bill(
    bill_id: int,
    text: str = Form(...),
    current_user: User = Depends(require_bill_owner),
    session: Session = Depends(get_session),
    core: BillCoreService = Depends(get_bill_core_service),
):
    """The owner says what was ordered and who had it — heard from a recording,
    or typed where the phone cannot record. New lines are added and the ones
    whose eaters were named handed out. Pro only."""
    require_pro(session, current_user, "voice", datetime.utcnow())
    told = VoiceBillService(BillRepository(session), UserRepository(session)).tell(bill_id, text)
    return VoiceBillResponse(
        heard=told.heard,
        added=told.added,
        assigned=told.assigned,
        held=told.held,
        unseated=told.unseated,
        bill=core.get_bill_details(bill_id, current_user.id),
    )

@router.post("/{bill_id}/participants", response_model=list[BillParticipantResponse])
def add_bill_participant(
    bill_id: int, 
    participant_data: BillParticipantCreate,
    current_user: User = Depends(require_bill_owner),
    service: BillParticipantService = Depends(get_bill_participant_service),
):
    """The owner seating someone by hand — a developer's tool for filling a
    table. In production it would let an owner seat any account by id and read
    its profile; joining goes through the invite link, which proves the invite."""
    if not unsigned_init_data_allowed():
        raise HTTPException(status_code=404, detail="Not found")
    return service.add_bill_participant(bill_id, participant_data)

@router.post("/{bill_id}/split-remainder", response_model=BillDetailResponse)
def split_bill_remainder(
    bill_id: int,
    split_data: BillSplitRemainder,
    current_user: User = Depends(require_bill_owner),
    service: BillSplitService = Depends(get_bill_split_service),
    core: BillCoreService = Depends(get_bill_core_service),
):
    """Distribute remaining unallocated sum equally among selected participants.

    Returns the full recomputed bill so the client never re-derives totals.
    """
    service.split_bill_remainder(bill_id, split_data.participant_ids)
    return core.get_bill_details(bill_id, current_user.id)

@router.post("/{bill_id}/assign-amount", response_model=BillDetailResponse)
def assign_participant_amount(
    bill_id: int,
    assign_data: BillParticipantAssign,
    current_user: User = Depends(require_bill_owner),
    service: BillSplitService = Depends(get_bill_split_service),
    core: BillCoreService = Depends(get_bill_core_service),
):
    """Manually assign amount to a participant; returns the recomputed bill."""
    service.assign_amount(bill_id, assign_data)
    return core.get_bill_details(bill_id, current_user.id)

@router.post("/{bill_id}/participants/{participant_id}/payment", response_model=BillDetailResponse)
def update_payment_status(
    bill_id: int,
    participant_id: int,
    payment_data: BillParticipantPaymentUpdate,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
    core: BillCoreService = Depends(get_bill_core_service),
):
    """Update payment status; returns the recomputed bill (status/totals included)."""
    ensure_self(current_user, payment_data.user_id)
    service.update_payment_status(bill_id, participant_id, payment_data)
    return core.get_bill_details(bill_id, current_user.id)

@router.delete("/{bill_id}/participants/{participant_id}", response_model=BillDetailResponse)
def remove_bill_participant(
    bill_id: int,
    participant_id: int,
    remove_data: BillParticipantRemove,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
):
    """Free a seat — the person leaves, the seat and its dishes stay."""
    ensure_self(current_user, remove_data.user_id)
    return service.release_seat(bill_id, participant_id, remove_data.user_id)


@router.patch("/{bill_id}/participants/{participant_id}", response_model=BillParticipantResponse)
def rename_guest_seat(
    bill_id: int,
    participant_id: int,
    data: BillParticipantRename,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
):
    """Label an unclaimed guest seat. Owner only."""
    ensure_self(current_user, data.user_id)
    return service.rename_guest(bill_id, participant_id, data.user_id, data.guest_name)


@router.get("/{bill_id}/receipts/{task_id}/image")
def get_receipt_image(
    bill_id: int,
    task_id: int,
    current_user: User = Depends(require_bill_member),
    session: Session = Depends(get_session),
):
    """The photo of one specific receipt on the bill."""
    asset = FileAssetRepository(session).get_by_task_id(task_id)
    if not asset or asset.bill_id != bill_id or not os.path.exists(asset.path):
        raise HTTPException(status_code=404, detail="No photo for this receipt")
    return FileResponse(asset.path, media_type=asset.mime_type)


@router.get("/{bill_id}/receipts/{task_id}/impact", response_model=ReceiptDeleteImpact)
def get_receipt_delete_impact(
    bill_id: int,
    task_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """What deleting this receipt would take with it — quoted in the dialog."""
    return service.get_receipt_delete_impact(bill_id, task_id, current_user.id)


@router.delete("/{bill_id}/receipts/{task_id}", response_model=BillDetailResponse)
def delete_receipt(
    bill_id: int,
    task_id: int,
    items: Literal["delete", "keep"] = "delete",
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Remove one receipt. `items=keep` detaches its lines instead of deleting
    them, so they survive in the «no receipt» group."""
    return service.delete_receipt(
        bill_id, task_id, current_user.id, keep_items=items == "keep"
    )


@router.get("/public/{public_token}/seats", response_model=BillSeatsResponse)
def get_seats_by_token(
    public_token: str,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
):
    """Seats behind an invite link — readable before you're in the bill."""
    return service.get_seats_by_token(public_token, current_user.id)


@router.post("/{bill_id}/seats/{participant_id}/claim", response_model=BillDetailResponse)
def claim_seat(
    bill_id: int,
    participant_id: int,
    data: SeatClaim,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
    invites: InviteService = Depends(get_invite_service),
):
    """Sit down at a seat, or move to a different one."""
    ensure_self(current_user, data.user_id)
    inviter_id = invites.inviter_for(data.invite_code, bill_id)
    bill = service.validator.get_bill_or_404(bill_id)
    is_member = bill.owner_id == current_user.id or (
        service.bill_repo.get_participant_by_bill_and_user(bill_id, current_user.id) is not None
    )
    was_invited = inviter_id is not None or secrets.compare_digest(
        data.token or "", bill.public_token
    )
    if not (is_member or was_invited):
        raise HTTPException(status_code=403, detail="INVITE_REQUIRED")
    return service.claim_seat(
        bill_id,
        participant_id,
        current_user.id,
        inviter_id,
        confirm_move=data.confirm_move,
    )


@router.post("/{bill_id}/seats/{participant_id}/release", response_model=BillDetailResponse)
def release_seat(
    bill_id: int,
    participant_id: int,
    data: SeatClaim,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
):
    """Stand up from a seat, leaving its dishes for whoever sits there next."""
    ensure_self(current_user, data.user_id)
    return service.release_seat(bill_id, participant_id, current_user.id)

@router.post("/join-by-token", response_model=BillParticipantResponse)
def join_bill_by_token(
    join_data: BillJoinByToken,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
    invites: InviteService = Depends(get_invite_service),
):
    """Join a bill via its unguessable public token (used by invite links).

    Returns the participant record, whose bill_id the client uses to navigate.
    """
    ensure_self(current_user, join_data.user_id)
    bill = service.bill_repo.get_by_token(join_data.token)
    inviter_id = invites.inviter_for(join_data.invite_code, bill.id) if bill else None
    return service.join_bill_by_token(join_data.token, current_user.id, inviter_id)

@router.post("/{bill_id}/join-welcome", status_code=204)
def join_welcome(
    bill_id: int,
    payload: BillJoinWelcome,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
):
    """After a user joins via an invite link and grants write access, the bot sends
    its one-time onboarding DM (landing in their chat list). Best-effort — never
    blocks the join flow."""
    service.send_onboarding_dm(bill_id, current_user.id, payload.lang)
    return None

@public_router.get("/{bill_id}/events")
async def bill_events(bill_id: int, ticket: str | None = None):
    """Subscribe to real-time updates for a specific bill.

    EventSource cannot send the identity header, so the caller first trades it
    for a one-shot ticket at POST /api/auth/sse-ticket.

    The check gets a session of its own, closed before streaming starts: a
    request-scoped one would hold a pooled connection for as long as the screen
    stays open, and fifteen open bills would empty the pool for everyone.
    """
    user_id = sse_tickets.redeem(ticket, resource_key("bill", bill_id))
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired stream ticket")
    with Session(engine) as session:
        bill_repo = BillRepository(session)
        bill = bill_repo.get_by_id(bill_id)
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found")
        is_member = (
            bill.owner_id == user_id
            or bill_repo.get_participant_by_bill_and_user(bill_id, user_id) is not None
        )
    if not is_member:
        raise HTTPException(status_code=403, detail="Not authorized to view this bill")

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

@router.post("/{bill_id}/close", response_model=BillDetailResponse)
def confirm_and_close_bill(
    bill_id: int,
    close_data: BillClose,
    current_user: User = Depends(get_authenticated_user),
    service: BillParticipantService = Depends(get_bill_participant_service),
):
    """Finalize payments and close the bill (Owner only)"""
    ensure_self(current_user, close_data.user_id)
    return service.confirm_and_close_bill(bill_id, current_user.id, close_data.remainder)

@router.post("/{bill_id}/reopen", response_model=BillDetailResponse)
def reopen_bill(
    bill_id: int,
    reopen_data: BillParticipantRemove,
    current_user: User = Depends(get_authenticated_user),
    service: BillCoreService = Depends(get_bill_core_service),
):
    """Reopen a closed bill (Owner only)."""
    ensure_self(current_user, reopen_data.user_id)
    return service.reopen_bill(bill_id, current_user.id)
