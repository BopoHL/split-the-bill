from typing import Literal
from pydantic import BaseModel, Field
from datetime import datetime
from app.schemas.types import UtcDatetime
from app.utils.currency import from_tiins

class BillCreate(BaseModel):
    """Schema for creating a bill"""
    owner_id: int
    total_sum: float
    title: str | None = None
    payment_details: str | None = None
    expected_people: int | None = None
    include_owner: bool = False
    # Currency the creator is using; bound to the bill at creation. Falls back
    # to the owner's saved setting (then 'uzs') server-side if omitted/invalid.
    currency: str | None = None

class BillUpdate(BaseModel):
    """Schema for updating bill fields.

    Only fields present in the request are applied (the service uses
    `model_fields_set` to distinguish 'not sent' from 'explicitly null').
    """
    title: str | None = None
    payment_details: str | None = None
    expected_people: int | None = None
    # New currency for the whole bill (owner only). Validated server-side; an
    # invalid code is rejected. Amounts are not re-denominated (STB-213).
    currency: str | None = None
    user_id: int

class ParticipantPreview(BaseModel):
    """Compact participant for dashboard cards (initial + optional avatar)."""
    initial: str
    avatar_url: str | None = None

class ViewerSeat(BaseModel):
    """The seat of whoever asked for the list, on a bill they sit at."""
    id: int
    amount: float
    is_paid: bool

class BillOwner(BaseModel):
    name: str | None = None
    avatar_url: str | None = None

class BillCollection(BaseModel):
    """What the owner is still collecting on an open bill, and whom they may
    remind of it now — the bell on their row on the home screen."""
    left: float
    remindable: int
    reminded_at: datetime | None = None
    next_reminder_at: datetime | None = None

class BillCounts(BaseModel):
    all: int
    owned: int
    joined: int

class BillResponse(BaseModel):
    """Schema for bill response"""
    id: int
    owner_id: int
    total_sum: float
    title: str | None
    payment_details: str | None
    split_type: str
    status: str
    currency: str = "uzs"
    unallocated_sum: float
    created_at: UtcDatetime
    participants_count: int
    # Dashboard-card aggregates (computed in one query, no N+1).
    items_count: int = 0
    paid_count: int = 0
    # Same counts with the owner excluded — the card shows how many of the
    # people who owe the owner have settled up, and the owner isn't one of them.
    payers_count: int = 0
    payers_paid: int = 0
    participants_preview: list[ParticipantPreview] = []
    public_token: str
    expected_people: int | None = None
    # Said for whoever listed their bills; absent elsewhere.
    my_seat: ViewerSeat | None = None
    owner: BillOwner | None = None
    collection: BillCollection | None = None

class BillItemCreate(BaseModel):
    """Schema for creating a bill item"""
    name: str
    price: float
    count: int = Field(default=1, ge=1)

class BillItemUpdate(BaseModel):
    """Partial update of a bill item; unset fields are left unchanged."""
    name: str | None = None
    price: float | None = None
    count: int | None = Field(default=None, ge=1)
    is_shared_globally: bool | None = None

class BillItemResponse(BaseModel):
    """Schema for bill item response"""
    id: int
    bill_id: int
    name: str
    price: float
    count: int
    item_sum: float
    is_shared_globally: bool
    # Distinct participants assigned to ANY portion of the item (avatars /
    # shared-tag). Participants, not users: a guest seat has no account yet.
    assigned_participant_ids: list[int]
    # Which receipt brought this line in; None for hand-added ones. The client
    # groups the list by it — without it every item looked hand-added.
    receipt_task_id: int | None = None
    # Per-portion assignees: list of length `count`, each the participant ids on
    # that portion. Lets the client show/take individual portions of a multi-qty item.
    portions: list[list[int]] = []

    @classmethod
    def from_item(cls, item) -> "BillItemResponse":
        """Build the response from a BillItem ORM row (with .assignments)."""
        count = max(1, item.count or 1)
        portions: list[list[int]] = [[] for _ in range(count)]
        for a in item.assignments:
            if 0 <= a.portion_index < count:
                portions[a.portion_index].append(a.participant_id)
        return cls(
            id=item.id,
            bill_id=item.bill_id,
            name=item.name,
            price=from_tiins(item.price),
            count=item.count,
            item_sum=from_tiins(item.item_sum),
            is_shared_globally=item.is_shared_globally,
            assigned_participant_ids=sorted({a.participant_id for a in item.assignments}),
            receipt_task_id=item.receipt_task_id,
            portions=portions,
        )

