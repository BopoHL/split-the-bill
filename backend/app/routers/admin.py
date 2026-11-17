"""Admin panel API.

Read-only over the app's data plus the broadcast controls. Deliberately does NOT
expose saved payment details: they are encrypted at rest precisely so that a
compromised admin session can't hand out everyone's card numbers, and no screen
needs them.
"""
import asyncio
import contextlib
import ipaddress
import os
import tempfile
import uuid
from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import and_, func
from sqlmodel import Session, select

from app.database import get_session
from app.jobs import broadcast_sender
from app.models import (
    Bill,
    BillItem,
    BillStatus,
    BillUser,
    Broadcast,
    BroadcastDelivery,
    BroadcastFormat,
    BroadcastStatus,
    Feedback,
    FileAsset,
    PaymentReminder,
    ReceiptSource,
    ReceiptTask,
    ReceiptTaskStatus,
    ScanMode,
    User,
)
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.schemas.admin_schemas import (
    AdminBillDetail,
    AdminBillsPage,
    AdminBillRow,
    AdminFeedbackPage,
    AdminFeedbackRow,
    AdminLogin,
    AdminReminderRow,
    AdminRemindersPage,
    AdminScanDetail,
    AdminScanItem,
    AdminScanModeStat,
    AdminScanRow,
    AdminSettings,
    AdminSettingsUpdate,
    AdminStats,
    AdminUserDetail,
    AdminUserSettingsUpdate,
    AdminUsersPage,
    AdminUserRow,
    BroadcastCreate,
    BroadcastDeliveriesPage,
    BroadcastDetail,
    BroadcastMedia,
    BroadcastRecipient,
    BroadcastRow,
    BroadcastTest,
    BroadcastTestResult,
)
from app.services.app_settings import (
    LABEL_MODEL_KEY,
    RECEIPT_MODEL_KEY,
    SCAN_MODE_KEY,
    SUPPORT_USERNAME_KEY,
    get_label_model,
    get_receipt_model,
    get_scan_mode,
    get_support_username,
    normalize_telegram_username,
    set_setting,
)
from app.services import broadcast_media
from app.services.llm import model_exists
from app.services.product_events import set_person
from app.services.bill_core_service import BillCoreService
from app.utils.admin_auth import (
    COOKIE_NAME,
    TOKEN_TTL_SECONDS,
    check_credentials,
    issue_token,
    require_admin,
)
from app.utils.currency import from_tiins, normalize_currency
from app.utils.images import compress_image
from app.utils.local_time import naive_utc
from app.utils.scan_check import reconcile_scan_many
from app.utils.telegram import largest_photo_file_id, mini_app_link
from app.utils.telegram_html import (
    CAPTION_LIMIT,
    RICH_TEXT_LIMIT,
    TelegramHtmlError,
    rich_visible_length,
    visible_length,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# A crude in-process limiter — enough to make guessing the single operator
# password impractical without dragging in Redis. Counted per /64 for IPv6, a
# single customer's block, with a ceiling for everyone together: addresses are
# cheap, and clearing the table when it filled up gave every guesser a new start.
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
MAX_FAILURES = 50
ATTEMPT_WINDOW_SECONDS = 15 * 60

BROADCAST_PHOTO_DIR = "storage/broadcasts"
# Bills listed on a user's page.
USER_DETAIL_BILLS = 50

# The guided tour's walkthrough bills say nothing about how the app is used.
REAL_BILL = Bill.is_demo.is_(False)


def _client_ip(request: Request) -> str:
    """Who is knocking. `request.client` is nginx, the same for everybody, so
    one stranger's guesses locked the operator out; nginx overwrites X-Real-IP
    with the address it saw, and the backend has no port of its own."""
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _guesser(ip: str) -> str:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    return str(ipaddress.ip_network(f"{ip}/64", strict=False)) if address.version == 6 else ip


def _rate_limit(ip: str, now: float) -> None:
    for key in list(_LOGIN_ATTEMPTS):
        fresh = [t for t in _LOGIN_ATTEMPTS[key] if now - t < ATTEMPT_WINDOW_SECONDS]
        if fresh:
            _LOGIN_ATTEMPTS[key] = fresh
        else:
            del _LOGIN_ATTEMPTS[key]
    mine = len(_LOGIN_ATTEMPTS.get(_guesser(ip), []))
    everyone = sum(map(len, _LOGIN_ATTEMPTS.values()))
    if mine >= MAX_ATTEMPTS or everyone >= MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Too many attempts")


def _note_failure(ip: str, now: float) -> None:
    _LOGIN_ATTEMPTS.setdefault(_guesser(ip), []).append(now)


@router.post("/auth/login")
def login(data: AdminLogin, request: Request, response: Response):
    ip, now = _client_ip(request), datetime.utcnow().timestamp()
    _rate_limit(ip, now)
    if not check_credentials(data.email, data.password):
        _note_failure(ip, now)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = issue_token(data.email)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        secure=os.getenv("ENV") == "production",
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(session_data: dict = Depends(require_admin)):
    return {"email": session_data.get("sub")}


@router.get("/stats", response_model=AdminStats)
def stats(session: Session = Depends(get_session), _=Depends(require_admin)):
    def count(model, *where):
        return session.exec(select(func.count(model.id)).where(*where)).one()

    week_ago = datetime.utcnow() - timedelta(days=7)
    live = and_(REAL_BILL, Bill.deleted_at.is_(None))

    total_sum = session.exec(
        select(func.coalesce(func.sum(Bill.total_sum), 0)).where(live)
    ).one()
    bills_total = count(Bill, live)

    return AdminStats(
        users_total=count(User),
        users_new_7d=count(User, User.created_at >= week_ago),
        bills_total=bills_total,
        bills_open=count(Bill, live, Bill.status == BillStatus.OPEN),
        bills_closed=count(Bill, live, Bill.status == BillStatus.CLOSED),
        bills_deleted=count(Bill, REAL_BILL, Bill.deleted_at.is_not(None)),
        scans_total=count(ReceiptTask),
        scans_failed=count(ReceiptTask, ReceiptTask.status == ReceiptTaskStatus.FAILED),
        average_bill=from_tiins(int(total_sum / bills_total)) if bills_total else 0.0,
    )


def _user_label(user: User | None) -> str | None:
    if user is None:
        return None
    return user.username or user.name or str(user.telegram_id)


def _count_by(session: Session, column, ids: list[int], *where) -> dict[int, int]:
    """How many rows each id has, in one grouped query for the whole page —
    counting per row made a page of 200 bills about 800 queries."""
    if not ids:
        return {}
    return dict(session.exec(
        select(column, func.count()).where(column.in_(ids), *where).group_by(column)
    ).all())


def _bill_rows(session: Session, bills: list[Bill]) -> list[AdminBillRow]:
    ids = [bill.id for bill in bills]
    seats = _count_by(session, BillUser.bill_id, ids)
    items = _count_by(session, BillItem.bill_id, ids)
    receipts = _count_by(session, ReceiptTask.bill_id, ids)
    owner_ids = {bill.owner_id for bill in bills}
    owners = {
        user.id: user for user in session.exec(select(User).where(User.id.in_(owner_ids))).all()
    } if owner_ids else {}
    return [
        AdminBillRow(
            id=bill.id,
            title=bill.title,
            owner_id=bill.owner_id,
            owner=_user_label(owners.get(bill.owner_id)),
            status=bill.status,
            currency=bill.currency,
            total_sum=from_tiins(bill.total_sum),
            participants_count=seats.get(bill.id, 0),
            items_count=items.get(bill.id, 0),
            receipts_count=receipts.get(bill.id, 0),
            is_deleted=bill.deleted_at is not None,
            created_at=bill.created_at,
        )
        for bill in bills
    ]


def _user_rows(session: Session, users: list[User]) -> list[AdminUserRow]:
    ids = [user.id for user in users]
    owned = _count_by(session, Bill.owner_id, ids, REAL_BILL)
    joined = dict(session.exec(
        select(BillUser.user_id, func.count(BillUser.id))
        .join(Bill, Bill.id == BillUser.bill_id)
        .where(BillUser.user_id.in_(ids), Bill.owner_id != BillUser.user_id, REAL_BILL)
        .group_by(BillUser.user_id)
    ).all()) if ids else {}
    rows = []
    for user in users:
        settings = user.settings or {}
        rows.append(AdminUserRow(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            name=user.name,
            surname=user.surname,
            avatar_url=user.avatar_url,
            language=settings.get("language"),
            currency=settings.get("currency"),
            onboarding_completed=bool(settings.get("onboarding_completed")),
            bot_blocked=bool(settings.get("bot_blocked")),
            bills_count=owned.get(user.id, 0),
            participant_bills_count=joined.get(user.id, 0),
            created_at=user.created_at,
        ))
    return rows


@router.get("/bills", response_model=AdminBillsPage)
def list_bills(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_deleted: bool = False,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    conditions = [REAL_BILL]
    if not include_deleted:
        conditions.append(Bill.deleted_at.is_(None))

    total = session.exec(select(func.count(Bill.id)).where(*conditions)).one()
    query = (
        select(Bill)
        .where(*conditions)
        .order_by(Bill.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    return AdminBillsPage(
        items=_bill_rows(session, session.exec(query).all()),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/bills/{bill_id}/restore", response_model=AdminBillRow)
def restore_bill(
    bill_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Undo a soft delete — the only place this is possible."""
    service = BillCoreService(BillRepository(session), UserRepository(session))
    bill = service.restore_bill(bill_id)
    return _bill_rows(session, [bill])[0]


@router.get("/bills/{bill_id}", response_model=AdminBillDetail)
def bill_detail(
    bill_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    bill = BillRepository(session).get_by_id_including_deleted(bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    detail = BillCoreService(
        BillRepository(session), UserRepository(session)
    ).get_bill_details(bill_id, include_deleted=True)
    owner = session.get(User, bill.owner_id)
    data = detail.model_dump(exclude={"payment_details", "public_token"})
    return AdminBillDetail(
        **data,
        owner=_user_label(owner),
        is_deleted=bill.deleted_at is not None,
        deleted_at=bill.deleted_at,
    )


@router.get("/bills/{bill_id}/receipts/{task_id}/photo")
def bill_receipt_photo(
    bill_id: int,
    task_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Receipt photo inside a bill detail, gated by the admin session."""
    bill = BillRepository(session).get_by_id_including_deleted(bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    asset = session.exec(
        select(FileAsset).where(
            FileAsset.bill_id == bill_id,
            FileAsset.receipt_task_id == task_id,
        )
    ).first()
    if not asset or not os.path.exists(asset.path):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(asset.path, media_type=asset.mime_type)


@router.get("/users", response_model=AdminUsersPage)
def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    total = session.exec(select(func.count(User.id))).one()
    users = session.exec(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return AdminUsersPage(
        items=_user_rows(session, users),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/feedback", response_model=AdminFeedbackPage)
def list_feedback(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """What people sent from the app's feedback form, newest first."""
    total = session.exec(select(func.count(Feedback.id))).one()
    rows = session.exec(
        select(Feedback, User)
        .outerjoin(User, User.id == Feedback.user_id)
        .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return AdminFeedbackPage(
        items=[
            AdminFeedbackRow(
                id=feedback.id,
                message=feedback.message,
                name=feedback.name,
                created_at=feedback.created_at,
                user_id=feedback.user_id,
                user=_user_label(user),
                telegram_id=user.telegram_id if user else None,
            )
            for feedback, user in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def user_detail(
    user_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_detail(session, user)


def _user_detail(session: Session, user: User) -> AdminUserDetail:
    user_id = user.id
    # The newest ones; the counts in the row say how many there are in all.
    owned_bills = session.exec(
        select(Bill).where(Bill.owner_id == user_id, REAL_BILL)
        .order_by(Bill.created_at.desc()).limit(USER_DETAIL_BILLS)
    ).all()
    participant_bills = session.exec(
        select(Bill)
        .join(BillUser, BillUser.bill_id == Bill.id)
        .where(BillUser.user_id == user_id, Bill.owner_id != user_id, REAL_BILL)
        .order_by(Bill.created_at.desc()).limit(USER_DETAIL_BILLS)
    ).all()

    return AdminUserDetail(
        **_user_rows(session, [user])[0].model_dump(),
        settings=user.settings or {},
        owned_bills=_bill_rows(session, owned_bills),
        participant_bills=_bill_rows(session, participant_bills),
    )


@router.put("/users/{user_id}/settings", response_model=AdminUserDetail)
def update_user_settings(
    user_id: int,
    payload: AdminUserSettingsUpdate,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Change someone's settings by hand — to replay the onboarding for them, or
    to put a language right. Keys nobody sent are left as they are."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.currency is not None and normalize_currency(payload.currency) is None:
        raise HTTPException(status_code=400, detail="Unknown currency")

    settings = dict(user.settings or {})
    for key in payload.model_fields_set:
        value = getattr(payload, key)
        if value is None:
            settings.pop(key, None)
        else:
            settings[key] = normalize_currency(value) if key == "currency" else value
    user.settings = settings
    session.add(user)
    session.commit()
    if "internal" in payload.model_fields_set:
        set_person(user.id, internal=bool(payload.internal))
    return _user_detail(session, user)


def _broadcast_row(broadcast: Broadcast) -> BroadcastRow:
    """`has_photo` rather than the path: the panel only needs to know whether a
    picture is attached, and where it sits on disk is nobody's business."""
    return BroadcastRow(
        **broadcast.model_dump(exclude={"photo_path", "photo_file_id"}),
        has_photo=bool(broadcast.photo_path),
    )


@router.get("/broadcasts", response_model=list[BroadcastRow])
def list_broadcasts(session: Session = Depends(get_session), _=Depends(require_admin)):
    return [
        _broadcast_row(broadcast)
        for broadcast in session.exec(select(Broadcast).order_by(Broadcast.id.desc())).all()
    ]


def _resolve_targets(session: Session, targets: list[str]) -> list[int]:
    """Turn what the operator typed into user ids.

    Usernames and telegram ids are resolved now, at creation, rather than at
    send time: a username can change between the two, and a message meant for
    one person would then go to whoever holds the handle.
    """
    resolved: list[int] = []
    unknown: list[str] = []

    for raw in targets:
        needle = raw.strip().lstrip("@")
        if not needle:
            continue

        user = None
        if needle.isdigit():
            user = session.exec(
                select(User).where(User.telegram_id == int(needle))
            ).first()
        if user is None:
            user = session.exec(
                select(User).where(func.lower(User.username) == needle.lower())
            ).first()

        if user is None:
            unknown.append(raw)
        elif user.id not in resolved:
            resolved.append(user.id)

    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNKNOWN_RECIPIENTS", "targets": unknown},
        )
    return resolved


def _default_button_url() -> str:
    return mini_app_link()


def _check_body(message_format: str, body: dict[str, str]) -> None:
    """Refuse here what Telegram would refuse for every recipient: broken
    markup, and a rich message over its own limit."""
    if not any(text.strip() for text in body.values()):
        raise HTTPException(status_code=400, detail="Message body is empty")
    rich = message_format == BroadcastFormat.RICH
    for language, text in body.items():
        try:
            length = rich_visible_length(text) if rich else visible_length(text)
        except TelegramHtmlError as error:
            raise HTTPException(
                status_code=400,
                detail={"code": "BAD_HTML", "language": language, "message": str(error)},
            )
        if rich and length > RICH_TEXT_LIMIT:
            raise HTTPException(
                status_code=400,
                detail={"code": "TEXT_TOO_LONG", "language": language, "limit": RICH_TEXT_LIMIT, "length": length},
            )


def _button(with_button: bool, text: str | None, url: str | None) -> tuple[str | None, str | None]:
    """An empty label or link falls back to «open the bot» rather than silently
    dropping the button."""
    if not with_button:
        return None, None
    return (text or "").strip() or "Открыть", (url or "").strip() or _default_button_url()


@router.post("/broadcasts", response_model=BroadcastRow, status_code=201)
def create_broadcast(
    data: BroadcastCreate,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    _check_body(data.format, data.body)
    target_user_ids: list[int] = []
    if data.audience == "selected":
        target_user_ids = _resolve_targets(session, data.targets)
        if not target_user_ids:
            raise HTTPException(status_code=400, detail="No recipients selected")

    # Everything downstream compares against `datetime.utcnow()`, which is
    # naive UTC — so an aware instant is normalised here rather than left to
    # collide with it later.
    scheduled_at = naive_utc(data.scheduled_at) if data.scheduled_at else None

    button_text, button_url = _button(data.with_button, data.button_text, data.button_url)
    broadcast = Broadcast(
        title=data.title,
        format=data.format,
        body=data.body,
        parse_mode="HTML",
        audience=data.audience,
        target_user_ids=target_user_ids,
        scheduled_at=scheduled_at,
        button_text=button_text,
        button_url=button_url,
    )
    session.add(broadcast)
    session.commit()
    session.refresh(broadcast)
    return _broadcast_row(broadcast)


def _longest_body(body: dict[str, str]) -> int:
    """Measured the way Telegram measures: markup doesn't count towards the
    limit, and the unit is UTF-16 code units, so an emoji costs two."""
    return max((visible_length(text or "") for text in body.values()), default=0)


def _assert_caption_fits(body: dict[str, str]) -> None:
    """A photo shrinks the room for text, so the check belongs wherever the two
    are put together — attaching a picture, queueing a broadcast and a test send
    all land here rather than letting Telegram reject it one recipient at a time."""
    longest = _longest_body(body)
    if longest > CAPTION_LIMIT:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CAPTION_TOO_LONG",
                "limit": CAPTION_LIMIT,
                "length": longest,
            },
        )


@router.post("/broadcasts/{broadcast_id}/photo", response_model=BroadcastRow)
async def attach_broadcast_photo(
    broadcast_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    broadcast = session.get(Broadcast, broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Broadcast already started")
    if broadcast.format == BroadcastFormat.RICH:
        raise HTTPException(
            status_code=409,
            detail={"code": "RICH_PICTURES_INLINE", "message": "У rich-рассылки картинки — внутри текста"},
        )
    _assert_caption_fits(broadcast.body or {})

    # The declared content type is whatever the sender chose to claim. Decoding
    # the bytes is the actual proof, and re-encoding caps the size — a file
    # Telegram refuses would otherwise fail once per recipient.
    # Off the event loop: re-encoding a photo stalls every request meanwhile.
    compressed = await asyncio.to_thread(compress_image, await file.read())
    if compressed is None:
        raise HTTPException(status_code=400, detail="File is not a readable image")
    data, extension, _mime = compressed

    os.makedirs(BROADCAST_PHOTO_DIR, exist_ok=True)
    path = os.path.join(BROADCAST_PHOTO_DIR, f"{uuid.uuid4()}{extension}")
    with open(path, "wb") as handle:
        handle.write(data)

    previous = broadcast.photo_path
    broadcast.photo_path = path
    # The cached handle belongs to the previous picture; keeping it would send
    # the old one to everybody.
    broadcast.photo_file_id = None
    session.add(broadcast)
    try:
        session.commit()
    except Exception:
        os.remove(path)  # nothing points at it now
        raise
    session.refresh(broadcast)

    if previous and previous != path:
        # Nothing else refers to it, and the purge job only knows about receipts.
        with contextlib.suppress(OSError):
            os.remove(previous)
    return _broadcast_row(broadcast)


def _stored_test_photo(raw: bytes) -> str:
    compressed = compress_image(raw)
    if compressed is None:
        raise HTTPException(status_code=400, detail="File is not a readable image")
    data, extension, _mime = compressed
    with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as handle:
        handle.write(data)
    return handle.name


@router.post("/broadcasts/test", response_model=BroadcastTestResult)
async def test_broadcast(
    payload: str = Form(...),
    photo: UploadFile | None = File(None),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Send every language of a draft now, to one person — the operator, to see
    it on a phone before it goes to everyone. Nothing is saved. For a rich
    message Telegram's own answer is the check that counts: what it refuses
    comes back here, with the language it refused."""
    try:
        data = BroadcastTest.model_validate_json(payload)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_url=False))
    _check_body(data.format, data.body)
    recipients = _resolve_targets(session, [data.target])
    if not recipients:
        raise HTTPException(status_code=400, detail="No recipients selected")
    chat_id = session.get(User, recipients[0]).telegram_id
    if not chat_id:
        raise HTTPException(status_code=400, detail="This person has no Telegram chat with the bot")

    photo_path = None
    if photo is not None:
        if data.format == BroadcastFormat.RICH:
            raise HTTPException(
                status_code=409,
                detail={"code": "RICH_PICTURES_INLINE", "message": "У rich-рассылки картинки — внутри текста"},
            )
        _assert_caption_fits(data.body)
        photo_path = await asyncio.to_thread(_stored_test_photo, await photo.read())

    markup = broadcast_sender.button_markup(*_button(data.with_button, data.button_text, data.button_url))
    sent: list[str] = []
    photo_file_id = None
    try:
        for language, text in data.body.items():
            if not text.strip():
                continue
            try:
                result = broadcast_sender.send_broadcast_message(
                    chat_id,
                    text,
                    message_format=data.format,
                    markup=markup,
                    photo=photo_file_id,
                    photo_path=None if photo_file_id else photo_path,
                )
            except RuntimeError as error:
                raise HTTPException(
                    status_code=502,
                    detail={"code": "TELEGRAM_REFUSED", "language": language, "sent": sent, "message": str(error)},
                )
            if photo_path and not photo_file_id:
                photo_file_id = largest_photo_file_id(result)
            sent.append(language)
    finally:
        if photo_path:
            with contextlib.suppress(OSError):
                os.remove(photo_path)
    return BroadcastTestResult(sent=sent)


@router.post("/broadcasts/media", response_model=BroadcastMedia, status_code=201)
async def upload_broadcast_media(file: UploadFile = File(...), _=Depends(require_admin)):
    """A picture for a rich broadcast. The answer is its public address, which
    goes into the text as `<img src>`."""
    try:
        url = await asyncio.to_thread(broadcast_media.save, await file.read())
    except broadcast_media.NotAnImage as error:
        raise HTTPException(status_code=400, detail=str(error))
    except broadcast_media.NoPublicAddress as error:
        raise HTTPException(status_code=503, detail={"code": "NO_PUBLIC_BASE_URL", "message": str(error)})
    return BroadcastMedia(url=url)


@router.get("/broadcasts/{broadcast_id}", response_model=BroadcastDetail)
def broadcast_detail(
    broadcast_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    broadcast = session.get(Broadcast, broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    named = []
    if broadcast.target_user_ids:
        named = [
            user.username or str(user.telegram_id)
            for user in session.exec(
                select(User).where(User.id.in_(broadcast.target_user_ids))
            ).all()
        ]

    return BroadcastDetail(
        **_broadcast_row(broadcast).model_dump(),
        target_usernames=named,
    )


@router.get("/broadcasts/{broadcast_id}/deliveries", response_model=BroadcastDeliveriesPage)
def broadcast_deliveries(
    broadcast_id: int,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Who a broadcast reached, one row per recipient.

    Paged and filterable rather than returned wholesale: the reason to open this
    list is almost always the failures, and they are a handful among thousands.
    """
    if not session.get(Broadcast, broadcast_id):
        raise HTTPException(status_code=404, detail="Broadcast not found")

    conditions = [BroadcastDelivery.broadcast_id == broadcast_id]
    if status:
        conditions.append(BroadcastDelivery.status == status)
    if q:
        conditions.append(UserRepository.search_condition(q))

    total = session.exec(
        select(func.count(BroadcastDelivery.id))
        .join(User, User.id == BroadcastDelivery.user_id)
        .where(*conditions)
    ).one()
    rows = session.exec(
        select(BroadcastDelivery, User)
        .join(User, User.id == BroadcastDelivery.user_id)
        .where(*conditions)
        .order_by(BroadcastDelivery.id)
        .offset(offset)
        .limit(limit)
    ).all()

    return BroadcastDeliveriesPage(
        items=[
            BroadcastRecipient(
                user_id=user.id,
                username=user.username,
                telegram_id=user.telegram_id,
                status=delivery.status,
                sent_at=delivery.sent_at,
                error=delivery.error,
            )
            for delivery, user in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/broadcasts/{broadcast_id}", status_code=204)
def delete_broadcast(
    broadcast_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Drafts only. Once a broadcast has been queued its delivery rows are the
    record of what people received, and that record stays."""
    broadcast = session.get(Broadcast, broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Broadcast already started")

    if broadcast.photo_path:
        with contextlib.suppress(OSError):
            os.remove(broadcast.photo_path)
    session.delete(broadcast)
    session.commit()
    return Response(status_code=204)


@router.post("/broadcasts/{broadcast_id}/send", response_model=BroadcastRow)
def queue_broadcast(
    broadcast_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Hand the broadcast to the scheduler; it materialises and sends it."""
    broadcast = session.get(Broadcast, broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    if broadcast.status != BroadcastStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Broadcast already started")
    if broadcast.photo_path:
        _assert_caption_fits(broadcast.body or {})

    broadcast.status = BroadcastStatus.QUEUED
    session.add(broadcast)
    session.commit()
    session.refresh(broadcast)
    return _broadcast_row(broadcast)


@router.post("/broadcasts/{broadcast_id}/cancel", response_model=BroadcastRow)
def cancel_broadcast(
    broadcast_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Stop mid-flight. Already-sent messages obviously stay sent."""
    broadcast = session.get(Broadcast, broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    broadcast.status = BroadcastStatus.CANCELLED
    session.add(broadcast)
    session.commit()
    session.refresh(broadcast)
    return _broadcast_row(broadcast)


def _reminder_state(reminder: PaymentReminder) -> str:
    """What the scheduler will do next with this row.

    «stopped» is not a failure: the job clears next_due_at the moment a seat
    stops qualifying — the share got paid, the bill closed, an item came back
    unallocated.
    """
    if reminder.muted_at is not None:
        return "muted"
    if reminder.next_due_at is None:
        return "stopped"
    return "scheduled"


def _reminder_state_conditions(state: str) -> list:
    if state == "muted":
        return [PaymentReminder.muted_at.is_not(None)]
    if state == "stopped":
        return [
            PaymentReminder.muted_at.is_(None),
            PaymentReminder.next_due_at.is_(None),
        ]
    if state == "scheduled":
        return [
            PaymentReminder.muted_at.is_(None),
            PaymentReminder.next_due_at.is_not(None),
        ]
    return []


@router.get("/reminders", response_model=AdminRemindersPage)
def list_reminders(
    state: str | None = None,
    only_sent: bool = False,
    bill_id: int | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Payment reminders as the scheduler keeps them: one row per seat.

    The job stores state rather than a log, so this answers «where does each
    nudge stand» — how many went out, when the last one did, when the next is
    due — not «what was sent at 15:04».
    """
    conditions = _reminder_state_conditions(state or "")
    if only_sent:
        conditions.append(PaymentReminder.sent_count > 0)
    if bill_id is not None:
        conditions.append(PaymentReminder.bill_id == bill_id)
    if q:
        conditions.append(UserRepository.search_condition(q))

    def joined(query):
        return (
            query.join(BillUser, BillUser.id == PaymentReminder.participant_id)
            .join(Bill, Bill.id == PaymentReminder.bill_id)
            .outerjoin(User, User.id == BillUser.user_id)
            .where(*conditions)
        )

    total = session.exec(joined(select(func.count(PaymentReminder.id)))).one()
    sent_total = session.exec(
        joined(select(func.coalesce(func.sum(PaymentReminder.sent_count), 0)))
    ).one()
    rows = session.exec(
        joined(select(PaymentReminder, BillUser, Bill, User))
        # Newest activity first, and a reminder that never fired sorts by when
        # the scheduler first noticed the seat.
        .order_by(
            func.coalesce(
                PaymentReminder.last_sent_at, PaymentReminder.created_at
            ).desc(),
            PaymentReminder.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return AdminRemindersPage(
        items=[
            AdminReminderRow(
                id=reminder.id,
                bill_id=bill.id,
                bill_title=bill.title,
                bill_status=bill.status,
                currency=bill.currency,
                participant_id=seat.id,
                user_id=seat.user_id,
                username=(user.username if user else None),
                telegram_id=(user.telegram_id if user else None),
                amount=from_tiins(seat.allocated_amount),
                is_paid=seat.is_paid,
                state=_reminder_state(reminder),
                sent_count=reminder.sent_count,
                last_sent_at=reminder.last_sent_at,
                next_due_at=reminder.next_due_at,
                muted_at=reminder.muted_at,
                created_at=reminder.created_at,
            )
            for reminder, seat, bill, user in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        sent_total=sent_total,
    )


def _scan_row(task: ReceiptTask, user: User | None, bill: Bill | None,
              items_count: int, has_photo: bool) -> AdminScanRow:
    return AdminScanRow(
        id=task.id,
        created_at=task.created_at,
        status=task.status,
        source=task.source,
        user=(user.username if user else None),
        bill_id=task.bill_id,
        bill_title=(bill.title if bill else None),
        scan_mode=task.scan_mode,
        llm_model=task.llm_model,
        scan_quality=task.scan_quality,
        items_count=items_count,
        has_photo=has_photo,
        error_message=task.error_message,
    )


def _settings(session: Session) -> AdminSettings:
    return AdminSettings(
        scan_mode=get_scan_mode(session).value,
        receipt_model=get_receipt_model(session),
        label_model=get_label_model(session),
        support_username=get_support_username(session),
    )


def _check_model(model: str) -> None:
    try:
        known = model_exists(model)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not check the model with OpenAI: {exc}")
    if not known:
        raise HTTPException(status_code=400, detail=f"OpenAI has no model «{model}» for this key")


@router.get("/settings", response_model=AdminSettings)
def read_settings(session: Session = Depends(get_session), _=Depends(require_admin)):
    return _settings(session)


@router.put("/settings", response_model=AdminSettings)
def write_settings(
    payload: AdminSettingsUpdate,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """Takes effect without a restart: the worker reads its settings per scan,
    the labeling job per tick, and the app asks for the support contact
    whenever it opens.

    A new model is checked with OpenAI first: a typo saved here would fail every
    scan, or every labeling tick, until somebody noticed."""
    if payload.scan_mode is not None:
        try:
            mode = ScanMode(payload.scan_mode)
        except ValueError:
            raise HTTPException(status_code=400, detail="Unknown scan mode")
        set_setting(session, SCAN_MODE_KEY, mode.value)

    for key, wanted, current in (
        (RECEIPT_MODEL_KEY, payload.receipt_model, get_receipt_model(session)),
        (LABEL_MODEL_KEY, payload.label_model, get_label_model(session)),
    ):
        model = (wanted or "").strip()
        if model and model != current:
            _check_model(model)
            set_setting(session, key, model)

    if payload.support_username is not None:
        raw = payload.support_username.strip()
        support = normalize_telegram_username(raw) if raw else ""
        if support is None:
            raise HTTPException(status_code=400, detail="Not a Telegram username")
        set_setting(session, SUPPORT_USERNAME_KEY, support)

    return _settings(session)


@router.get("/scans/modes", response_model=list[AdminScanModeStat])
def scan_mode_stats(session: Session = Depends(get_session), _=Depends(require_admin)):
    """How each reader is doing, one row per mode.

    Only photo scans count: a Soliq import has no reader to judge. Scans from
    before the modes existed are grouped under the mode that was the only one
    at the time, which is what they in fact used.
    """
    # Only the columns the stats read: whole rows dragged every scan's OCR text
    # into memory, which on a 2 GB box grows with the history.
    tasks = session.exec(
        select(
            ReceiptTask.id, ReceiptTask.source, ReceiptTask.scan_mode, ReceiptTask.status,
            ReceiptTask.scan_quality, ReceiptTask.llm_response,
        ).where(ReceiptTask.source == ReceiptSource.PHOTO)
    ).all()
    # Every scanned line at once, grouped by the scan that produced it — one
    # query for the table rather than one per completed scan.
    items_by_task: dict[int, list] = {}
    for item in session.exec(
        select(BillItem.receipt_task_id, BillItem.item_sum).where(BillItem.receipt_task_id.is_not(None))
    ).all():
        items_by_task.setdefault(item.receipt_task_id, []).append(item)

    by_mode: dict[str, list] = {}
    for task in tasks:
        by_mode.setdefault(task.scan_mode or ScanMode.OCR_LLM.value, []).append(task)

    stats = []
    for mode, group in by_mode.items():
        completed = [t for t in group if t.status == ReceiptTaskStatus.COMPLETED]
        checked = 0
        mismatched = 0
        for task in completed:
            printed, mismatch = reconcile_scan_many([task], items_by_task.get(task.id, []))
            if printed is None:
                continue
            checked += 1
            mismatched += int(mismatch)

        rated = [t.scan_quality for t in group if t.scan_quality]
        stats.append(
            AdminScanModeStat(
                mode=mode,
                scans=len(group),
                failed=len([t for t in group if t.status == ReceiptTaskStatus.FAILED]),
                mismatch_rate=(mismatched / checked) if checked else None,
                avg_quality=(sum(rated) / len(rated)) if rated else None,
                rated=len(rated),
            )
        )
    return sorted(stats, key=lambda row: row.mode)


@router.get("/scans", response_model=list[AdminScanRow])
def list_scans(
    status: str | None = None,
    source: str | None = None,
    mode: str | None = None,
    # «rated» and «unrated» split the list by whether the reader left a score at
    # all; «low» narrows it to the ones worth reading the OCR text for.
    quality: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    items_count = (
        select(func.count(BillItem.id))
        .where(BillItem.receipt_task_id == ReceiptTask.id)
        .correlate(ReceiptTask)
        .scalar_subquery()
    )
    photo_exists = (
        select(func.count(FileAsset.id))
        .where(FileAsset.receipt_task_id == ReceiptTask.id)
        .correlate(ReceiptTask)
        .scalar_subquery()
    )

    query = (
        select(ReceiptTask, User, Bill, items_count, photo_exists)
        .outerjoin(User, User.id == ReceiptTask.user_id)
        .outerjoin(Bill, Bill.id == ReceiptTask.bill_id)
        .order_by(ReceiptTask.id.desc())
        .limit(limit)
    )
    if status:
        query = query.where(ReceiptTask.status == status)
    if source:
        query = query.where(ReceiptTask.source == source)
    if mode:
        query = query.where(ReceiptTask.scan_mode == mode)
    if quality == "rated":
        query = query.where(ReceiptTask.scan_quality.is_not(None))
    elif quality == "unrated":
        query = query.where(ReceiptTask.scan_quality.is_(None))
    elif quality == "low":
        query = query.where(ReceiptTask.scan_quality <= 3)

    return [
        _scan_row(task, user, bill, count, bool(photos))
        for task, user, bill, count, photos in session.exec(query).all()
    ]


@router.get("/scans/{scan_id}", response_model=AdminScanDetail)
def scan_detail(
    scan_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    task = session.get(ReceiptTask, scan_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scan not found")

    user = session.get(User, task.user_id) if task.user_id else None
    bill = session.get(Bill, task.bill_id) if task.bill_id else None
    items = session.exec(
        select(BillItem).where(BillItem.receipt_task_id == task.id).order_by(BillItem.id)
    ).all()
    photo = session.exec(
        select(FileAsset).where(FileAsset.receipt_task_id == task.id)
    ).first()

    return AdminScanDetail(
        **_scan_row(task, user, bill, len(items), photo is not None).model_dump(),
        ocr_text=task.ocr_text,
        llm_response=task.llm_response,
        source_url=task.source_url,
        bill_total=(bill.total_sum if bill else None),
        items=[
            AdminScanItem(
                name=item.name,
                price=item.price,
                count=item.count,
                item_sum=item.item_sum,
                is_shared_globally=item.is_shared_globally,
            )
            for item in items
        ],
    )


@router.get("/scans/{scan_id}/photo")
def scan_photo(
    scan_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    """The receipt image behind a scan. Served here rather than through the
    public bill endpoint so that looking at it needs an admin session, not the
    bill's share token."""
    asset = session.exec(
        select(FileAsset).where(FileAsset.receipt_task_id == scan_id)
    ).first()
    if not asset or not os.path.exists(asset.path):
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(asset.path, media_type=asset.mime_type)
