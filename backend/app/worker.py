import base64
from datetime import datetime
import mimetypes
import os
import asyncio
import logging
import json
import time
from sqlalchemy import update
from sqlmodel import Session, select
from app.database import engine
from app.models import (
    ReceiptTask, ReceiptTaskStatus, ReceiptSource, BillItem, BillItemSource,
    FileAsset, ScanMode, SplitType, BillStatus,
)
from app.repositories.receipt_repo import ReceiptRepository
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.utils.currency import to_tiins, from_tiins
from app.services.bill_core_service import BillCoreService
from app.services.bill_item_service import BillItemService
from app.notifier import notifier
from app.services.soliq import (
    fetch_soliq_payment,
    parse_soliq_payment,
    SoliqError,
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from google.cloud import vision
from app.queue_manager import queue_manager
from app.services.scan_report import report_scan
from app.services.product_events import ProductEvent, Surface, capture
from app.services.app_settings import get_receipt_model, get_scan_mode
from app.services.llm import get_openai_client

STORAGE_DIR = "storage/receipts"

# The Vision client is initialized lazily
_vision_client = None

def get_vision_client():
    global _vision_client
    if _vision_client is None:
        # This will check GOOGLE_APPLICATION_CREDENTIALS env var automatically
        _vision_client = vision.ImageAnnotatorClient()
    return _vision_client


# Google Vision answers a receipt in a few seconds; past this it is not coming.
VISION_TIMEOUT_SECONDS = 30


class ScanCancelled(Exception):
    """The uploader gave up on the scan while it was being read."""


def _move_on(session: Session, task: ReceiptTask, status: ReceiptTaskStatus) -> None:
    """Move the scan to its next step, unless it was cancelled meanwhile: a
    plain write would put a cancelled scan back to work, and its receipt would
    land on the bill after all."""
    moved = session.execute(
        update(ReceiptTask)
        .where(ReceiptTask.id == task.id, ReceiptTask.status != ReceiptTaskStatus.CANCELLED)
        .values(status=status)
    ).rowcount
    session.commit()
    if moved != 1:
        raise ScanCancelled()


async def _gpt_structure(
    raw_text: str | None,
    people: int | None,
    image: bytes | None = None,
    image_name: str | None = None,
    *,
    model: str,
) -> tuple[dict, str]:
    """Turn a receipt into the structured receipt dict via the LLM.

    Reads whatever it is given: OCR text, the photo, or both — which one is
    the operator's choice, see ScanMode. Returns (parsed_data, raw_json_response).
    """
    openai_client = get_openai_client()
    people_hint = (
        f"\n\nThe user says this bill is for {people} people. Use this only as a "
        f"plausibility check: the item quantities shouldn't be implausible for {people} "
        "people. If something looks off, re-read the receipt instead of inventing items."
        if people
        else ""
    )
    # Offload to a thread: keeps the event loop free so the status stream can
    # report the STRUCTURING phase live.
    response = await asyncio.to_thread(
        openai_client.chat.completions.create,
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a receipt parsing expert. You turn a receipt — its photo, its "
                    "OCR text, or both — into one structured JSON object, and you re-check your "
                    "own arithmetic before answering."
                ),
            },
            {
                "role": "user",
                "content": _user_content((
                    "Parse this receipt into JSON of the shape "
                    '{"title": string, "place": string|null, "total_sum": number, '
                    '"items": [{"name": string, "count": number, "amount": number, '
                    '"is_shared_globally": boolean}]}.\n\n'
                    "RULES:\n"
                    "1. `amount` is the value in the total/«Сумма» column for that line — the LINE TOTAL "
                    "for the whole quantity (it already equals unit_price × count). Copy it exactly as "
                    "printed; do NOT multiply it by count and do NOT divide it. `count` is the SEPARATE "
                    "«Кол-во»/quantity column — never fold the quantity digit into the price. When OCR "
                    "splits a long name across lines it can drop the quantity and the line total INTO THE "
                    "MIDDLE of the name: e.g. `Чизбургер большой ( Doub 3 204 000 le )` is name "
                    "«Чизбургер большой (Double)», count 3, amount 204000 — NOT count 1 with amount "
                    "3204000 or 320400.\n"
                    "2. `total_sum` is the single final grand total printed at the very bottom (e.g. "
                    "«Итого к оплате», «Total»). Ignore subtotal lines such as «Всего»/«Subtotal» and any "
                    "per-guest running subtotals — never output them as items.\n"
                    "3. `is_shared_globally`: true means this line is 100% shared by every participant "
                    "in the bill. Use true only for bill-level adjustments and charges that definitely "
                    "belong to everyone (e.g. «Hizmet», «Обслуживание», «Service», «Tip», a VAT/tax "
                    "surcharge, a global discount, or another whole-bill line). Shared charges are "
                    "positive; shared discounts are negative. Normal dishes, drinks, products and "
                    "sets are false even when their quantity is >1 or people may later split them "
                    "manually.\n"
                    "4. A DISCOUNT is a line that SUBTRACTS from the bill (e.g. «Скидка», «Chegirma», "
                    "«Discount», «Sale», a «-…%» line, or any amount printed with a minus). Output it as "
                    "one item with a NEGATIVE `amount` and `is_shared_globally`: true when it is a "
                    "bill-level discount.\n"
                    "5. A bare «…%» is NOT automatically a service charge — decide by DIRECTION using the "
                    "totals: if the grand total is SMALLER than the items subtotal, that percent line is a "
                    "DISCOUNT (negative `amount`); if it is LARGER, it is a SERVICE/VAT CHARGE "
                    "(positive `amount`). E.g. subtotal 392 000 but total 313 600 ⇒ a −78 400 "
                    "discount, even when the receipt prints «20%» without a minus sign.\n"
                    "6. A VAT / sales-tax line (e.g. «ҚҚС», «QQS», «НДС», «VAT», a «…12%» tax) can be "
                    "either informational or a real bill-level adjustment. If the receipt says it is "
                    "included in prices, or the items already add up to the printed grand total, treat "
                    "it as informational: do not output it as an item and never add it on top. But if it "
                    "is printed as an add-on/surcharge/«Надбавка» with its own amount and the grand "
                    "total is larger than the items subtotal by that amount, output it as one POSITIVE "
                    "item with `is_shared_globally`: true. Example: «Полная сумма 1 530 000; "
                    "Надбавка \"НДС 12%\" (+12%) +183 600; ИТОГО К ОПЛАТЕ 1 713 600» means output a "
                    "separate item named «Надбавка НДС 12%» with amount 183600 and "
                    "`is_shared_globally`: true.\n"
                    "7. Each physical dish appears EXACTLY ONCE. Merge duplicates and per-guest split "
                    "annotations into one line. A line is an item only if it has its own amount in the "
                    "«Сумма» column. Set/combo components listed (indented) under a SET have no own price — "
                    "never output them and never copy the parent's price onto them.\n"
                    "8. DO NOT translate names — keep them exactly as printed (Russian/Uzbek/etc.); only fix "
                    "obvious OCR gibberish.\n"
                    "8a. `place` is the venue's name as guests know it — the brand printed on the receipt, "
                    "without the legal form, branch or address («CAFFEINE Ц-1 ООО» → «Caffeine»); null when "
                    "the receipt does not name the venue.\n"
                    "9. Amounts are in Uzbek sum: a real dish can't cost a few units. An implausibly tiny "
                    "amount (e.g. 5 among thousands) is an OCR error with missing trailing digits — correct "
                    "it from context.\n"
                    "10. SELF-CHECK before answering: add up every item `amount` with its sign (service "
                    "or tax charge added, discount subtracted); the result MUST equal `total_sum`. If it "
                    "does not, you mis-read something (a quantity, a line total taken as per-unit, a "
                    "service/tax charge or discount SIGN, or an extra/missing line) — fix the items and "
                    "re-check until they reconcile. A discount must make the sum go DOWN to match a "
                    "total that is below the subtotal."
                    f"{people_hint}"
                    f"{_source_note(raw_text, image)}"
                ), image, image_name),
            },
        ],
        response_format={"type": "json_object"}
    )
    raw = response.choices[0].message.content
    return json.loads(raw), raw


