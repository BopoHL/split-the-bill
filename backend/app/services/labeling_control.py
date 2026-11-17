"""Where labeling stands.

From the moment the job first runs, whatever is written or changed is labeled
on its own, a few minutes later at most. What was there before — the history —
is labeled only once the admin asks for it, and can be paused and resumed; how
far it has got is kept here, next to how the job is doing.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel
from sqlmodel import Session, func, select

from app.models import AppSetting, Bill, BillItem
from app.services.app_settings import get_setting, set_setting

SINCE_KEY = "labeling_since"
CURSOR_KEY = "labeling_cursor"
HISTORY_KEY = "labeling_history"
STATUS_KEY = "labeling_status"


class Cursor(BaseModel):
    """The last receipt line passed: lines are taken in (updated_at, id) order."""

    at: datetime
    line_id: int = 0


class HistoryState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"


class History(BaseModel):
    state: HistoryState
    started_at: datetime
    finished_at: datetime | None = None
    cursor: Cursor
    lines_total: int
    lines_done: int = 0
    bills_total: int
    bills_done: int = 0


class Status(BaseModel):
    last_labeled_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None


class AlreadyRunning(Exception):
    """The history is being labeled already."""


# Bills whose place nobody has worked out yet.
UNPLACED = (Bill.place_checked_at.is_(None), Bill.deleted_at.is_(None), Bill.is_demo.is_(False))


def history_bills(since: datetime) -> tuple:
    """Those from before labeling began."""
    return (*UNPLACED, Bill.updated_at < since)


class LabelingControl:
    def __init__(self, session: Session):
        self.session = session

    def since(self, now: datetime) -> datetime:
        """When labeling began; the first to ask fixes it."""
        stored = get_setting(self.session, SINCE_KEY)
        if stored:
            return datetime.fromisoformat(stored)
        set_setting(self.session, SINCE_KEY, now.isoformat())
        return now

    def started(self) -> datetime | None:
        stored = get_setting(self.session, SINCE_KEY)
        return datetime.fromisoformat(stored) if stored else None

    # ── New data ─────────────────────────────────────────────────────────────

    def cursor(self, since: datetime) -> Cursor:
        stored = get_setting(self.session, CURSOR_KEY)
        return Cursor.model_validate_json(stored) if stored else Cursor(at=since)

    def move_cursor(self, cursor: Cursor) -> None:
        set_setting(self.session, CURSOR_KEY, cursor.model_dump_json())

    # ── History ──────────────────────────────────────────────────────────────

    def history(self) -> History | None:
        # Read from the database, not the session: the admin may have paused
        # the run while a tick was going through it.
        stored = self.session.exec(select(AppSetting.value).where(AppSetting.key == HISTORY_KEY)).first()
        return History.model_validate_json(stored) if stored else None

    def start_history(self, now: datetime) -> History:
        """Resume a paused run, or start over once the last one is done."""
        current = self.history()
        if current and current.state is HistoryState.RUNNING:
            raise AlreadyRunning
        if current and current.state is HistoryState.PAUSED:
            return self._keep(current.model_copy(update={"state": HistoryState.RUNNING}))
        since = self.since(now)
        return self._keep(History(
            state=HistoryState.RUNNING,
            started_at=now,
            cursor=Cursor(at=datetime.min),
            lines_total=self.session.exec(select(func.count(BillItem.id)).where(BillItem.updated_at < since)).one(),
            bills_total=self.session.exec(select(func.count(Bill.id)).where(*history_bills(since))).one(),
        ))

    def pause_history(self) -> History | None:
        current = self.history()
        if current is None or current.state is not HistoryState.RUNNING:
            return current
        return self._keep(current.model_copy(update={"state": HistoryState.PAUSED}))

    def advance_history(self, cursor: Cursor | None, lines: int, bills: int, now: datetime) -> None:
        """Count what a tick got through. Nothing left to get through ends the run."""
        current = self.history()
        if current is None:
            return
        update = {"lines_done": current.lines_done + lines, "bills_done": current.bills_done + bills}
        if cursor:
            update["cursor"] = cursor
        if not lines and not bills and current.state is HistoryState.RUNNING:
            update |= {"state": HistoryState.DONE, "finished_at": now}
        self._keep(current.model_copy(update=update))

    def _keep(self, history: History) -> History:
        set_setting(self.session, HISTORY_KEY, history.model_dump_json())
        return history

    # ── How it is going ──────────────────────────────────────────────────────

    def status(self) -> Status:
        stored = get_setting(self.session, STATUS_KEY)
        return Status.model_validate_json(stored) if stored else Status()

    def note_labeled(self, now: datetime) -> None:
        self._note(self.status().model_copy(update={"last_labeled_at": now, "last_error": None}))

    def note_error(self, error: Exception, now: datetime) -> None:
        self._note(self.status().model_copy(update={"last_error": str(error)[:500], "last_error_at": now}))

    def _note(self, status: Status) -> None:
        set_setting(self.session, STATUS_KEY, status.model_dump_json())
