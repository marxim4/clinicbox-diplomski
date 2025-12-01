from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.types import PositiveFloat

from ..enums import CashTransactionType, TransactionStatus


class CreateCashboxRequestSchema(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


class UpdateCashboxRequestSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one(self):
        if self.name is None and self.description is None and self.is_active is None:
            raise ValueError("Provide at least one field to update.")
        return self

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        if not v2:
            raise ValueError("name must not be empty if provided")
        return v2

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


class CashboxResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cashbox_id: int
    clinic_id: int
    name: str
    description: Optional[str]
    is_active: bool


class CashboxBalanceResponseSchema(BaseModel):
    total_in: float
    total_out: float
    total_adjustment: float
    net: float


class CreateCashTransactionRequestSchema(BaseModel):
    cashbox_id: int
    type: CashTransactionType

    amount: float
    category_id: Optional[int] = None
    payment_id: Optional[int] = None
    tip_id: Optional[int] = None
    tip_payout_id: Optional[int] = None

    note: Optional[str] = None
    occurred_at: Optional[datetime] = None

    @field_validator("amount")
    @classmethod
    def normalize_amount(cls, v: float) -> float:
        if v == 0:
            raise ValueError("amount must not be zero")
        return round(v, 2)

    @model_validator(mode="after")
    def validate_logic(self):
        # For IN / OUT, force positive amount
        if self.type in (CashTransactionType.IN, CashTransactionType.OUT):
            if self.amount <= 0:
                raise ValueError("amount must be positive for IN/OUT")
        # For ADJUSTMENT we allow positive or negative
        return self


class CashTransactionResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tx_id: int
    clinic_id: int
    cashbox_id: int
    type: CashTransactionType

    payment_id: Optional[int]
    category_id: Optional[int]
    tip_id: Optional[int]
    tip_payout_id: Optional[int]

    amount: float
    occurred_at: datetime
    status: TransactionStatus
    note: Optional[str]

    created_by: int
    approved_by: Optional[int]