def _user_content(prompt: str, image: bytes | None, image_name: str | None = None):
    """A plain string, or the prompt and the photo side by side."""
    if image is None:
        return prompt
    return [{"type": "text", "text": prompt}, _image_content(image, image_name)]


def _source_note(raw_text: str | None, image: bytes | None) -> str:
    """What the model is looking at, said in the prompt.

    With both, the photo is the document and the text is a second opinion on the
    characters — saying so is the difference between the model using the text to
    settle a doubtful digit and it trusting a line OCR ran together.
    """
    if raw_text and image:
        return (
            "\n\nYou are given the photo of this receipt AND the OCR text read from it. "
            "The photo is the document: read the layout from it. Use the OCR text only to "
            "confirm characters you are unsure of, and prefer the photo when the two "
            f"disagree about structure.\n\nOCR TEXT:\n{raw_text}"
        )
    if raw_text:
        return f"\n\nRAW TEXT:\n{raw_text}"
    return "\n\nThe receipt is attached as a photo. Read it directly."


def _image_content(image: bytes, filename: str | None = None) -> dict:
    encoded = base64.b64encode(image).decode()
    # The upload path normalises what it can read to JPEG; anything it could
    # not is stored as-is, and a wrong label is one more reason for the model
    # to refuse it.
    mime = mimetypes.guess_type(filename or "")[0] if filename else None
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}


