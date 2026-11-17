from pydantic import BaseModel


class PaymentMethodCreate(BaseModel):
    """Schema for saving a new payment method."""
    value: str
    label: str | None = None


class PaymentMethodResponse(BaseModel):
    """Schema for a saved payment method (value decrypted for its owner)."""
    id: int
    label: str | None
    value: str
