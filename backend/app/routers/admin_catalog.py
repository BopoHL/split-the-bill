"""What the analytics count by, from the admin panel: the places bills were run
up at, and what each receipt line was labelled as — with a way to correct a
label the model got wrong."""
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func
from sqlmodel import Session, select

from app.database import get_session
from app.models import Bill, BillItem, BillUser, DishGroup, DishKind, DishLabel, Place, dish_key
from app.schemas.admin_schemas import (
    AdminDishesPage,
    AdminDishKind,
    AdminDishLabelUpdate,
    AdminDishRow,
    AdminPlaceRow,
    AdminPlacesPage,
)
from app.utils.admin_auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# Who corrected a label, in place of the model's name.
CORRECTED_BY = "admin"
KIND_SHAPE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
# What every bill counted here is: not deleted, not the tour's demo.
COUNTED = (Bill.deleted_at.is_(None), Bill.is_demo.is_(False))
# A receipt line by the key its label is kept under: trimmed, lowercased, cut to 200.
LINE_KEY = func.substr(func.lower(func.trim(BillItem.name)), 1, 200)


def _contains(column, text: str):
    return func.lower(column).contains(text.strip().lower(), autoescape=True)


@router.get("/places", response_model=AdminPlacesPage)
def list_places(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """The places, the most used first."""
    conditions = [_contains(Place.name, q)] if q and q.strip() else []
    total = session.exec(select(func.count(Place.id)).where(*conditions)).one()
    bills = func.count(func.distinct(Bill.id))
    rows = session.exec(
        select(
            Place,
            bills,
            func.count(func.distinct(BillUser.user_id)),
            func.min(Bill.created_at),
            func.max(Bill.created_at),
        )
        .outerjoin(Bill, and_(Bill.place_id == Place.id, *COUNTED))
        .outerjoin(BillUser, BillUser.bill_id == Bill.id)
        .where(*conditions)
        .group_by(Place.id)
        .order_by(bills.desc(), Place.name)
        .offset(offset)
        .limit(limit)
    ).all()
    return AdminPlacesPage(
        items=[
            AdminPlaceRow(id=place.id, name=place.name, bills=count, people=people, first_bill_at=first, last_bill_at=last)
            for place, count, people, first, last in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/dishes", response_model=AdminDishesPage)
def list_dishes(
    q: str | None = None,
    group: str | None = None,
    kind: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """Every wording labelled so far, the most frequent on receipts first."""
    conditions = []
    if q and q.strip():
        conditions.append(_contains(DishLabel.name_key, q))
    if group:
        conditions.append(DishLabel.group == group)
    if kind:
        conditions.append(DishLabel.kind == kind)

    lines = (
        select(LINE_KEY.label("name_key"), func.count(BillItem.id).label("lines"))
        .join(Bill, Bill.id == BillItem.bill_id)
        .where(*COUNTED)
        .group_by(LINE_KEY)
        .subquery()
    )
    used = func.coalesce(lines.c.lines, 0)

    total = session.exec(select(func.count()).select_from(DishLabel).where(*conditions)).one()
    rows = session.exec(
        select(DishLabel, DishKind.ru, used)
        .outerjoin(DishKind, DishKind.key == DishLabel.kind)
        .outerjoin(lines, lines.c.name_key == DishLabel.name_key)
        .where(*conditions)
        .order_by(used.desc(), DishLabel.name_key)
        .offset(offset)
        .limit(limit)
    ).all()
    return AdminDishesPage(
        items=[_dish_row(label, kind_name, count) for label, kind_name, count in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _dish_row(label: DishLabel, kind_name: str | None, lines: int) -> AdminDishRow:
    return AdminDishRow(
        name_key=label.name_key,
        group=label.group,
        kind=label.kind,
        kind_name=kind_name,
        model=label.model,
        lines=lines,
        updated_at=label.updated_at,
    )


@router.patch("/dishes", response_model=AdminDishRow)
def correct_dish(payload: AdminDishLabelUpdate, session: Session = Depends(get_session)):
    """Say what a wording really is. The labelling job never asks again about a
    wording it knows, so the correction stays."""
    label = session.get(DishLabel, dish_key(payload.name_key))
    if not label:
        raise HTTPException(status_code=404, detail="No such dish")
    if payload.group not in {group.value for group in DishGroup}:
        raise HTTPException(status_code=400, detail=f"Unknown group «{payload.group}»")
    kind = session.get(DishKind, payload.kind) if payload.kind else None
    if payload.kind and not kind:
        raise HTTPException(status_code=400, detail=f"Unknown kind «{payload.kind}»")
    label.group = payload.group
    label.kind = payload.kind
    label.model = CORRECTED_BY
    session.add(label)
    session.commit()
    session.refresh(label)
    lines = session.exec(
        select(func.count(BillItem.id))
        .join(Bill, Bill.id == BillItem.bill_id)
        .where(LINE_KEY == label.name_key, *COUNTED)
    ).one()
    return _dish_row(label, kind.ru if kind else None, lines)


@router.get("/dish-kinds", response_model=list[AdminDishKind])
def list_dish_kinds(session: Session = Depends(get_session)):
    return session.exec(select(DishKind).order_by(DishKind.ru)).all()


@router.post("/dish-kinds", response_model=AdminDishKind, status_code=201)
def create_dish_kind(payload: AdminDishKind, session: Session = Depends(get_session)):
    """A kind the model has not named yet, in every language the app speaks."""
    key = payload.key.strip().lower()
    if not KIND_SHAPE.match(key):
        raise HTTPException(status_code=400, detail="A kind is 2 to 40 latin letters, digits or _")
    names = [name.strip() for name in (payload.ru, payload.uz, payload.en)]
    if not all(names) or any(len(name) > 60 for name in names):
        raise HTTPException(status_code=400, detail="A kind is named in ru, uz and en, up to 60 letters each")
    if session.get(DishKind, key):
        raise HTTPException(status_code=409, detail="This kind already exists")
    made = DishKind(key=key, ru=names[0], uz=names[1], en=names[2])
    session.add(made)
    session.commit()
    session.refresh(made)
    return made
