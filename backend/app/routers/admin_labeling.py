"""Labeling from the admin panel: how the job is doing, and the run through
the history, which only starts when the admin says so."""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.database import get_session
from app.schemas.admin_schemas import AdminLabeling, AdminLabelingHistory
from app.services.app_settings import get_label_model
from app.services.labeling_control import AlreadyRunning, LabelingControl
from app.utils.admin_auth import require_admin

router = APIRouter(prefix="/admin/labeling", tags=["admin"], dependencies=[Depends(require_admin)])


def _labeling(session: Session) -> AdminLabeling:
    control = LabelingControl(session)
    status = control.status()
    history = control.history()
    return AdminLabeling(
        key_set=bool(os.getenv("OPENAI_API_KEY")),
        model=get_label_model(session),
        since=control.started(),
        last_labeled_at=status.last_labeled_at,
        last_error=status.last_error,
        last_error_at=status.last_error_at,
        history=AdminLabelingHistory(
            state=history.state.value,
            started_at=history.started_at,
            finished_at=history.finished_at,
            lines_done=min(history.lines_done, history.lines_total),
            lines_total=history.lines_total,
            bills_done=min(history.bills_done, history.bills_total),
            bills_total=history.bills_total,
        ) if history else None,
    )


@router.get("", response_model=AdminLabeling)
def read_labeling(session: Session = Depends(get_session)):
    return _labeling(session)


@router.post("/history", response_model=AdminLabeling)
def start_history(session: Session = Depends(get_session)):
    """Start labeling the history, or resume it where it was paused. The job
    takes it up on its next tick."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=409, detail="OPENAI_API_KEY is not set")
    try:
        LabelingControl(session).start_history(datetime.utcnow())
    except AlreadyRunning:
        raise HTTPException(status_code=409, detail="The history is being labeled already")
    return _labeling(session)


@router.post("/history/pause", response_model=AdminLabeling)
def pause_history(session: Session = Depends(get_session)):
    LabelingControl(session).pause_history()
    return _labeling(session)