async def _structure_from_photo(session, repo, task, bill) -> dict:
    """Photo path. Which reader and which model are used are operator settings
    — see ScanMode.

    Both are recorded on the task before anything is called: comparing them on
    real receipts is the reason they can be switched, and a scan whose reader is
    unknown is a scan that can't be counted.
    """
    mode = get_scan_mode(session)
    model = get_receipt_model(session)
    task.scan_mode = mode.value
    task.llm_model = model
    session.add(task)
    session.commit()

    with open(os.path.join(STORAGE_DIR, task.filename), "rb") as image_file:
        image_bytes = image_file.read()

    full_text = None
    if mode == ScanMode.OCR_LLM:
        full_text = await _run_ocr(task, image_bytes)
    elif mode == ScanMode.HYBRID:
        # The text is a second opinion here, not the document: a photo OCR
        # reads nothing from is still a photo the model can read.
        try:
            full_text = await _run_ocr(task, image_bytes)
        except Exception as exc:
            logger.warning(f"Task {task.id}: OCR found nothing, reading the photo alone: {exc}")

    # Whatever came before, the model is the second step the client is waiting
    # on — so the indicator moves on before the slow call, not after it.
    _move_on(session, task, ReceiptTaskStatus.STRUCTURING)

    logger.info(f"Calling {model} to structure task {task.id} in {mode.value} mode")
    openai_start_time = time.time()
    data, raw_gpt_response = await _gpt_structure(
        full_text,
        bill.expected_people,
        image=image_bytes if mode in (ScanMode.VISION, ScanMode.HYBRID) else None,
        image_name=task.filename,
        model=model,
    )
    logger.info(f"OpenAI structuring successful for task {task.id} (took {time.time() - openai_start_time:.2f}s)")

    # Persist the raw LLM output right away (STB-69) BEFORE any session.refresh —
    # refresh reloads the row and would discard an un-committed value.
    task.llm_response = raw_gpt_response
    session.add(task)
    session.commit()
    return data


