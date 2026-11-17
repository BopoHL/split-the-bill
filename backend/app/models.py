import secrets
from enum import Enum
from sqlalchemy import Index, BigInteger, func, JSON, Text, UniqueConstraint, text, false
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class SplitType(str, Enum):
    """Enum for different ways to split a bill"""
    MANUAL = "manual"
    BY_ITEMS = "by_items"


class BillStatus(str, Enum):
    """Enum for bill statuses"""
    OPEN = "open"
    PAID = "paid"
    CLOSED = "closed"


class ReceiptTaskStatus(str, Enum):
    """Enum for receipt parsing task statuses.

    PROCESSING covers the OCR phase (extracting text); STRUCTURING covers the
    LLM phase (assembling the bill). The split lets the client show a two-step
    scan indicator.
    """
    PENDING = "pending"
    PROCESSING = "processing"
    STRUCTURING = "structuring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReceiptSource(str, Enum):
    """How a receipt task gets its data.

    PHOTO: an uploaded image, parsed via OCR + LLM. SOLIQ_QR: an Uzbek fiscal
    check imported from its ofd.soliq.uz QR link (items read from the HTML).
    MANUAL_PHOTO: an image the user attached without asking for recognition —
    there is nothing to reconcile and nothing to rate, so it has to be tellable
    apart from a scanned one.
    """
    PHOTO = "photo"
    MANUAL_PHOTO = "manual_photo"
    SOLIQ_QR = "soliq_qr"


class ScanMode(str, Enum):
    """How a photo is turned into items.

    OCR and a vision model fail differently: OCR flattens the layout, so a price
    can end up against the wrong line, while the model reads the layout but can
    misread a digit on creased paper. Which of those costs more is a question
    about real receipts, not about models, so all three are switchable.
    """
    OCR_LLM = "ocr_llm"     # Vision OCR → text to the model. The original.
    VISION = "vision"       # The photo itself to the model, no OCR.
    HYBRID = "hybrid"       # Both, so the model can settle a doubtful glyph.


class BillItemSource(str, Enum):
    """Legacy item origin kept during the receipt-task expand migration."""
    MANUAL = "manual"
    AI = "ai"


class StorageType(str, Enum):
    """Where a stored file physically lives."""
    LOCAL = "local"


class TimestampModel(SQLModel):
    """Base model for adding created_at and updated_at timestamps"""
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": func.now()}
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now()
        }
    )


class User(TimestampModel, table=True):
    """User model for Telegram users"""
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(unique=True, index=True, sa_type=BigInteger)
    username: Optional[str] = None
    name: Optional[str] = None
    surname: Optional[str] = None
    avatar_url: Optional[str] = None
    invited_by_user_id: Optional[int] = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        description="Who brought this person to the app. Written once, when the account is created from an invite; later invites do not overwrite it",
    )
    settings: dict = Field(
        default_factory=dict,
        # Stored as JSONB on Postgres (matches the DB and the b1a2c3d4e5f6
        # migration); plain JSON on SQLite so the test suite still runs.
        sa_type=JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        sa_column_kwargs={"server_default": text("'{}'")},
        description="User preferences such as theme and language",
    )

    # Relationships
    owned_bills: list["Bill"] = Relationship(back_populates="owner")
    bill_participations: list["BillUser"] = Relationship(
        back_populates="user",
        # bills_users points at users twice now (the occupant and whoever
        # invited them), so the occupant side has to be named.
        sa_relationship_kwargs={"foreign_keys": "[BillUser.user_id]"},
    )


class BillItemAssignment(TimestampModel, table=True):
    """Maps bill PARTICIPANTS to the item PORTIONS they're assigned to.

    An item with `count` N has portions 0..N-1; each portion costs item_sum/N and
    can be shared by several participants (its cost splits among them). A
    single-quantity item just uses portion 0.

    This points at bills_users rather than users so an ephemeral guest — a seat
    with no account behind it yet — can be assigned dishes like anyone else. It
    also makes it structurally impossible to assign an item to somebody who
    isn't in the bill.
    """
    __tablename__ = "bill_item_assignments"

    id: Optional[int] = Field(default=None, primary_key=True)
    bill_item_id: int = Field(foreign_key="bill_items.id", index=True)
    participant_id: int = Field(
        foreign_key="bills_users.id", index=True, ondelete="CASCADE"
    )
    # Which portion (0-based) of the item this assignment covers.
    portion_index: int = Field(default=0, sa_column_kwargs={"server_default": "0"})

    __table_args__ = (
        Index(
            "ix_item_portion_participant_unique",
            "bill_item_id", "portion_index", "participant_id",
            unique=True,
        ),
    )

    # Relationships
    bill_item: "BillItem" = Relationship(back_populates="assignments")
    participant: "BillUser" = Relationship()