class BillItemAssign(BaseModel):
    """Schema for assigning/unassigning an item to a participant.

    `portion_index` targets a single portion of a multi-quantity item; when
    omitted (None) the toggle applies to the WHOLE item (every portion) — the
    "take/assign the whole dish" action.
    """
    participant_id: int
    is_assigned: bool
    portion_index: int | None = None

class BillItemAssignOp(BaseModel):
    item_id: int
    participant_id: int
    is_assigned: bool
    portion_index: int | None = None
    # Optional optimistic guard for flattened position refs. Legacy callers may
    # omit it; new callers send the count used to build itemId:portionIndex.
    expected_count: int | None = None


class BillItemSharedOp(BaseModel):
    item_id: int
    is_shared_globally: bool


class BillItemAssignBatch(BaseModel):
    """Apply many assign/unassign (and shared-flag) ops in one atomic request.

    Commits a whole multi-select in a single round-trip instead of N requests,
    avoiding the N-SSE-refetch race that dropped some portions on iOS. Shared
    flags apply first, then the per-portion assignment ops.
    """
    shared: list[BillItemSharedOp] = []
    ops: list[BillItemAssignOp] = []


class BillParticipantCreate(BaseModel):
    """Schema for adding a participant to a bill.

    Guests (free-text names) are no longer accepted — a participant must be a
    real user, added via the invite link. guest_name remains on the model and
    the response only so legacy bills still display their old guest entries.
    """
    user_id: int

class ParticipantReminder(BaseModel):
    """The last reminder the owner sent this seat by hand."""
    status: str
    # When it was asked for.
    at: datetime
    failure: str | None = None
    # Until when another one cannot be sent; None when it can be now.
    next_at: datetime | None = None


class BillParticipantResponse(BaseModel):
    """Schema for bill participant response"""
    id: int
    bill_id: int
    user_id: int | None
    guest_name: str | None
    username: str | None = None
    name: str | None = None
    surname: str | None = None
    avatar_url: str | None = None
    allocated_amount: float
    is_paid: bool
    # Seat metadata. `is_guest` is derived rather than stored — a seat is a guest
    # for exactly as long as no account occupies it.
    seat_index: int = 0
    is_guest: bool = False
    claimed_at: datetime | None = None
    reminder: ParticipantReminder | None = None
    # The badge by their name: «pro» or an analytics title's key.
    badge: str | None = None


class BillParticipantRename(BaseModel):
    """Rename an unclaimed guest seat. Empty resets it to the default label."""
    user_id: int
    guest_name: str | None = None


class SeatClaim(BaseModel):
    user_id: int
    invite_code: str | None = None
    # The bill's invite-link token. A newcomer needs it or an invite code of
    # this bill — seat ids are sequential, so knowing one proves nothing.
    token: str | None = None
    # Set only after the client has asked. Moving seats abandons the dishes on
    # the seat being left, so the server refuses a move that nobody confirmed —
    # see BillParticipantService.claim_seat.
    confirm_move: bool = False


class SeatItemPreview(BaseModel):
    """A dish already sitting on a seat, shown while choosing where to sit."""
    name: str
    share: float


class SeatPreview(BaseModel):
    id: int
    seat_index: int
    guest_name: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    is_taken: bool
    is_me: bool = False
    allocated_amount: float
    items: list[SeatItemPreview] = []


class ReceiptSummary(BaseModel):
    """One receipt attached to a bill, as the receipts list shows it."""
    task_id: int
    index: int
    source: str
    status: str
    merchant_name: str | None = None
    total: float | None = None
    items_count: int = 0
    quality: int | None = None
    has_photo: bool = False
    created_at: UtcDatetime


class ReceiptDeleteImpact(BaseModel):
    """What deleting a receipt would cost, shown in the confirmation."""
    items_count: int
    total: float
    assigned_count: int


class BillSeatsResponse(BaseModel):
    """Everything a newcomer needs to pick a seat, without granting them the bill."""
    bill_id: int
    title: str | None
    currency: str
    status: str
    seats: list[SeatPreview]