async def _run_ocr(task, image_bytes: bytes) -> str:
    """Google Vision over the stored photo. Raises when it reads nothing."""
    logger.info(f"Calling Google Cloud Vision for task {task.id}")
    image = vision.Image(content=image_bytes)
    vision_client = get_vision_client()

    vision_start_time = time.time()
    # Offload the blocking SDK call to a worker thread so the asyncio event loop
    # stays free; otherwise the status-stream coroutine can't poll and the client
    # never sees the PROCESSING→STRUCTURING transition.
    response_vision = await asyncio.to_thread(vision_client.text_detection, image=image, timeout=VISION_TIMEOUT_SECONDS)
    vision_duration = time.time() - vision_start_time

    texts = response_vision.text_annotations
    if not texts:
        raise Exception("No text found on the receipt by Google Vision")

    task.ocr_text = texts[0].description  # persist raw OCR for debugging (STB-69)
    logger.info(f"Google Vision OCR successful for task {task.id} (took {vision_duration:.2f}s)")
    return task.ocr_text


async def _structure_from_soliq(session, repo, task, bill) -> dict:
    """Soliq QR path: call the check's JSON API and map items from its response.

    Soliq's check page is now a client-side SPA that loads the receipt from a
    JSON endpoint, so we call that endpoint directly (see app.services.soliq).
    The response is already structured — there is no LLM step here; an empty or
    unreadable receipt fails cleanly so the caller drops the provisional bill.
    """
    logger.info(f"Fetching Soliq receipt for task {task.id}")
    payment = await fetch_soliq_payment(task.source_url)

    # Fetched → structuring phase (keeps the two-step client indicator working).
    _move_on(session, task, ReceiptTaskStatus.STRUCTURING)

    data = parse_soliq_payment(payment)
    if not data["items"]:
        raise SoliqError("Soliq receipt has no items")

    logger.info(f"Task {task.id}: parsed {len(data['items'])} items from Soliq API")
    # `llm_response` doubles as the raw-parse debug column for both paths.
    task.llm_response = json.dumps(data, ensure_ascii=False)
    session.add(task)
    session.commit()
    return data


