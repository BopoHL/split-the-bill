import asyncio
import os
import uuid

from fastapi import UploadFile

from app.utils.images import compress_image
from app.repositories.receipt_repo import ReceiptRepository
from app.repositories.file_repo import FileAssetRepository
from app.models import ReceiptTask, ReceiptTaskStatus, ReceiptSource, FileAsset, StorageType

STORAGE_DIR = "storage/receipts"


class ReceiptService:
    def __init__(
        self,
        repo: ReceiptRepository,
        file_repo: FileAssetRepository | None = None,
    ):
        self.repo = repo
        self.file_repo = file_repo
        os.makedirs(STORAGE_DIR, exist_ok=True)

    async def save_receipt(
        self,
        file: UploadFile,
        user_id: int = None,
        bill_id: int | None = None,
        owns_bill: bool = False,
    ) -> ReceiptTask:
        # Decoding and re-encoding a phone photo is about a CPU-second; run on the
        # event loop, it held up every other request and stream for that long.
        return await asyncio.to_thread(
            self.save_receipt_bytes,
            await file.read(),
            user_id=user_id,
            bill_id=bill_id,
            original_name=file.filename,
            owns_bill=owns_bill,
        )

    def save_receipt_bytes(
        self,
        raw: bytes,
        user_id: int = None,
        bill_id: int | None = None,
        original_name: str | None = None,
        notify_chat_id: int | None = None,
        owns_bill: bool = False,
    ) -> ReceiptTask:
        """Store a receipt image we already hold in memory.

        An upload arrives as an UploadFile, but a photo sent to the bot arrives
        as a file_id we download ourselves — same bytes, no request to wrap them
        in.
        """
        data, ext, mime = self._compress(raw)

        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(STORAGE_DIR, unique_filename)
        session = self.repo.session

        try:
            with open(file_path, "wb") as buffer:
                buffer.write(data)

            # Task and asset are one transaction: a failed asset insert must not
            # leave a pending task that the startup worker later processes.
            task = ReceiptTask(
                user_id=user_id,
                filename=unique_filename,
                status=ReceiptTaskStatus.PENDING,
                bill_id=bill_id,
                notify_chat_id=notify_chat_id,
                owns_bill=owns_bill,
            )
            session.add(task)
            session.flush()

            if self.file_repo is not None:
                if self.file_repo.session is not session:
                    raise RuntimeError("Receipt repositories must share a session")
                session.add(FileAsset(
                    user_id=user_id,
                    bill_id=bill_id,
                    receipt_task_id=task.id,
                    original_name=original_name,
                    path=file_path,
                    size=len(data),
                    mime_type=mime,
                    storage_type=StorageType.LOCAL,
                ))

            session.commit()
            session.refresh(task)
            return task
        except Exception:
            session.rollback()
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                pass
            raise

    def create_qr_task(
        self,
        source_url: str,
        user_id: int | None = None,
        bill_id: int | None = None,
        owns_bill: bool = False,
    ) -> ReceiptTask:
        """Create a task that imports a bill from a Soliq QR check link.

        No image is stored — the worker fetches `source_url` and reads the items
        out of the check page HTML, then enriches the (already created) bill.
        """
        task = ReceiptTask(
            user_id=user_id,
            filename=None,
            source=ReceiptSource.SOLIQ_QR,
            source_url=source_url,
            status=ReceiptTaskStatus.PENDING,
            bill_id=bill_id,
            owns_bill=owns_bill,
        )
        return self.repo.create_task(task)

    async def attach_to_bill(
        self, file: UploadFile, bill_id: int, user_id: int | None = None
    ) -> FileAsset:
        """Store an image and link it to an existing bill, WITHOUT OCR/AI parsing.

        It still becomes a proper receipt on the bill — a completed task with no
        items behind it. A photo the user chose not to have recognised is a
        receipt like any other: it shows up in the list, it can be opened, and it
        can be removed. Leaving it as a bare file made it invisible.
        """
        if self.file_repo is None:
            raise RuntimeError("file_repo is required to attach a receipt")

        raw = await file.read()
        data, ext, mime = await asyncio.to_thread(self._compress, raw)

        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(STORAGE_DIR, unique_filename)
        try:
            with open(file_path, "wb") as buffer:
                buffer.write(data)

            task = self.repo.create_task(
                ReceiptTask(
                    user_id=user_id,
                    bill_id=bill_id,
                    filename=unique_filename,
                    source=ReceiptSource.MANUAL_PHOTO,
                    status=ReceiptTaskStatus.COMPLETED,
                )
            )

            return self.file_repo.create(
                FileAsset(
                    user_id=user_id,
                    bill_id=bill_id,
                    receipt_task_id=task.id,
                    original_name=file.filename,
                    path=file_path,
                    size=len(data),
                    mime_type=mime,
                    storage_type=StorageType.LOCAL,
                )
            )
        except Exception:
            self.file_repo.session.rollback()
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _compress(raw: bytes) -> tuple[bytes, str, str]:
        """An undecodable upload is still kept as-is: the worker then fails it
        with a readable message, which beats losing the photo at upload time."""
        return compress_image(raw) or (raw, ".bin", "application/octet-stream")

    def get_task(self, task_id: int) -> ReceiptTask:
        return self.repo.get_task(task_id)

    def get_image_path(self, filename: str) -> str:
        return os.path.join(STORAGE_DIR, filename)
