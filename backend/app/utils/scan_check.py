import json

from app.models import ReceiptSource
from app.utils.currency import from_tiins, to_tiins

# A gap smaller than one currency unit is rounding noise (percentage service /
# discount lines), not a mis-parsed line.
MISMATCH_TOLERANCE_TIINS = 100


def _receipt_total_tiins(llm_response: str | None) -> int | None:
    """The receipt's printed grand total (in tiins) taken from a task's stored
    parse JSON, or None when it is absent or unreadable."""
    if not llm_response:
        return None
    try:
        total = json.loads(llm_response).get("total_sum")
    except (ValueError, TypeError):
        return None
    if not isinstance(total, (int, float)) or isinstance(total, bool) or total <= 0:
        return None
    return to_tiins(total)


def reconcile_scan_many(receipt_tasks, items) -> tuple[float | None, bool]:
    """Same check across every receipt on the bill.

    With several receipts the printed totals add up, and so do the items each of
    them produced — a two-receipt bill should reconcile against the sum of both
    slips, not against whichever was scanned last. Receipts with no usable
    printed total (Soliq imports, unreadable parses) sit the check out entirely
    rather than dragging the total down.
    """
    total_tiins = 0
    scanned_sum = 0
    reconcilable = False

    for task in receipt_tasks or []:
        if task.source != ReceiptSource.PHOTO:
            continue
        printed = _receipt_total_tiins(task.llm_response)
        if printed is None:
            continue
        reconcilable = True
        total_tiins += printed
        scanned_sum += sum(i.item_sum for i in items if i.receipt_task_id == task.id)

    if not reconcilable:
        return None, False

    mismatch = abs(total_tiins - scanned_sum) > MISMATCH_TOLERANCE_TIINS
    return from_tiins(total_tiins), mismatch