class Place(TimestampModel, table=True):
    """Where a bill was run up — a café or restaurant by the name people know it
    by, not the legal entity on the fiscal receipt. One row per name, so every
    bill at the same place counts toward it."""
    __tablename__ = "places"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=80)
    name_key: str = Field(max_length=80, unique=True, index=True, description="The name lowercased, so «CAFFEINE» and «Caffeine» are one place")


class Bill(TimestampModel, table=True):
    """Bill model for managing split bills"""
    __tablename__ = "bills"
    # The admin pages through every bill newest first.
    __table_args__ = (Index("ix_bills_created_at", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="users.id")
    total_sum: int = Field(default=0, sa_type=BigInteger, description="Total amount in smallest currency unit (cents/kopeks/tiins)")
    unallocated_sum: int = Field(default=0, sa_type=BigInteger, description="Remaining unallocated amount")
    title: Optional[str] = None
    payment_method_id: Optional[int] = Field(
        default=None,
        foreign_key="payment_methods.id",
        index=True,
        description="Bill references an encrypted payment_methods row instead of storing the card number in the clear",
    )
    expected_people: Optional[int] = Field(
        default=None,
        description="Headcount the bill was created for; used to cap participants and split among all",
    )
    split_type: str = Field(default=SplitType.MANUAL)
    status: str = Field(default=BillStatus.OPEN)
    currency: str = Field(
        default="uzs",
        sa_column_kwargs={"server_default": "uzs"},
        description="Currency code bound to the bill at creation (uzs/usd/rub)",
    )
    public_token: str = Field(
        default_factory=lambda: secrets.token_urlsafe(12),
        index=True,
        unique=True,
        description="Unguessable public identifier used in invite links",
    )
    deleted_at: Optional[datetime] = Field(
        default=None,
        description="Soft delete marker. Items, participants and assignments have no meaning outside a bill, so they are hidden by filtering on the bill rather than carrying their own flag",
    )
    is_demo: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": false()},
        description="Made by the guided tour to walk a newcomer through the app. Nobody else ever sees it: it stays out of bill lists and stats, and the tour erases it when done",
    )
    invite_nudged_at: Optional[datetime] = Field(
        default=None,
        description="When the bot told the owner nobody had joined yet and handed them the invite to forward; it says so once",
    )
    place_id: Optional[int] = Field(default=None, foreign_key="places.id", ondelete="SET NULL", index=True)
    place_checked_at: Optional[datetime] = Field(
        default=None,
        description="When the place was last worked out from the scan or the title; NULL asks the labeling job to (re)do it",
    )
    place_by_owner: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": false()},
        description="The owner said where the bill was, or that it was nowhere: a new scan no longer asks the labeling job again",
    )

    # Relationships
    owner: User = Relationship(back_populates="owned_bills")
    items: list["BillItem"] = Relationship(back_populates="bill", cascade_delete=True)
    participants: list["BillUser"] = Relationship(back_populates="bill", cascade_delete=True)


class BillItem(TimestampModel, table=True):
    """Individual items in a bill"""
    __tablename__ = "bill_items"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bills.id", index=True)
    name: str
    price: int = Field(sa_type=BigInteger, sa_column_kwargs={"server_default": "0"}, description="Price in smallest currency unit")
    count: int = Field(default=1)
    item_sum: int = Field(default=0, sa_type=BigInteger, sa_column_kwargs={"server_default": "0"}, description="Total sum for this item (price * count)")
    is_shared_globally: bool = Field(default=False, description="If true, item is automatically divided among all participants (e.g. service fee)")
    # Keep this compatibility marker for one release so old and new workers can
    # run against the expanded schema during deployment. receipt_task_id is the
    # new source of truth; a later contract migration can remove this column.
    source: str = Field(
        default=BillItemSource.MANUAL,
        sa_column_kwargs={"server_default": BillItemSource.MANUAL.value},
        description="Deprecated compatibility marker for scan-produced items.",
    )
    receipt_task_id: Optional[int] = Field(
        default=None,
        foreign_key="receipt_tasks.id",
        index=True,
        description="Scan task that produced this item; NULL for manually added ones. A re-scan replaces only items that have a task.",
    )

    # Relationships
    bill: Bill = Relationship(back_populates="items")
    assignments: list["BillItemAssignment"] = Relationship(back_populates="bill_item", cascade_delete=True)