def _enrich_bill(session, bill_repo, user_repo, task, bill, data: dict) -> None:
    """Fill the (already created) bill from a parsed receipt dict and complete
    the task. Only this scan's own items are replaced — hand-added items and the
    other receipts on the bill are left alone. Identical for photo and Soliq.

    One transaction under the bill's lock, held to the rule hand edits follow: a
    share somebody already paid stays as it was. A new receipt's shared lines
    (service, a discount) would otherwise raise it after the money moved."""
    locked = bill_repo.get_by_id_for_update(bill.id)
    if locked is None or locked.status == BillStatus.CLOSED:
        # Closed while the receipt was read: its lines must not land on it.
        raise Exception("The bill was closed while its receipt was being read")
    items = BillItemService(bill_repo, user_repo)
    paid_before = items._paid_allocations(bill.id)
    total_sum_val = data.get("total_sum", 0)
    if not isinstance(total_sum_val, (int, float)):
        total_sum_val = 0
    # Name an as-yet-untitled bill from the scan, but never clobber a title the
    # user already set (re-scan).
    if not bill.title:
        bill.title = data.get("title") or "Parsed Receipt"
    # The receipt may say where the bill was; the labeling job reads it from the
    # stored response — unless the owner has already said.
    if not bill.place_by_owner:
        bill.place_checked_at = None

    # Replace only THIS scan's items. A bill can hold several receipts, so
    # wiping every scanned item would delete the other receipts' contents on
    # every re-scan. Items with no task at all are the legacy pre-multi-receipt
    # rows and belong to the first scan.
    for existing in bill_repo.get_items_by_bill_id(bill.id):
        belongs_to_this_scan = existing.receipt_task_id == task.id
        legacy_scanned = (
            existing.receipt_task_id is None
            and existing.source == BillItemSource.AI
        )
        if belongs_to_this_scan or legacy_scanned:
            session.delete(existing)

    calculated_total_tiins = 0
    for item_data in data.get("items", []):
        # `amount` is the whole-line total (qty already included). Older
        # responses used `price` the same way — fall back to it.
        amount_val = item_data.get("amount")
        if amount_val is None:
            amount_val = item_data.get("price", 0)
        if not isinstance(amount_val, (int, float)):
            amount_val = 0

        try:
            count = int(item_data.get("count", 1))
        except (TypeError, ValueError):
            count = 1
        if count < 1:
            count = 1

        # Do NOT multiply by count — the amount is already the line total.
        item_sum_tiins = to_tiins(amount_val)
        # `is_service_fee` is the legacy name accepted while old workers/prompts
        # drain out. The domain flag is whether the line belongs to everyone.
        shared_value = item_data.get("is_shared_globally")
        if shared_value is None:
            shared_value = item_data.get("is_service_fee", False)
        is_shared = shared_value is True or item_sum_tiins < 0

        item = BillItem(
            bill_id=bill.id,
            name=item_data.get("name", "Unknown Item"),
            price=item_sum_tiins // count,  # per-unit, for display
            count=count,
            item_sum=item_sum_tiins,
            is_shared_globally=is_shared,
            source=BillItemSource.AI,
            receipt_task_id=task.id,
        )
        session.add(item)
        calculated_total_tiins += item_sum_tiins

    # Surface parse inconsistencies: if the printed grand total doesn't match the
    # sum of items, a line was likely mis-parsed. We still rely on the item sum.
    parsed_total_tiins = to_tiins(total_sum_val)
    if parsed_total_tiins and parsed_total_tiins != calculated_total_tiins:
        logger.warning(
            f"Task {task.id}: grand total ({from_tiins(parsed_total_tiins)}) "
            f"!= sum of parsed items ({from_tiins(calculated_total_tiins)}) "
            f"— likely a mis-parsed or duplicated line."
        )

    # Total is the sum of ALL items — the kept manual ones plus the freshly
    # scanned ones — so the split logic holds for a first scan and a re-scan alike.
    session.flush()
    all_items = bill_repo.get_items_by_bill_id(bill.id)
    bill.total_sum = sum(i.item_sum for i in all_items)
    bill.unallocated_sum = bill.total_sum
    # A bill with items defaults to items-first split (people take dishes).
    if all_items:
        bill.split_type = SplitType.BY_ITEMS
    bill_repo.session.add(bill)

    # Done only if not cancelled in the meantime; a cancel arriving now waits
    # for this row and then finds the scan done.
    completed = session.execute(
        update(ReceiptTask)
        .where(ReceiptTask.id == task.id, ReceiptTask.status != ReceiptTaskStatus.CANCELLED)
        .values(status=ReceiptTaskStatus.COMPLETED, bill_id=bill.id)
    ).rowcount
    if completed != 1:
        raise ScanCancelled()

    # Re-derive per-person allocations (assignments survive on the kept manual
    # items) and the unallocated remainder, then nudge any open viewers.
    if all_items:
        items.recalculate_by_items(bill.id, commit=False)
    items._ensure_paid_allocations_unchanged(bill.id, paid_before)
    session.commit()
    notifier.broadcast(bill.id, "REFRESH")
    report_scan(session, task, bill)
    logger.info(f"Task {task.id} completed successfully. Bill ID: {bill.id}")


