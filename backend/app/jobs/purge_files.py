"""Reclaims disk space taken by old receipt photos.

The bills, items and participants stay forever — they're small and people look
back at them. Photos are the part that actually grows, and they stop being
useful once a bill is settled, so they're cleared by age rather than by deletion.
"""
import logging
import os

from sqlmodel import Session

from app.repositories.bill_repo import BillRepository
from app.repositories.user_repo import UserRepository
from app.services.bill_core_service import BillCoreService

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 30
# Pro keeps them three times as long.
DEFAULT_PRO_TTL_DAYS = 90


def _days(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, default)))
    except ValueError:
        return default


def ttl_days() -> int:
    return _days("RECEIPT_FILES_TTL_DAYS", DEFAULT_TTL_DAYS)


def pro_ttl_days() -> int:
    return max(ttl_days(), _days("PRO_RECEIPT_FILES_TTL_DAYS", DEFAULT_PRO_TTL_DAYS))


def run(session: Session) -> int:
    """Delete photos older than the TTL on bills that are closed or deleted —
    the longer Pro one where the bill's owner has Pro."""
    service = BillCoreService(BillRepository(session), UserRepository(session))
    removed = service.purge_receipt_files(older_than_days=ttl_days(), pro_older_than_days=pro_ttl_days())
    if removed:
        logger.info("Purged %s receipt photo(s)", removed)
    return removed