class BillUser(TimestampModel, table=True):
    """Participants in a bill (users or guests)"""
    __tablename__ = "bills_users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bills.id")
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    guest_name: Optional[str] = Field(
        default=None,
        description="Owner-given name for an unclaimed seat. NULL means the UI shows the default «Guest N» built from seat_index — the localized label is never stored",
    )
    seat_index: int = Field(
        default=0,
        sa_column_kwargs={"server_default": "0"},
        description="Position at the table. The owner is always seat 0; guests take 1..N-1. Gives the participant list a stable order and survives people swapping seats",
    )
    claimed_at: Optional[datetime] = Field(
        default=None,
        description="When a real account took this seat; NULL while it is still an ephemeral guest",
    )
    allocated_amount: int = Field(default=0, sa_type=BigInteger, description="Amount allocated to this participant")
    is_paid: bool = Field(default=False)
    paid_at: Optional[datetime] = Field(default=None, description="When the seat was last marked paid; NULL while unpaid")
    owner_told_at: Optional[datetime] = Field(
        default=None,
        description="When the owner learned of this payment: from the bot, or at once when it was theirs to mark. NULL on a paid seat means the bot still has to tell them",
    )
    invited_by_user_id: Optional[int] = Field(
        default=None,
        foreign_key="users.id",
        description="Who invited this person into THIS bill. Unlike User.invited_by_user_id it is per-bill: the same person can be brought in by different people to different tables",
    )

    __table_args__ = (
        # Составной индекс: ускоряет поиск по паре bill_id + user_id
        # и гарантирует, что пользователь не добавится в один счет дважды.
        # Гостевые места (user_id IS NULL) под него не попадают — NULL'ы в
        # Postgres не конфликтуют между собой.
        Index("ix_bill_user_unique", "bill_id", "user_id", unique=True),
        Index("ix_bill_user_seat", "bill_id", "seat_index", unique=True),
    )
    
    # Relationships
    bill: Bill = Relationship(back_populates="participants")
    user: Optional[User] = Relationship(
        back_populates="bill_participations",
        sa_relationship_kwargs={"foreign_keys": "[BillUser.user_id]"},
    )


class BroadcastStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENDING = "sending"
    DONE = "done"
    CANCELLED = "cancelled"


class BroadcastFormat(str, Enum):
    # An ordinary message, or a photo with the text as its caption.
    MESSAGE = "message"
    # A rich message (Bot API 10.1+): headings, lists, tables, and pictures
    # between paragraphs. Clients from before mid-2026, Telegram Web and the
    # macOS app show it as unsupported, and the bot is never told.
    RICH = "rich"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


