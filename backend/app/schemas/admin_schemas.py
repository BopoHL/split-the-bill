from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.bill_schemas import (
    BillItemResponse,
    BillParticipantResponse,
    ReceiptSummary,
)


class AdminLogin(BaseModel):
    email: str
    password: str


class AdminStats(BaseModel):
    """Headline numbers for the dashboard."""
    users_total: int
    users_new_7d: int
    bills_total: int
    bills_open: int
    bills_closed: int
    bills_deleted: int
    scans_total: int
    scans_failed: int
    average_bill: float


class AdminBillRow(BaseModel):
    id: int
    title: str | None
    owner_id: int
    owner: str | None
    status: str
    currency: str
    total_sum: float
    participants_count: int
    items_count: int
    receipts_count: int
    is_deleted: bool
    created_at: datetime


class AdminBillsPage(BaseModel):
    items: list[AdminBillRow]
    total: int
    limit: int
    offset: int


class AdminUserRow(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    name: str | None
    surname: str | None = None
    avatar_url: str | None = None
    language: str | None
    currency: str | None = None
    onboarding_completed: bool = False
    bot_blocked: bool
    bills_count: int
    participant_bills_count: int = 0
    created_at: datetime


class AdminUsersPage(BaseModel):
    items: list[AdminUserRow]
    total: int
    limit: int
    offset: int


class AdminBillDetail(BaseModel):
    id: int
    owner_id: int
    owner: str | None
    total_sum: float
    title: str | None
    split_type: str
    status: str
    currency: str
    unallocated_sum: float
    allocated_sum: float
    paid_count: int
    created_at: datetime
    expected_people: int | None = None
    has_receipt: bool = False
    is_ai_scanned: bool = False
    scan_quality: int | None = None
    receipt_total_sum: float | None = None
    scan_total_mismatch: bool = False
    is_deleted: bool = False
    deleted_at: datetime | None = None
    receipts: list[ReceiptSummary] = []
    items: list[BillItemResponse]
    participants: list[BillParticipantResponse]


class AdminUserDetail(AdminUserRow):
    settings: dict = {}
    owned_bills: list[AdminBillRow] = []
    participant_bills: list[AdminBillRow] = []


class AdminUserSettingsUpdate(BaseModel):
    """What an operator may change in someone's settings. Only the keys sent
    change; a null takes the key out, so the app falls back to its default."""
    language: Literal["ru", "uz", "en"] | None = None
    theme: Literal["light", "dark", "nord", "nord_frost", "sakura", "midnight"] | None = None
    currency: str | None = None
    onboarding_completed: bool | None = None
    welcome_sent: bool | None = None
    bot_blocked: bool | None = None
    # One of the team, or a test account: PostHog leaves them out of the numbers.
    internal: bool | None = None


class BroadcastCreate(BaseModel):
    title: str
    # message — an ordinary message or a photo with a caption; rich — a rich
    # message with pictures inside the text (see BroadcastFormat).
    format: Literal["message", "rich"] = "message"
    # Message text per language. Always HTML — it is the only markup Telegram
    # parses without demanding that punctuation be escaped.
    body: dict[str, str]
    # An inline button under the message. Left on by default and pre-filled with
    # «open the bot», because a broadcast people can't act on is a dead end.
    with_button: bool = True
    button_text: str | None = None
    button_url: str | None = None
    audience: str = "all"
    # Usernames (with or without @) or telegram ids, for audience=selected.
    targets: list[str] = []
    # When to send. Absent means as soon as the scheduler picks it up. Sent as an
    # instant (ISO with an offset), never as a wall-clock string, so the two ends
    # can't disagree about which hour was meant.
    scheduled_at: datetime | None = None


class BroadcastRow(BaseModel):
    id: int
    title: str
    format: str = "message"
    body: dict[str, str]
    parse_mode: str | None = None
    button_text: str | None
    button_url: str | None
    audience: str
    target_user_ids: list[int] = []
    scheduled_at: datetime | None = None
    has_photo: bool = False
    status: str
    total_count: int
    sent_count: int
    failed_count: int
    created_at: datetime


class BroadcastTest(BaseModel):
    """A draft, sent in every language to one person before it goes to everyone."""
    format: Literal["message", "rich"] = "message"
    body: dict[str, str]
    with_button: bool = True
    button_text: str | None = None
    button_url: str | None = None
    # A username (with or without @) or a telegram id, as for audience=selected.
    target: str


class BroadcastTestResult(BaseModel):
    # The languages that went out, in the order they did.
    sent: list[str]


class BroadcastMedia(BaseModel):
    """An uploaded picture for a rich broadcast: the address to put in
    `<img src>`, which Telegram downloads it from."""
    url: str


class BroadcastRecipient(BaseModel):
    user_id: int
    username: str | None
    telegram_id: int | None
    status: str
    sent_at: datetime | None
    error: str | None


class BroadcastDetail(BroadcastRow):
    """Everything the list omits except the recipients themselves, which are
    paged through separately — a broadcast to tens of thousands can't be an
    attachment on every read of the header."""
    target_usernames: list[str] = []


class BroadcastDeliveriesPage(BaseModel):
    items: list[BroadcastRecipient] = []
    total: int
    limit: int
    offset: int


class AdminReminderRow(BaseModel):
    """The scheduler's state for one seat, as the panel reads it."""
    id: int
    bill_id: int
    bill_title: str | None
    bill_status: str
    currency: str
    participant_id: int
    user_id: int | None
    username: str | None
    telegram_id: int | None
    amount: float
    is_paid: bool
    state: str
    sent_count: int
    last_sent_at: datetime | None
    next_due_at: datetime | None
    muted_at: datetime | None
    created_at: datetime


class AdminRemindersPage(BaseModel):
    items: list[AdminReminderRow] = []
    total: int
    limit: int
    offset: int
    sent_total: int


class AdminFeedbackRow(BaseModel):
    """One message from the feedback form the app used to have. `name` is what
    the person typed into the form; the account fields say who was signed in."""
    id: int
    message: str
    name: str | None
    created_at: datetime
    user_id: int | None
    user: str | None
    telegram_id: int | None


class AdminFeedbackPage(BaseModel):
    items: list[AdminFeedbackRow]
    total: int
    limit: int
    offset: int


class AdminSettings(BaseModel):
    """The knobs an operator may turn without a deploy."""
    scan_mode: str
    receipt_model: str
    label_model: str
    support_username: str


class AdminSettingsUpdate(BaseModel):
    """Only what is sent changes. An empty support username goes back to the
    default one."""
    scan_mode: str | None = None
    receipt_model: str | None = None
    label_model: str | None = None
    support_username: str | None = None


class AdminScanModeStat(BaseModel):
    """How one reader is doing on real receipts.

    `mismatch_rate` is the share of scans whose printed total disagreed with the
    items read out of it — the one measure that needs no human. `avg_quality` is
    the readers' own 1-5 rating, over however few of them left one.
    """
    mode: str
    scans: int
    failed: int
    mismatch_rate: float | None = None
    avg_quality: float | None = None
    rated: int = 0


class AdminScanRow(BaseModel):
    id: int
    created_at: datetime
    status: str
    source: str
    scan_mode: str | None = None
    llm_model: str | None = None
    user: str | None
    bill_id: int | None
    bill_title: str | None
    scan_quality: int | None
    items_count: int
    has_photo: bool
    error_message: str | None


class AdminScanItem(BaseModel):
    name: str
    price: int
    count: int
    item_sum: int
    is_shared_globally: bool


class AdminScanDetail(AdminScanRow):
    ocr_text: str | None
    llm_response: str | None
    source_url: str | None
    # In tiins, like every other amount here — the panel formats them in one place.
    bill_total: int | None
    items: list[AdminScanItem] = []


class AdminSenderAccount(BaseModel):
    id: int
    phone: str
    telegram_id: int | None
    username: str | None
    display_name: str | None
    status: str
    rest_until: datetime | None
    last_error: str | None
    last_used_at: datetime | None
    sent_count: int
    created_at: datetime


class AdminSenderAccounts(BaseModel):
    # False until TG_API_ID / TG_API_HASH are set: nothing can be logged in.
    configured: bool
    accounts: list[AdminSenderAccount]


class AdminSenderLoginStart(BaseModel):
    phone: str


class AdminSenderCode(BaseModel):
    code: str


class AdminSenderLoginCode(BaseModel):
    code: str | None = None
    received_at: datetime | None = None


class AdminSenderPassword(BaseModel):
    password: str


class AdminSenderEnabled(BaseModel):
    enabled: bool


class AdminProStats(BaseModel):
    # Everyone Pro right now, and of them those who paid for it.
    active: int
    paying: int
    trial: int
    stars_last_30_days: int
    stars_total: int


class AdminProSettings(BaseModel):
    """Each plan's price in Telegram Stars, and the free day's scans."""
    prices: dict[str, int]
    # The struck-out «was» price of each plan; null where there is none.
    was_prices: dict[str, int | None]
    free_scans_per_day: int
    # The one-off discount on paying up front for someone who has never paid: 0% offers none.
    offer_percent: int
    offer_hours: int
    stats: AdminProStats


class AdminProSettingsUpdate(BaseModel):
    prices: dict[str, int] | None = None
    # A null takes the plan's «was» price away.
    was_prices: dict[str, int | None] | None = None
    free_scans_per_day: int | None = None
    offer_percent: int | None = None
    offer_hours: int | None = None


class AdminPromoCode(BaseModel):
    id: int
    code: str
    days: int
    max_uses: int | None
    uses: int
    expires_at: datetime | None
    is_active: bool
    note: str | None
    created_at: datetime


class AdminPromoCodeCreate(BaseModel):
    # Left empty, one is made up.
    code: str | None = None
    days: int
    max_uses: int | None = None
    expires_at: datetime | None = None
    note: str | None = None


class AdminPromoCodeUpdate(BaseModel):
    is_active: bool


class AdminProGrantUser(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    name: str | None


class AdminProGrant(BaseModel):
    """One stretch of Pro: whose, why, for how long, and what the admin may do
    with it now — `actions` holds revoke, refund, stop_renewal, allow_renewal."""
    id: int
    user: AdminProGrantUser
    source: str
    plan: str | None
    days: int | None
    stars: int | None
    promo_code: str | None
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    revoked_at: datetime | None
    refunded_at: datetime | None
    subscription_id: int | None
    renewal_canceled_at: datetime | None
    state: str
    actions: list[str]


class AdminProGrantsPage(BaseModel):
    items: list[AdminProGrant]
    total: int
    limit: int
    offset: int


class AdminRenewalUpdate(BaseModel):
    canceled: bool


class AdminPlaceRow(BaseModel):
    """A place and how it is used: bills there, people at them, first and last."""
    id: int
    name: str
    bills: int
    people: int
    first_bill_at: datetime | None
    last_bill_at: datetime | None


class AdminPlacesPage(BaseModel):
    items: list[AdminPlaceRow]
    total: int
    limit: int
    offset: int


class AdminDishRow(BaseModel):
    """A receipt line's wording and what it was labelled as; `lines` is how many
    receipt lines carry it."""
    name_key: str
    group: str
    kind: str | None
    kind_name: str | None
    # Which model labelled it, or «admin» once someone corrected it.
    model: str | None
    lines: int
    updated_at: datetime


class AdminDishesPage(BaseModel):
    items: list[AdminDishRow]
    total: int
    limit: int
    offset: int


class AdminDishLabelUpdate(BaseModel):
    name_key: str
    group: str
    # Null: not a dish of any kind.
    kind: str | None = None


class AdminDishKind(BaseModel):
    key: str
    ru: str
    uz: str
    en: str


class AdminLabelingHistory(BaseModel):
    """The run through what was there before labeling began."""
    state: str
    started_at: datetime
    finished_at: datetime | None = None
    lines_done: int
    lines_total: int
    bills_done: int
    bills_total: int


class AdminLabeling(BaseModel):
    """How labeling is doing. `since`: when it began — what came after is
    labeled on its own; None until the job first runs."""
    key_set: bool
    model: str
    since: datetime | None = None
    last_labeled_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    history: AdminLabelingHistory | None = None


class AdminBotQueue(BaseModel):
    """Where the bot's queue stands right now."""
    slots: int
    waiting: int
    in_hand: int
    retrying: int
    oldest_waiting_at: datetime | None = None
    handled_last_hour: int
    failed_last_day: int
    unsettled_payments: int


class AdminBotUpdate(BaseModel):
    update_id: int
    lane: str
    kind: str
    who: str | None = None
    what: str | None = None
    received_at: datetime
    attempts: int
    state: str
    not_before: datetime | None = None
    claimed_until: datetime | None = None
    done_at: datetime | None = None
    settled_at: datetime | None = None
    error: str | None = None
    payload: dict
    actions: list[str] = []


class AdminBotUpdatesPage(BaseModel):
    items: list[AdminBotUpdate]
    total: int
    limit: int
    offset: int
