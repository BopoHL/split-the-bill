import os
import asyncio
import json
import weakref
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import update
from sqlmodel import Session
from app.database import get_session, engine
from app.models import ReceiptTask, ReceiptTaskStatus, BillStatus
from app.schemas.receipt_schemas import ReceiptTaskResponse
from app.services.receipt_service import ReceiptService
from app.repositories.receipt_repo import ReceiptRepository
from app.repositories.file_repo import FileAssetRepository
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.services.bill_core_service import BillCoreService
from app.schemas.bill_schemas import BillCreate
from app.services.soliq import validate_soliq_url, SoliqError
from app.queue_manager import queue_manager
from app.dependencies import ensure_self, get_authenticated_user
from app.models import User
from app.services.sse_ticket_service import resource_key, sse_tickets
from app.services.scan_allowance import ScanAllowance, ScanLimitReached

# The scan stream is the one route that cannot carry the identity header,
# so it lives on public_router and authenticates with a ticket instead.
router = APIRouter(
    prefix="/receipts", tags=["receipts"], dependencies=[Depends(get_authenticated_user)]
)
public_router = APIRouter(prefix="/receipts", tags=["receipts"])

def get_receipt_service(session: Session = Depends(get_session)) -> ReceiptService:
    return ReceiptService(ReceiptRepository(session), FileAssetRepository(session))

def get_bill_core_service(session: Session = Depends(get_session)) -> BillCoreService:
    return BillCoreService(BillRepository(session), UserRepository(session))

def get_scan_allowance(session: Session = Depends(get_session)) -> ScanAllowance:
    return ScanAllowance(session)

# The free-scan check counts tasks, and an upload's task is written only after
# its photo is read and squeezed, a second later. Without this, ten uploads sent
# at once all read «one left». A lock per person, dropped when nobody holds it.
# shortcut: in-process, enough for the one uvicorn process; a second replica needs a database lock.
_scan_locks: "weakref.WeakValueDictionary[int, asyncio.Lock]" = weakref.WeakValueDictionary()


def _scan_lock(user_id: int) -> asyncio.Lock:
    lock = _scan_locks.get(user_id)
    if lock is None:
        lock = _scan_locks[user_id] = asyncio.Lock()
    return lock


def ensure_scan_left(allowance: ScanAllowance, user_id: int) -> None:
    """Stop a scan past the day's free ones; the app opens the paywall on this."""
    try:
        allowance.ensure(user_id, datetime.utcnow())
    except ScanLimitReached as reached:
        raise HTTPException(status_code=402, detail={"code": "SCAN_LIMIT", "limit": reached.limit})