class Broadcast(TimestampModel, table=True):
    """An announcement sent to everyone the bot can write to."""
    __tablename__ = "broadcasts"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    body: dict = Field(
        default_factory=dict,
        sa_type=JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        sa_column_kwargs={"server_default": text("'{}'")},
        description="Message text per language code, e.g. {'ru': '…', 'en': '…'}",
    )
    button_text: Optional[str] = None
    button_url: Optional[str] = None
    parse_mode: Optional[str] = Field(
        default="HTML",
        description="HTML | Markdown | NULL for plain text — how Telegram renders the body",
    )
    format: str = Field(
        default=BroadcastFormat.MESSAGE,
        sa_column_kwargs={"server_default": BroadcastFormat.MESSAGE.value},
        description="message | rich — sent with sendMessage/sendPhoto, or with sendRichMessage",
    )
    audience: str = Field(
        default="all",
        description="all | active_30d | selected — who the deliveries are materialised for",
    )
    target_user_ids: list = Field(
        default_factory=list,
        sa_type=JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        sa_column_kwargs={"server_default": text("'[]'")},
        description="Resolved recipients for audience=selected; usernames and telegram ids are resolved when the broadcast is created, so the list can't drift afterwards",
    )
    # An attached image, kept on disk like receipt photos. `photo_file_id` is
    # Telegram's own handle for it, learned from the first successful send and
    # reused for the rest — re-uploading the same picture to every recipient
    # would multiply the traffic by the size of the audience.
    photo_path: Optional[str] = Field(default=None)
    photo_file_id: Optional[str] = Field(default=None)
    scheduled_at: Optional[datetime] = Field(
        default=None,
        index=True,
        description="Naive UTC. NULL means «as soon as possible». Stored in UTC so the server's own timezone never enters the picture — the wall clock the operator typed is converted once, in the admin panel",
    )
    status: str = Field(default=BroadcastStatus.DRAFT, index=True)
    total_count: int = Field(default=0)
    sent_count: int = Field(default=0)
    failed_count: int = Field(default=0)


class BroadcastDelivery(TimestampModel, table=True):
    """One recipient of one broadcast.

    Exists for correctness rather than statistics: a send to thousands of users
    takes minutes, and without a per-recipient record a restart mid-flight would
    start over and message people twice.
    """
    __tablename__ = "broadcast_deliveries"

    id: Optional[int] = Field(default=None, primary_key=True)
    broadcast_id: int = Field(foreign_key="broadcasts.id", index=True, ondelete="CASCADE")
    user_id: int = Field(foreign_key="users.id", index=True)
    status: str = Field(default=DeliveryStatus.PENDING, index=True)
    error: Optional[str] = None
    sent_at: Optional[datetime] = None

    __table_args__ = (
        Index("ix_broadcast_delivery_unique", "broadcast_id", "user_id", unique=True),
    )


class PaymentReminder(TimestampModel, table=True):
    """Nudges an unpaid participant towards settling up.

    One row per (bill, seat). It is the scheduler's memory: how many reminders
    have gone out, when the next one is due, and whether the bot has been shut
    out. Keeping it in the database rather than in the process means a restart
    doesn't reset everyone's cadence — or fire a burst of catch-up messages.
    """
    __tablename__ = "payment_reminders"

    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bills.id", index=True)
    participant_id: int = Field(
        foreign_key="bills_users.id", index=True, ondelete="CASCADE"
    )
    sent_count: int = Field(default=0)
    last_sent_at: Optional[datetime] = None
    next_due_at: Optional[datetime] = Field(
        default=None,
        description="When the next reminder may go out; NULL means the conditions no longer hold",
    )
    muted_at: Optional[datetime] = Field(
        default=None,
        description="Set when Telegram says it can't deliver (bot blocked, chat gone) — not a user-facing setting",
    )

    __table_args__ = (
        Index("ix_payment_reminder_unique", "bill_id", "participant_id", unique=True),
        Index("ix_payment_reminder_due", "next_due_at"),
    )


class SenderAccountStatus(str, Enum):
    AWAITING_CODE = "awaiting_code"
    AWAITING_PASSWORD = "awaiting_password"
    ACTIVE = "active"
    # Telegram held it back for a while — flood or spam limits; back after rest_until.
    RESTING = "resting"
    # Telegram shut it out for good; it only takes room in the list now.
    BANNED = "banned"
    DISABLED = "disabled"


class SenderAccount(TimestampModel, table=True):
    """A Telegram user account that delivers reminders the bot cannot.

    Someone who blocked the bot still gets the reminder, from one of these, as
    the bot's own post sent through it. They are spent over time — Telegram
    limits and bans accounts that write to strangers — so the operator logs new
    ones in from the admin panel rather than from a deploy.
    """
    __tablename__ = "sender_accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    phone: str = Field(unique=True, index=True)
    session_enc: Optional[str] = Field(
        default=None,
        description="AES-GCM encrypted Telethon StringSession: the login itself, kept from the first step of logging in",
    )
    phone_code_hash: Optional[str] = Field(
        default=None, description="What the code sent at login has to be checked against; cleared once logged in"
    )
    telegram_id: Optional[int] = Field(default=None, sa_type=BigInteger)
    username: Optional[str] = None
    display_name: Optional[str] = None
    status: str = Field(default=SenderAccountStatus.AWAITING_CODE, index=True)
    rest_until: Optional[datetime] = Field(default=None, description="Naive UTC; while RESTING")
    last_error: Optional[str] = None
    last_used_at: Optional[datetime] = None
    sent_count: int = Field(default=0)


class ManualReminderStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ReminderChannel(str, Enum):
    BOT = "bot"
    ACCOUNT = "account"


class ReminderFailure(str, Enum):
    # Nobody could write to the person: the bot is blocked, and no account can
    # find them (no username) or their privacy keeps strangers out.
    UNREACHABLE = "unreachable"
    # The bot is blocked and every sender account was used up.
    NO_SENDERS = "no_senders"
    # The share was paid or the bill closed before the reminder went out.
    SETTLED = "settled"
    ERROR = "error"


class ManualReminder(TimestampModel, table=True):
    """A reminder the bill's owner sent by hand to one person on their seat.

    Written as pending when asked for and delivered by a job — from the bot, or
    through the sender accounts when the bot is blocked — so a press in the app
    never waits on Telegram, and a restart does not lose what was asked for.
    """
    __tablename__ = "manual_reminders"

    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bills.id", index=True)
    participant_id: int = Field(foreign_key="bills_users.id", index=True, ondelete="CASCADE")
    requested_by_user_id: int = Field(foreign_key="users.id")
    status: str = Field(default=ManualReminderStatus.PENDING, index=True)
    channel: Optional[str] = Field(default=None, description="A ReminderChannel, once sent")
    sender_account_id: Optional[int] = Field(
        default=None, foreign_key="sender_accounts.id", ondelete="SET NULL",
        description="The account that sent it, when the bot could not",
    )
    failure: Optional[str] = Field(default=None, description="A ReminderFailure, when it could not be sent")
    sent_at: Optional[datetime] = None


class ReceiptTask(TimestampModel, table=True):
    """Background task for processing receipt photos"""
    __tablename__ = "receipt_tasks"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    # The stored photo filename — null for QR imports, which have no image.
    filename: Optional[str] = Field(default=None)
    # Where the receipt comes from and, for QR imports, the validated
    # ofd.soliq.uz check URL the worker fetches.
    source: str = Field(
        default=ReceiptSource.PHOTO,
        sa_column_kwargs={"server_default": ReceiptSource.PHOTO.value},
    )
    source_url: Optional[str] = Field(default=None)
    status: str = Field(default=ReceiptTaskStatus.PENDING, index=True)
    # The bill is created up front (with its headcount/payment/currency) when the
    # scan is uploaded; the worker only enriches THIS bill (title, items, total),
    # so the task no longer carries wizard inputs of its own.
    bill_id: Optional[int] = Field(default=None, foreign_key="bills.id")
    # True when the bill was created for this scan and has not been seen by
    # anyone yet — a failed or cancelled scan then takes it down again. A scan
    # into a bill that already existed must never delete it.
    owns_bill: bool = Field(default=False, sa_column_kwargs={"server_default": "false"})
    error_message: Optional[str] = None
    # Chat waiting to be told how the scan went. Set when the scan was started
    # from a conversation with the bot; null for uploads out of the Mini App,
    # where the user is already watching the bill update itself.
    notify_chat_id: Optional[int] = Field(default=None, sa_type=BigInteger)
    # Raw AI responses, kept to debug scan quality (STB-69), and a 1–5 user
    # rating of the scan (STB-70).
    scan_mode: Optional[str] = Field(
        default=None,
        index=True,
        description="Which mode actually read this receipt — the setting can change between scans, and comparing them is the point of having modes",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Which model structured this receipt — like the mode, the setting can change between scans",
    )
    ocr_text: Optional[str] = Field(default=None, sa_type=Text)
    llm_response: Optional[str] = Field(default=None, sa_type=Text)
    scan_quality: Optional[int] = Field(default=None)

    __table_args__ = (
        Index("ix_receipt_tasks_bill_id_id", "bill_id", "id"),
    )

    # Relationships
    user: Optional[User] = Relationship()
    bill: Optional[Bill] = Relationship()


