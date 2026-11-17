from sqlmodel import Session, select
from app.models import FileAsset


class FileAssetRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, asset: FileAsset) -> FileAsset:
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def list_by_bill(self, bill_id: int) -> list[FileAsset]:
        """Every photo attached to the bill, oldest first — one per receipt."""
        return self.session.exec(
            select(FileAsset)
            .where(FileAsset.bill_id == bill_id)
            .order_by(FileAsset.id)
        ).all()

    def get_by_task_id(self, task_id: int) -> FileAsset | None:
        return self.session.exec(
            select(FileAsset).where(FileAsset.receipt_task_id == task_id)
        ).first()

    def get_first_by_bill_id(self, bill_id: int) -> FileAsset | None:
        """The bill's first photo — used for the Telegram invite preview, which
        can only show one."""
        return self.session.exec(
            select(FileAsset)
            .where(FileAsset.bill_id == bill_id)
            .order_by(FileAsset.id)
            .limit(1)
        ).first()
