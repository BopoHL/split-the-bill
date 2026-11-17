"""Reconciliation of the receipts' printed totals against the items they produced.

This surfaces the "sum of items doesn't match the receipt" nudge to the owner,
so a mis-parsed line (e.g. a quantity folded into a price) can't pass silently.
A bill can hold several receipts, so the printed totals add up and so do their
items. Only PHOTO scans take part; Soliq QR imports are already structured.
"""
import json
from types import SimpleNamespace

from app.models import ReceiptSource
from app.utils.currency import to_tiins
from app.utils.scan_check import reconcile_scan_many


def _task(total, source=ReceiptSource.PHOTO, task_id=1):
    return SimpleNamespace(
        id=task_id, source=source, llm_response=json.dumps({"total_sum": total})
    )


def _item(amount, receipt_task_id=1):
    return SimpleNamespace(item_sum=to_tiins(amount), receipt_task_id=receipt_task_id)


def test_no_task_nothing_to_reconcile():
    assert reconcile_scan_many([], []) == (None, False)


def test_soliq_never_reconciles():
    # QR imports come structured from the API — they must never trip the flag.
    assert reconcile_scan_many([_task(300, source=ReceiptSource.SOLIQ_QR)], [_item(999)]) == (None, False)


def test_items_match_printed_total():
    total, mismatch = reconcile_scan_many([_task(300)], [_item(200), _item(100)])
    assert total == 300
    assert mismatch is False


def test_mis_parsed_line_flags_mismatch():
    # The real Fish and Bread case: a "3 204 000" cheeseburger line read as one
    # unit at 320 400 leaves the items 116 400 over the printed 457 700.
    items = [_item(320400), _item(89000), _item(57000), _item(48000), _item(59700)]
    total, mismatch = reconcile_scan_many([_task(457700)], items)
    assert total == 457700
    assert mismatch is True


def test_only_this_tasks_items_count():
    # A manual line (None) and another scan's item must not shift the sum.
    _, mismatch = reconcile_scan_many(
        [_task(300, task_id=7)],
        [_item(300, receipt_task_id=7), _item(50, receipt_task_id=None), _item(80, receipt_task_id=8)],
    )
    assert mismatch is False


def test_unreadable_or_missing_total():
    photo = ReceiptSource.PHOTO
    assert reconcile_scan_many([SimpleNamespace(id=1, source=photo, llm_response="x")], []) == (None, False)
    assert reconcile_scan_many([SimpleNamespace(id=1, source=photo, llm_response=None)], []) == (None, False)


def test_several_receipts_reconcile_against_their_combined_totals():
    """Two slips on one bill: the check is over both, not the latest one."""
    total, mismatch = reconcile_scan_many(
        [_task(300, task_id=1), _task(120, task_id=2)],
        [_item(300, receipt_task_id=1), _item(120, receipt_task_id=2)],
    )
    assert total == 420
    assert mismatch is False


def test_a_receipt_without_a_printed_total_sits_the_check_out():
    """It must not drag the combined total down and fake a mismatch."""
    total, mismatch = reconcile_scan_many(
        [_task(300, task_id=1), SimpleNamespace(id=2, source=ReceiptSource.PHOTO, llm_response=None)],
        [_item(300, receipt_task_id=1), _item(120, receipt_task_id=2)],
    )
    assert total == 300
    assert mismatch is False