class AppSetting(TimestampModel, table=True):
    """One operator-owned knob, by name.

    Everything else that configures the app is an env var, which is right for
    things that only change with a deploy. This is for the ones an operator flips
    while watching what happens.
    """
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)
    value: str


class PaymentMethod(TimestampModel, table=True):
    """A user's saved payment details, stored encrypted at rest."""
    __tablename__ = "payment_methods"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    label: Optional[str] = Field(default=None, description="Optional human label")
    enc_value: str = Field(description="AES-GCM encrypted payment details (base64)")
    deleted_at: Optional[datetime] = Field(
        default=None,
        description="Removed from the picker but kept on disk: bills reference this row, and a hard delete would either violate the FK or strip the card off past bills",
    )

    # Relationships
    user: Optional[User] = Relationship()


class FileAsset(TimestampModel, table=True):
    """Metadata for a stored file (e.g. a receipt photo), kept separate from
    the binary so the backing store can later move to S3 etc."""
    __tablename__ = "file_assets"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    bill_id: Optional[int] = Field(default=None, foreign_key="bills.id", index=True)
    receipt_task_id: Optional[int] = Field(default=None, foreign_key="receipt_tasks.id", index=True, description="Scan task this file belongs to; deleting it cascades to the task's items.")
    original_name: Optional[str] = None
    path: str = Field(index=True, description="Path/key within the storage backend")
    size: int = Field(default=0, description="Stored (compressed) size in bytes")
    mime_type: str = Field(default="application/octet-stream")
    storage_type: str = Field(default=StorageType.LOCAL)


class Feedback(TimestampModel, table=True):
    """A message from the feedback form the app used to have. Nothing writes
    these any more — support is a Telegram chat now — but what was sent is kept
    and read in the admin panel."""
    __tablename__ = "feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    category: str = Field(default="suggestion")  # suggestion | complaint | other
    name: Optional[str] = Field(default=None, description="Optional display name of the submitter")
    message: str

    # Relationships
    user: Optional[User] = Relationship()


class BotDialogStep(str, Enum):
    """Where a chat currently sits inside a bot conversation."""
    BILL_HEADCOUNT = "bill_headcount"
    BILL_PAYMENT = "bill_payment"
    BILL_PAYMENT_NEW = "bill_payment_new"
    BILL_RECEIPT = "bill_receipt"
    # A voice message heard, waiting to be told which bill it is for.
    BILL_VOICE = "bill_voice"


class BotDialog(TimestampModel, table=True):
    """A chat's position in the bot's onboarding and bill-creation flows.

    The webhook is stateless and a flow spans several messages, so the step and
    everything gathered so far have to outlive the request. Memory would not:
    the API restarts on every deploy and can run more than one worker.
    """
    __tablename__ = "bot_dialogs"

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(unique=True, index=True, sa_type=BigInteger)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    step: str = Field(description="A BotDialogStep value")
    draft: dict = Field(
        default_factory=dict,
        sa_type=JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        sa_column_kwargs={"server_default": text("'{}'")},
        description="Answers collected so far, e.g. headcount and payment method",
    )

    # Relationships
    user: Optional[User] = Relationship()


class BotPanelKind(str, Enum):
    TEXT = "text"
    RICH = "rich"


class BotPanel(TimestampModel, table=True):
    """The one message in a chat that the bot keeps redrawing instead of
    sending new ones; see services/bot_panel.py."""
    __tablename__ = "bot_panels"

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(unique=True, index=True, sa_type=BigInteger)
    message_id: int
    bottom_message_id: int = Field(
        description="The newest message known to sit at the panel's foot: the panel itself, or what the "
        "person typed into it and the bot deleted. A newer one means something came in under the panel."
    )
    kind: str = Field(
        default=BotPanelKind.TEXT,
        description="A BotPanelKind value: a rich message can only be replaced, not edited into text",
    )


