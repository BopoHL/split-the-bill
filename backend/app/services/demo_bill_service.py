import json
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path

from fastapi import HTTPException
from sqlmodel import select

from app.models import Bill, BillItem, PaymentMethod, SplitType, User
from app.notifier import notifier
from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.schemas.bill_schemas import BillCreate, BillDetailResponse
from app.services.bill_core_service import BillCoreService
from app.services.bill_item_service import BillItemService
from app.utils import crypto
from app.utils.bot_copy import resolve_language
from app.utils.currency import to_tiins

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "assets" / "demo_bill.json"


@dataclass(frozen=True)
class DemoItem:
    name: str
    price: float


@dataclass(frozen=True)
class DemoFixture:
    title: str
    currency: str
    friends: tuple[str, ...]
    items: tuple[DemoItem, ...]


@cache
def _raw_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def demo_fixture(language: str | None) -> DemoFixture:
    """The prepared receipt the tour «scans», in the newcomer's language."""
    raw = _raw_fixture()
    lang = resolve_language(language)
    return DemoFixture(
        title=raw["title"][lang],
        currency=raw["currency"],
        friends=tuple(raw["friends"][lang]),
        items=tuple(DemoItem(name=item["name"][lang], price=item["price"]) for item in raw["items"]),
    )


class DemoBillService:
    """The bill the guided tour walks a newcomer through.

    It is a real bill, so every screen and every sum in the tour is the one the
    person will meet later. Only what the tour cannot do for real is staged: the
    receipt comes from a fixture instead of a scan, the card it «types in» never
    joins the person's saved ones, and the friends it «invites» sit down as named
    guests without anybody being messaged.
    """

    def __init__(self, bill_repo: BillRepository, user_repo: UserRepository):
        self.bill_repo = bill_repo
        self.core = BillCoreService(bill_repo, user_repo)
        self.items = BillItemService(bill_repo, user_repo)

    def create(self, owner: User, language: str | None, payment_details: str | None = None) -> BillDetailResponse:
        """A fresh demo bill, as if its receipt had just been scanned.

        A tour left halfway leaves its bill behind; starting another one clears
        it, so a person never has more than one."""
        self._erase_all(owner.id)
        fixture = demo_fixture(language)

        created = self.core.create_bill(
            BillCreate(
                owner_id=owner.id,
                total_sum=0,
                title=fixture.title,
                expected_people=len(fixture.friends) + 1,
                include_owner=True,
                currency=fixture.currency,
            ),
            is_demo=True,
        )

        session = self.bill_repo.session
        total = 0
        for item in fixture.items:
            price = to_tiins(item.price)
            total += price
            session.add(BillItem(bill_id=created.id, name=item.name, price=price, count=1, item_sum=price))

        # Where a scanned receipt starts from: the items are the total, nobody
        # has taken anything yet, and people split by dishes.
        bill = self.bill_repo.get_by_id(created.id)
        bill.total_sum = total
        bill.unallocated_sum = total
        bill.split_type = SplitType.BY_ITEMS
        bill.payment_method_id = self._staged_card(owner.id, payment_details)
        session.add(bill)
        session.commit()
        self.items.recalculate_by_items(bill.id)

        return self.core.get_bill_details(bill.id)

    def seat_friends(self, bill_id: int, owner_id: int, language: str | None) -> BillDetailResponse:
        """The invite «worked»: the empty seats get the fixture's friends."""
        bill = self._own_demo(bill_id, owner_id)
        self.core.validator.ensure_bill_open(bill)

        empty_seats = [
            seat for seat in self.bill_repo.get_participants_by_bill_id(bill_id)
            if seat.user_id is None and not seat.guest_name
        ]
        session = self.bill_repo.session
        for seat, name in zip(empty_seats, demo_fixture(language).friends):
            seat.guest_name = name
            session.add(seat)
        session.commit()

        notifier.broadcast(bill_id, "REFRESH")
        return self.core.get_bill_details(bill_id)

    def erase(self, bill_id: int, owner_id: int) -> None:
        self._erase(self._own_demo(bill_id, owner_id))

    def _staged_card(self, owner_id: int, value: str | None) -> int | None:
        """The card on the demo bill, hidden from the start: the bill shows it,
        the person's own picker never offers it."""
        value = (value or "").strip()
        if not value:
            return None
        card = PaymentMethod(user_id=owner_id, enc_value=crypto.encrypt(value), deleted_at=datetime.utcnow())
        self.bill_repo.session.add(card)
        self.bill_repo.session.flush()
        return card.id

    def _erase(self, bill: Bill) -> None:
        card = self.bill_repo.session.get(PaymentMethod, bill.payment_method_id) if bill.payment_method_id else None
        self.core.erase(bill)
        if card is not None and card.deleted_at is not None and not self._card_in_use(card.id):
            self.bill_repo.session.delete(card)
            self.bill_repo.session.commit()

    def _card_in_use(self, card_id: int) -> bool:
        return self.bill_repo.session.exec(select(Bill.id).where(Bill.payment_method_id == card_id)).first() is not None

    def _own_demo(self, bill_id: int, owner_id: int) -> Bill:
        """Only the owner's demo bill — never a real one, whatever id is sent."""
        bill = self.bill_repo.get_by_id(bill_id)
        if bill is None or not bill.is_demo or bill.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="Demo bill not found")
        return bill

    def _erase_all(self, owner_id: int) -> None:
        leftovers = self.bill_repo.session.exec(
            select(Bill).where(Bill.owner_id == owner_id, Bill.is_demo.is_(True))
        ).all()
        for bill in leftovers:
            self._erase(bill)