class BillParticipantAssign(BaseModel):
    """Schema for manual amount assignment to a participant"""
    participant_id: int
    allocated_amount: float = Field(ge=0)

class BillSplitRemainder(BaseModel):
    """Schema for splitting the remainder among selected participants"""
    participant_ids: list[int]

class BillParticipantPaymentUpdate(BaseModel):
    """Schema for updating participant's payment status"""
    is_paid: bool
    user_id: int

class BillClose(BaseModel):
    """Close the bill. `remainder` first hands what nobody took to the owner
    (`me`) or to every seat (`all`), in the same transaction."""
    user_id: int
    remainder: Literal["me", "all"] | None = None


class BillParticipantRemove(BaseModel):
    """Schema for removing a participant"""
    user_id: int

class BillJoinByToken(BaseModel):
    """Schema for joining a bill via its unguessable public token"""
    token: str
    user_id: int
    invite_code: str | None = None

class BillShareRequest(BaseModel):
    """Prepare the bill's chat post to share from the Mini App.

    The server writes the post, since it rewrites it whenever the bill changes;
    `lang` is the sharer's, and the post keeps it. Without one the sharer's
    saved setting decides.
    """
    lang: str | None = None


class BillPersonalSeatInviteRequest(BaseModel):
    """Prepare a one-seat invite. `lang` selects server-side copy."""
    lang: str | None = None


class BillSeatAssign(BaseModel):
    """Seat a specific person on a specific seat.

    The person is `target_user_id` rather than `user_id`, which everywhere else
    in this API means the caller — here the caller is the owner and the id is
    somebody else entirely.
    """
    target_user_id: int
    lang: str | None = None


class BillAssignableUser(BaseModel):
    """A candidate for a seat, as the picker shows them."""
    user_id: int
    username: str | None = None
    name: str | None = None
    surname: str | None = None
    avatar_url: str | None = None


class BillJoinWelcome(BaseModel):
    """Ask the bot to DM a freshly-joined participant so the bot lands in their
    chat list. `lang` selects the localized copy (falls back to Russian)."""
    lang: str | None = None

class BillDetailResponse(BaseModel):
    """Detailed bill response with items and participants"""
    id: int
    owner_id: int
    total_sum: float
    title: str | None
    payment_details: str | None
    split_type: str
    status: str
    currency: str = "uzs"
    unallocated_sum: float
    # Convenience aggregates so the client never re-derives money/counts.
    allocated_sum: float = 0
    paid_count: int = 0
    # What the others still owe the owner: the figure the home screen shows too.
    left_to_collect: float = 0
    created_at: UtcDatetime
    public_token: str
    expected_people: int | None = None
    # Made by the guided tour; meaningless outside it.
    is_demo: bool = False
    place: str | None = None
    has_receipt: bool = False
    is_ai_scanned: bool = False
    scan_quality: int | None = None
    # The grand total printed on the scanned receipt and whether the sum of the
    # AI-scanned items disagrees with it — a nudge to double-check the parse.
    # Reconciled across every receipt on the bill.
    receipt_total_sum: float | None = None
    scan_total_mismatch: bool = False
    # A bill can hold several receipts; each keeps its own items.
    receipts: list[ReceiptSummary] = []
    items: list[BillItemResponse]
    participants: list[BillParticipantResponse]

class VoiceHeardResponse(BaseModel):
    heard: str


class VoiceBillResponse(BaseModel):
    """What the owner said, and what it did to the bill."""
    heard: str
    added: int
    assigned: int
    # Lines left as they were: changing them would move a share already paid.
    held: list[str] = []
    # Names said that no seat could be found or laid for.
    unseated: list[str] = []
    bill: BillDetailResponse

class ScanFeedback(BaseModel):
    """A user's 1–5 rating of an AI scan's quality."""
    rating: int
    user_id: int


class DemoBillRequest(BaseModel):
    """The guided tour's language, so its receipt and friends read like the app,
    and the card it pretended to type in."""
    language: str | None = None
    payment_details: str | None = None


class BillPlaceUpdate(BaseModel):
    """Where the bill was; empty says it was nowhere in particular."""
    name: str | None = Field(default=None, max_length=80)


class BillPlaceResponse(BaseModel):
    place: str | None