class TelegramUpdate(SQLModel, table=True):
    """An update Telegram delivered, kept from the moment it arrives until the
    bot is done with it.

    The webhook only stores it and answers; the bot's worker handles it in the
    background. Updates in one lane — one chat's messages, the taps on one
    post — are handled one after another in Telegram's order; lanes run side
    by side.
    """
    __tablename__ = "telegram_updates"
    __table_args__ = (
        Index(
            "ix_telegram_updates_waiting", "lane", "update_id",
            postgresql_where=text("done_at IS NULL"), sqlite_where=text("done_at IS NULL"),
        ),
    )

    update_id: int = Field(
        primary_key=True, sa_type=BigInteger, sa_column_kwargs={"autoincrement": False},
        description="Telegram's own id: an update delivered twice is kept once",
    )
    lane: str = Field(max_length=128, description="Updates in one lane are handled one at a time, in order")
    payload: dict = Field(sa_type=JSON().with_variant(JSONB(astext_type=Text()), "postgresql"))
    received_at: datetime
    attempts: int = Field(default=0, description="How many times a worker has taken it")
    not_before: Optional[datetime] = Field(default=None, description="A payment to be tried again waits until then")
    claimed_until: Optional[datetime] = Field(
        default=None, description="A worker is on it; should that worker die, another takes it after this",
    )
    claimed_by: Optional[str] = Field(default=None, max_length=32, description="The worker on it")
    done_at: Optional[datetime] = Field(default=None, description="When it was handled, or given up on")
    error: Optional[str] = Field(default=None, sa_type=Text, description="Why the last attempt failed")
    settled_at: Optional[datetime] = Field(
        default=None, description="When the admin settled by hand a payment the worker gave up on",
    )


class InviteChannel(str, Enum):
    """How an invite was handed over."""
    LINK = "link"
    QR = "qr"
    PREPARED = "prepared"
    SEAT = "seat"
    BOT = "bot"
    # Not handed over by anyone: the reminder an owner sent to someone on their seat.
    REMINDER = "reminder"


class Invite(TimestampModel, table=True):
    """One act of sharing a bill.

    The bill's public_token cannot answer "who brought this person" — it is one
    value per bill, shared by everyone at the table, and it says nothing about
    the channel. An invite is minted per share, so the link a person follows
    identifies both the inviter and how they were reached.
    """
    __tablename__ = "invites"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(
        default_factory=lambda: secrets.token_urlsafe(9),
        unique=True,
        index=True,
        description="What travels in the deep link, as inv_<code>",
    )
    bill_id: int = Field(foreign_key="bills.id", index=True)
    inviter_user_id: int = Field(foreign_key="users.id", index=True)
    seat_participant_id: Optional[int] = Field(
        default=None,
        foreign_key="bills_users.id",
        ondelete="SET NULL",
        description="Set for a personal invite to one seat; NULL for a link anyone at the table may take",
    )
    channel: InviteChannel = Field(default=InviteChannel.LINK)


class SharedBillMessage(TimestampModel, table=True):
    """A bill shared into a chat, kept current while the bill changes.

    A row is written when the share is prepared. Telegram names the message it
    became later — when the share is chosen, if inline feedback is on, or when
    somebody first presses its refresh button — and only from then on can it be
    edited. One share forwarded on turns into several messages, one row each.
    """
    __tablename__ = "shared_bill_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bills.id", index=True)
    invite_code: str = Field(index=True, description="The invite its open button carries; the refresh button names it too")
    language: str = Field(description="The sharer's language, which the message keeps")
    theme: str = Field(default="light", description="The sharer's app theme, which its picture keeps")
    inline_message_id: Optional[str] = Field(default=None, unique=True, index=True)
    fingerprint: Optional[str] = Field(default=None, description="Which state of the bill the message shows now")
    refreshed_at: Optional[datetime] = Field(default=None)
    is_final: bool = Field(default=False, description="Shows the closed bill; nothing left to update")
    is_gone: bool = Field(default=False, description="Telegram no longer knows the message: deleted, or never sent")


class DishGroup(str, Enum):
    """What a receipt line is, broadly — enough to say where the money went."""

    FOOD = "food"
    DRINK = "drink"
    DESSERT = "dessert"
    ALCOHOL = "alcohol"
    FEE = "fee"
    DISCOUNT = "discount"
    OTHER = "other"


class DishLabel(TimestampModel, table=True):
    """What a receipt line is, worked out once per wording and shared by every
    bill that has it: «Чизбургер Double» is food, a burger."""
    __tablename__ = "dish_labels"

    name_key: str = Field(primary_key=True, max_length=200, description="The line's name trimmed and lowercased")
    group: str = Field(default=DishGroup.OTHER)
    kind: Optional[str] = Field(default=None, max_length=40, description="A dish_kinds key — «burger», «cappuccino»; NULL for what is not a dish")
    model: Optional[str] = Field(default=None, description="Which model labeled it")


