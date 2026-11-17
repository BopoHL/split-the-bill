"""Labels what the analytics count by: what each receipt line is, and where
each bill was run up.

Whatever is written or changed after labeling began is labeled on its own, a
batch a tick. The history before that waits for the admin to start it, and then
goes a batch a tick alongside. A bill's place is worked out once, after it has
had a moment for its scan to land; a new scan or a new title asks again.
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlmodel import Session, and_, or_, select

from app.models import Bill, BillItem, DishKind, DishLabel, ReceiptTask, dish_key
from app.services.app_settings import get_label_model
from app.services.labeling import PlaceQuestion, label_dishes, name_places
from app.services.labeling_control import UNPLACED, Cursor, HistoryState, LabelingControl, history_bills
from app.services.places import place_named

logger = logging.getLogger(__name__)

LINES_PER_TICK = 500
DISHES_PER_CALL = 80
BILLS_PER_CALL = 30
# A bill made a moment ago may still be waiting for its receipt to be read.
SETTLE = timedelta(minutes=2)
# A line is stamped as it is written but seen only once its transaction commits,
# maybe after a line stamped later. New lines are passed only once this old, so
# the cursor never steps over one still landing.
LANDING = timedelta(minutes=2)


@dataclass(frozen=True)
class Passed:
    """How far a batch of lines got: how many it went past, the last of them,
    and how many wordings it asked about."""

    lines: int
    cursor: Cursor | None
    asked: int


def run(session: Session, now: datetime | None = None) -> int:
    if not os.getenv("OPENAI_API_KEY"):
        return 0
    now = now or datetime.utcnow()
    control = LabelingControl(session)
    since = control.since(now)
    model = get_label_model(session)
    try:
        done = _label_new(session, control, model, since, now) + _label_history(session, control, model, since, now)
    except Exception as error:
        session.rollback()
        control.note_error(error, now)
        raise
    if done:
        control.note_labeled(now)
    return done


def _label_new(session: Session, control: LabelingControl, model: str, since: datetime, now: datetime) -> int:
    passed = _label_lines(session, model, control.cursor(since), before=now - LANDING)
    if passed.cursor:
        control.move_cursor(passed.cursor)
    recent = (*UNPLACED, Bill.updated_at >= since, Bill.created_at <= now - SETTLE)
    return passed.asked + _place_bills(session, model, now, recent)


def _label_history(session: Session, control: LabelingControl, model: str, since: datetime, now: datetime) -> int:
    history = control.history()
    if history is None or history.state is not HistoryState.RUNNING:
        return 0
    passed = _label_lines(session, model, history.cursor, before=since)
    placed = _place_bills(session, model, now, history_bills(since))
    control.advance_history(passed.cursor, passed.lines, placed, now)
    return passed.asked + placed


def _label_lines(session: Session, model: str, after: Cursor, before: datetime) -> Passed:
    """The lines after the cursor and before `before`, and the wordings among
    them nobody has labeled yet."""
    lines = session.exec(
        select(BillItem.id, BillItem.name, BillItem.updated_at)
        .where(
            or_(BillItem.updated_at > after.at, and_(BillItem.updated_at == after.at, BillItem.id > after.line_id)),
            BillItem.updated_at < before,
        )
        .order_by(BillItem.updated_at, BillItem.id)
        .limit(LINES_PER_TICK)
    ).all()
    if not lines:
        return Passed(lines=0, cursor=None, asked=0)

    known = set(session.exec(
        select(DishLabel.name_key).where(DishLabel.name_key.in_({dish_key(name) for _, name, _ in lines}))
    ).all())
    asking: dict[str, str] = {}
    passed, reached = 0, None
    for line_id, name, updated_at in lines:
        key = dish_key(name)
        if key and key not in known and key not in asking:
            if len(asking) == DISHES_PER_CALL:
                break
            asking[key] = name.strip()
        passed, reached = passed + 1, Cursor(at=updated_at, line_id=line_id)

    if asking:
        _keep_labels(session, model, asking, label_dishes(list(asking.values()), model))
    return Passed(lines=passed, cursor=reached, asked=len(asking))


def _keep_labels(session: Session, model: str, asking: dict[str, str], answers) -> None:
    kinds = {answer.kind for answer in answers if answer and answer.kind}
    named = set(session.exec(select(DishKind.key).where(DishKind.key.in_(kinds))).all()) if kinds else set()
    for key, answer in zip(asking, answers):
        if answer is None:
            continue
        session.add(DishLabel(name_key=key, group=answer.group, kind=answer.kind, model=model))
        if answer.kind and answer.names and answer.kind not in named:
            session.add(DishKind(key=answer.kind, ru=answer.names.ru, uz=answer.names.uz, en=answer.names.en))
            named.add(answer.kind)
    session.commit()


def _place_bills(session: Session, model: str, now: datetime, which: tuple) -> int:
    bills = session.exec(
        select(Bill)
        .where(*which)
        .order_by(Bill.id)
        .limit(BILLS_PER_CALL)
    ).all()
    if not bills:
        return 0

    scanned = _scanned_venues(session, [bill.id for bill in bills])
    questions = [PlaceQuestion(scanned=scanned.get(bill.id, []), title=bill.title) for bill in bills]
    askable = [index for index, question in enumerate(questions) if question.scanned or question.title]
    names = dict(zip(askable, name_places([questions[index] for index in askable], model))) if askable else {}

    for index, bill in enumerate(bills):
        name = names.get(index)
        found = {"place_id": place_named(session, name).id} if name else {}
        # Only if nobody worked it out meanwhile: the owner may have said where
        # the bill was while the model was being asked.
        session.execute(
            update(Bill)
            .where(Bill.id == bill.id, Bill.place_checked_at.is_(None))
            .values(place_checked_at=now, **found)
        )
    session.commit()
    return len(bills)


def _scanned_venues(session: Session, bill_ids: list[int]) -> dict[int, list[str]]:
    """The venue each bill's read receipts named: the place the model picked
    out, or the receipt's heading on scans read before it was asked to."""
    venues: dict[int, list[str]] = {}
    for bill_id, raw in session.exec(
        select(ReceiptTask.bill_id, ReceiptTask.llm_response)
        .where(ReceiptTask.bill_id.in_(bill_ids), ReceiptTask.llm_response.is_not(None))
        .order_by(ReceiptTask.id)
    ).all():
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            continue
        venue = parsed.get("place") or parsed.get("title") if isinstance(parsed, dict) else None
        if isinstance(venue, str) and venue.strip() and venue.strip() not in venues.get(bill_id, []):
            venues.setdefault(bill_id, []).append(venue.strip())
    return venues