async def process_task(task_id: int):
    with Session(engine) as session:
        repo = ReceiptRepository(session)
        bill_repo = BillRepository(session)
        user_repo = UserRepository(session)

        task = repo.get_task(task_id)
        if not task:
            return

        try:
            _move_on(session, task, ReceiptTaskStatus.PROCESSING)
            if not task.user_id:
                raise Exception("User not found for this task")

            # The bill was created up front (with headcount/payment/currency) when
            # the scan was uploaded; the worker only enriches THIS bill.
            bill = bill_repo.get_by_id(task.bill_id) if task.bill_id else None
            if not bill:
                raise Exception("No bill associated with this scan task")

            # Produce the structured receipt dict from whichever source this task
            # uses — both branches return the same shape.
            if task.source == ReceiptSource.SOLIQ_QR:
                data = await _structure_from_soliq(session, repo, task, bill)
            else:
                data = await _structure_from_photo(session, repo, task, bill)

            logger.info(f"Parsed receipt data for task {task_id}: {data}")

            # The client may have cancelled (e.g. its 20s timeout) while we were
            # structuring — the cancel endpoint deletes the provisional bill, so
            # re-read and bail if cancelled / the bill is gone (STB-87).
            session.refresh(task)
            if task.status == ReceiptTaskStatus.CANCELLED:
                raise ScanCancelled()
            bill = bill_repo.get_by_id(task.bill_id) if task.bill_id else None
            if not bill:
                logger.info(f"Task {task_id}: bill is gone — skipping enrichment")
                return

            _enrich_bill(session, bill_repo, user_repo, task, bill, data)

        except ScanCancelled:
            session.rollback()
            logger.info(f"Task {task_id} was cancelled — skipping enrichment")
        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}")
            session.rollback()
            task = repo.get_task(task_id)
            if task:
                # A failed scan must leave nothing behind, so drop the empty
                # provisional bill (otherwise retries pile up empty bills).
                bill_id, owner_id, owns_bill = task.bill_id, task.user_id, task.owns_bill
                task.status = ReceiptTaskStatus.FAILED
                task.error_message = str(e)
                task.bill_id = None
                session.add(task)

                # A failed attempt must not replace the visible receipt with its
                # unusable upload or leave storage behind.
                for asset in session.exec(
                    select(FileAsset).where(FileAsset.receipt_task_id == task.id)
                ).all():
                    try:
                        if asset.path and os.path.exists(asset.path):
                            os.remove(asset.path)
                    except OSError:
                        pass
                    session.delete(asset)
                session.commit()
                if bill_id and owner_id:
                    # A failed FIRST scan must leave nothing behind, so drop the
                    # still-empty provisional bill it created. A scan INTO a
                    # bill that already existed keeps it intact and just lets
                    # any open viewers know nothing changed.
                    if owns_bill:
                        try:
                            BillCoreService(bill_repo, user_repo).discard_provisional_bill(bill_id, owner_id)
                        except Exception:
                            pass
                    else:
                        notifier.broadcast(bill_id, "REFRESH")
                _count_chat_scan(task, bill_id, ok=False)
        else:
            _count_chat_scan(task, bill.id, ok=True)


def _count_chat_scan(task: ReceiptTask, bill_id: int | None, ok: bool) -> None:
    """The Mini App counts how its own scans end. A photo sent to the bot, for
    the bill its wizard has just made, ends only here."""
    if not task.notify_chat_id or not task.user_id:
        return
    capture(
        task.user_id,
        ProductEvent.RECEIPT_SCAN_RESULT,
        Surface.BOT,
        mode="photo",
        target="new_bill",
        bill_id=bill_id,
        ok=ok,
        **({} if ok else {"reason": ReceiptTaskStatus.FAILED.value}),
    )


# Scans handled at once. Each waits mostly on OCR and the model, 10–30 s, and
# the app gives up after 90 s: one at a time, the fourth person scanning at
# dinner was cancelled before the worker even reached them.
CONCURRENT_SCANS = 3


async def worker_loop():
    logger.info("Worker started. Picking up unfinished tasks...")
    try:
        with Session(engine) as session:
            for task in ReceiptRepository(session).get_unfinished_tasks(datetime.utcnow()):
                await queue_manager.put(task.id)
    except Exception as e:
        logger.error(f"Error loading unfinished tasks on startup: {e}")

    slots = asyncio.Semaphore(CONCURRENT_SCANS)
    running: set[asyncio.Task] = set()

    async def handle(task_id: int) -> None:
        try:
            await process_task(task_id)
        except Exception as e:
            logger.error(f"Worker queue error: {e}")
        finally:
            slots.release()
            queue_manager.task_done()

    while True:
        # A slot first, so no task leaves the queue before it can start.
        await slots.acquire()
        task_id = await queue_manager.get()
        logger.info(f"Processing task {task_id} from internal queue")
        job = asyncio.create_task(handle(task_id))
        running.add(job)
        job.add_done_callback(running.discard)

if __name__ == "__main__":
    asyncio.run(worker_loop())
