from datetime import datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, HttpUrl, field_validator
from app.models import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    amount: Decimal
    currency: Currency
    description: str | None = None
    metadata: dict[str, Any] | None = None
    webhook_url: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v


class PaymentResponse(BaseModel):
    payment_id: str
    status: PaymentStatus
    created_at: datetime

    model_config = {"from_attributes": True}
