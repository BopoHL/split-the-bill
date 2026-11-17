"""Field types the API's schemas share."""
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def _with_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


# A moment the database keeps as naive UTC, sent with its offset so that a
# client reads it on its own clock instead of taking it for local time.
UtcDatetime = Annotated[datetime, AfterValidator(_with_utc)]
