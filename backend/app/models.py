from enum import Enum
from sqlalchemy import Index, BigInteger, func
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class SplitType(str, Enum):
    """Enum for different ways to split a bill"""
    MANUAL = "manual"
    EQUALLY = "equally"


class BillStatus(str, Enum):
    """Enum for bill statuses"""
    OPEN = "open"
    PAID = "paid"
    CLOSED = "closed"


class TimestampModel(SQLModel):
    """Base model for adding created_at and updated_at timestamps"""
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"server_default": func.now()}
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now()
        }
    )


class User(TimestampModel, table=True):
    """User model for Telegram users"""
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(unique=True, index=True, sa_type=BigInteger)
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    
    # Relationships
    owned_bills: list["Bill"] = Relationship(back_populates="owner")
    bill_participations: list["BillUser"] = Relationship(back_populates="user")


class Bill(TimestampModel, table=True):
    """Bill model for managing split bills"""
    __tablename__ = "bills"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="users.id")
    total_sum: int = Field(default=0, sa_type=BigInteger, description="Total amount in smallest currency unit (cents/kopeks/tiins)")
    unallocated_sum: int = Field(default=0, sa_type=BigInteger, description="Remaining unallocated amount")
    title: Optional[str] = None
    payment_details: Optional[str] = Field(description="Payment details like card number")
    is_closed: bool = Field(default=False)
    split_type: str = Field(default=SplitType.MANUAL)
    status: str = Field(default=BillStatus.OPEN)
    
    # Relationships
    owner: User = Relationship(back_populates="owned_bills")
    items: list["BillItem"] = Relationship(back_populates="bill", cascade_delete=True)
    participants: list["BillUser"] = Relationship(back_populates="bill", cascade_delete=True)


class BillItem(TimestampModel, table=True):
    """Individual items in a bill"""
    __tablename__ = "bill_items"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bills.id", index=True)
    name: str
    price: int = Field(sa_type=BigInteger, sa_column_kwargs={"server_default": "0"}, description="Price in smallest currency unit")
    count: int = Field(default=1)
    item_sum: int = Field(default=0, sa_type=BigInteger, sa_column_kwargs={"server_default": "0"}, description="Total sum for this item (price * count)")
    assigned_to_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    # Relationships
    bill: Bill = Relationship(back_populates="items")
    assigned_to: Optional[User] = Relationship()


class BillUser(TimestampModel, table=True):
    """Participants in a bill (users or guests)"""
    __tablename__ = "bills_users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    bill_id: int = Field(foreign_key="bills.id")
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    guest_name: Optional[str] = Field(description="Name for non-registered guests")
    allocated_amount: int = Field(default=0, sa_type=BigInteger, description="Amount allocated to this participant")
    is_paid: bool = Field(default=False)

    __table_args__ = (
        # Составной индекс: ускоряет поиск по паре bill_id + user_id
        # и гарантирует, что пользователь не добавится в один счет дважды
        Index("ix_bill_user_unique", "bill_id", "user_id", unique=True),
    )
    
    # Relationships
    bill: Bill = Relationship(back_populates="participants")
    user: Optional[User] = Relationship(back_populates="bill_participations")