class DishKind(TimestampModel, table=True):
    """A kind of dish or drink, named in each language the app speaks."""
    __tablename__ = "dish_kinds"

    key: str = Field(primary_key=True, max_length=40)
    ru: str = Field(max_length=60)
    uz: str = Field(max_length=60)
    en: str = Field(max_length=60)


class ProSource(str, Enum):
    """Why someone has Pro for a stretch of time."""
    # A free trial. Nothing gives one at the moment.
    TRIAL = "trial"
    # Paid in Telegram Stars once: six months or a year.
    PURCHASE = "purchase"
    # A month of a Stars subscription Telegram renews by itself, the first or a later one.
    SUBSCRIPTION = "subscription"
    PROMO = "promo"


class ProPlan(str, Enum):
    MONTH = "month"
    HALF_YEAR = "half_year"
    YEAR = "year"


class PromoCode(TimestampModel, table=True):
    """A code that gives Pro for some days, made in the admin panel."""
    __tablename__ = "promo_codes"

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(max_length=32, unique=True, index=True, description="Upper case; matched without regard to case")
    days: int
    max_uses: Optional[int] = Field(default=None, description="NULL: as many people as want it")
    uses: int = Field(default=0)
    expires_at: Optional[datetime] = None
    is_active: bool = Field(default=True)
    note: Optional[str] = Field(default=None, max_length=200, description="What it was made for, for the operator")


class ProSubscription(TimestampModel, table=True):
    """A month of Pro that Telegram renews in Stars by itself. The Bot API knows
    it by its first payment; every renewal is a grant of its own."""
    __tablename__ = "pro_subscriptions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    charge_id: str = Field(
        max_length=255, unique=True, description="telegram_payment_charge_id of the first payment: the subscription's name in the Bot API",
    )
    renewal_canceled_at: Optional[datetime] = Field(
        default=None, description="When the admin stopped Telegram renewing it; NULL while it renews",
    )


class ProOffer(TimestampModel, table=True):
    """A discount on paying for Pro up front, offered once: the first time someone
    who has never paid sees the paywall. It holds until ends_at — the moment the
    app counts down to — and so does the price; after it the plans cost what they
    cost everyone."""
    __tablename__ = "pro_offers"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True)
    percent: int
    ends_at: datetime


class FreeReminderUse(TimestampModel, table=True):
    """A «remind everyone» pressed without Pro. A few a month come free so the
    owner can see it work; the month's count is these rows."""
    __tablename__ = "free_reminder_uses"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)


class ProGrant(TimestampModel, table=True):
    """A stretch of time someone has Pro for, and why.

    Someone is Pro while any of their grants covers the moment. A new grant
    starts where the last one ends, so buying early, a promo code on top of a
    purchase and a subscription's renewals all add up rather than overlap.
    """
    __tablename__ = "pro_grants"
    __table_args__ = (UniqueConstraint("user_id", "promo_code_id", name="uq_pro_grants_user_promo"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    source: str = Field(max_length=20)
    plan: Optional[str] = Field(default=None, max_length=20)
    starts_at: datetime
    ends_at: datetime = Field(index=True)
    stars: Optional[int] = Field(default=None, description="What was paid, in Telegram Stars")
    charge_id: Optional[str] = Field(
        default=None, max_length=255, unique=True,
        description="telegram_payment_charge_id: the same payment reported twice is recorded once",
    )
    promo_code_id: Optional[int] = Field(default=None, foreign_key="promo_codes.id")
    subscription_id: Optional[int] = Field(default=None, foreign_key="pro_subscriptions.id", index=True)
    ending_noted_at: Optional[datetime] = Field(default=None, description="When the bot said this Pro is about to end")
    revoked_at: Optional[datetime] = Field(
        default=None, description="When the admin took it back: it ended then, and what was queued after it moved up",
    )
    refunded_at: Optional[datetime] = Field(default=None, description="When its Stars went back to the payer")


def dish_key(name: str) -> str:
    return name.strip().lower()[:200]


def place_key(name: str) -> str:
    return " ".join(name.lower().split())[:80]