@router.post("/upload", response_model=ReceiptTaskResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    user_id: int = Form(None),
    expected_people: int = Form(None),
    payment_details: str = Form(None),
    currency: str = Form(None),
    bill_id: int = Form(None),
    current_user: User = Depends(get_authenticated_user),
    service: ReceiptService = Depends(get_receipt_service),
    core: BillCoreService = Depends(get_bill_core_service),
    allowance: ScanAllowance = Depends(get_scan_allowance),
):
    """Upload a receipt image and create a parsing task.

    The bill is created up front here, so the wizard's headcount/payment/currency
    live on the bill itself; the worker only enriches THIS bill (title, items,
    total) from the parsed receipt. A scan with no user can't own a bill — that
    path stays task-only and the worker fails it.
    """
    # Telegram's in-app browser (especially on Android) often posts photos with
    # a generic/empty content type, so accept by extension / octet-stream too and
    # let the image decoder validate. Only clearly non-image uploads are rejected.
    user_id = ensure_self(current_user, user_id)
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    looks_like_image = (
        content_type.startswith("image/")
        or filename.endswith(
            (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp")
        )
        or content_type in ("", "application/octet-stream", "binary/octet-stream")
    )
    if not looks_like_image:
        raise HTTPException(status_code=400, detail="File must be an image")
    async with _scan_lock(user_id):
        ensure_scan_left(allowance, user_id)

        created_bill_id = None
        if bill_id is not None:
            # Re-scan of an existing bill (owner only, open): the worker replaces this
            # bill's AI-scanned items and keeps the manual ones (STB-207).
            existing = core.bill_repo.get_by_id(bill_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Bill not found")
            if existing.owner_id != user_id:
                raise HTTPException(status_code=403, detail="Only the owner can re-scan a bill")
            if existing.status != BillStatus.OPEN:
                raise HTTPException(status_code=409, detail="Only open bills can be scanned")
        else:
            bill = core.create_bill(
                BillCreate(
                    owner_id=user_id,
                    total_sum=0,
                    expected_people=expected_people,
                    payment_details=payment_details,
                    include_owner=True,
                    currency=currency,
                )
            )
            bill_id = bill.id
            created_bill_id = bill.id

        try:
            task = await service.save_receipt(
                file, user_id, bill_id, owns_bill=created_bill_id is not None
            )
        except Exception:
            if created_bill_id is not None and user_id is not None:
                try:
                    core.discard_provisional_bill(created_bill_id, user_id)
                except Exception:
                    pass
            raise

    # Put task into the internal queue for immediate processing
    await queue_manager.put(task.id)

    return task


@router.post("/upload-qr", response_model=ReceiptTaskResponse)
async def upload_receipt_qr(
    qr_url: str = Form(...),
    user_id: int = Form(None),
    expected_people: int = Form(None),
    payment_details: str = Form(None),
    bill_id: int = Form(None),
    current_user: User = Depends(get_authenticated_user),
    service: ReceiptService = Depends(get_receipt_service),
    core: BillCoreService = Depends(get_bill_core_service),
    allowance: ScanAllowance = Depends(get_scan_allowance),
):
    """Import a bill from an Uzbek fiscal (Soliq) receipt QR.

    `qr_url` is the link the client scanned. It's validated/normalised here (only
    ofd.soliq.uz check links pass — the worker will fetch it, so this is the SSRF
    gate) before the bill is created up front; the worker then reads the items
    from the check page and enriches THIS bill. Soliq receipts are always in
    sum, so the bill is bound to UZS.
    """
    user_id = ensure_self(current_user, user_id)
    try:
        url = validate_soliq_url(qr_url)
    except SoliqError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ensure_scan_left(allowance, user_id)

    # With a bill_id the import ADDS a receipt to an existing bill; without one
    # it creates the bill it will fill.
    created_bill_id = None
    if bill_id is not None:
        existing = core.bill_repo.get_by_id(bill_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Bill not found")
        if existing.owner_id != user_id:
            raise HTTPException(
                status_code=403, detail="Only the owner can add a receipt to a bill"
            )
        if existing.status != BillStatus.OPEN:
            raise HTTPException(status_code=409, detail="Only open bills can be scanned")
    else:
        bill = core.create_bill(
            BillCreate(
                owner_id=user_id,
                total_sum=0,
                expected_people=expected_people,
                payment_details=payment_details,
                include_owner=True,
                currency="uzs",
            )
        )
        bill_id = bill.id
        created_bill_id = bill.id

    task = service.create_qr_task(
        url, user_id, bill_id, owns_bill=created_bill_id is not None
    )
    await queue_manager.put(task.id)
    return task


@router.post("/tasks/{task_id}/cancel", response_model=ReceiptTaskResponse)
def cancel_receipt_task(
    task_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: ReceiptService = Depends(get_receipt_service),
    core: BillCoreService = Depends(get_bill_core_service),
):
    """Cancel a scan that the client gave up on (e.g. a phase timeout).

    A scan that created its own bill takes that still-empty provisional bill
    down with it — a cancelled scan leaves nothing behind. A scan INTO a bill
    that already existed leaves the bill exactly as it was: the receipt is what
    was abandoned, not the table. The worker also bails if it sees CANCELLED /
    the bill gone. A scan that already COMPLETED is left as-is."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the uploader can cancel a scan")
    # Only a scan still being read; one the worker finishes at this moment
    # stays finished — the row decides which of the two came first.
    cancelled = service.repo.session.execute(
        update(ReceiptTask)
        .where(
            ReceiptTask.id == task.id,
            ReceiptTask.status.not_in((ReceiptTaskStatus.COMPLETED, ReceiptTaskStatus.FAILED)),
        )
        .values(status=ReceiptTaskStatus.CANCELLED)
    ).rowcount
    service.repo.session.commit()
    if cancelled and task.owns_bill and task.bill_id and task.user_id:
        try:
            # Also detaches this task from the bill (bill_id → None).
            core.discard_provisional_bill(task.bill_id, task.user_id)
        except Exception:
            pass
    service.repo.session.refresh(task)
    return task

@router.get("/{task_id}/image")
async def get_receipt_image(
    task_id: int,
    current_user: User = Depends(get_authenticated_user),
    service: ReceiptService = Depends(get_receipt_service),
):
    """Get the uploaded receipt image (uploader only)."""
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this receipt")
    
    file_path = service.get_image_path(task.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image file not found")
    
    return FileResponse(file_path)

@public_router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: int, ticket: str | None = None):
    """Stream receipt task status updates.

    Authenticated with a one-shot ticket from POST /api/auth/sse-ticket,
    because EventSource cannot send the identity header.
    """
    user_id = sse_tickets.redeem(ticket, resource_key("receipt_task", task_id))
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired stream ticket")
    with Session(engine) as session:
        task = ReceiptRepository(session).get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to watch this scan")

    async def event_generator():
        last_status = None
        while True:
            # We need a fresh session for each check because worker updates it
            with Session(engine) as session:
                repo = ReceiptRepository(session)
                task = repo.get_task(task_id)
                
                if not task:
                    yield "data: {\"error\": \"Task not found\"}\n\n"
                    break
                
                if task.status != last_status:
                    last_status = task.status
                    data = {
                        "status": task.status,
                        "bill_id": task.bill_id,
                        "error": task.error_message
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                
                if task.status in [
                    ReceiptTaskStatus.COMPLETED,
                    ReceiptTaskStatus.FAILED,
                    ReceiptTaskStatus.CANCELLED,
                ]:
                    break

            # Poll quickly so the short-lived PROCESSING→STRUCTURING transition
            # isn't skipped — otherwise the client never shows the 2nd scan step
            # before the bill is ready (STB-104).
            await asyncio.sleep(0.3)
            
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
