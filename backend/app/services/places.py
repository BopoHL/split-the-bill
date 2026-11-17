"""Where a bill was run up: one row per place name, shared by every bill there."""
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models import Bill, Place, place_key
from app.repositories.bill_repo import BillRepository
from app.services.labeling import PLACE_NAME_MAX

RECENT_PLACES = 20


def place_named(session: Session, name: str) -> Place:
    """The place called this, made the first time anyone names it."""
    cleaned = " ".join(name.split())[:PLACE_NAME_MAX]
    key = place_key(cleaned)
    place = session.exec(select(Place).where(Place.name_key == key)).first()
    if place is None:
        place = Place(name=cleaned, name_key=key)
        session.add(place)
        session.flush()
    return place


def name_of(session: Session, bill: Bill) -> str | None:
    place = session.get(Place, bill.place_id) if bill.place_id else None
    return place.name if place else None


def set_place(session: Session, bill: Bill, requester_id: int, name: str | None, now: datetime) -> str | None:
    """The owner says where the bill was — or that it was nowhere in particular.
    Either way the labeling job leaves it alone from now on."""
    if bill.owner_id != requester_id:
        raise HTTPException(status_code=403, detail="Only the owner can set the place")
    cleaned = " ".join((name or "").split())
    bill.place_id = place_named(session, cleaned).id if cleaned else None
    bill.place_checked_at = now
    bill.place_by_owner = True
    session.add(bill)
    session.commit()
    return name_of(session, bill)


def recent_places(session: Session, user_id: int) -> list[str]:
    last_visit = func.max(Bill.created_at)
    return list(session.exec(
        select(Place.name)
        .join(Bill, Bill.place_id == Place.id)
        .where(*BillRepository.user_bill_conditions(user_id, None, None, None))
        .group_by(Place.id, Place.name)
        .order_by(last_visit.desc())
        .limit(RECENT_PLACES)
    ).all())
