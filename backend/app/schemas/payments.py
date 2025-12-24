from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ..enums import PaymentMethod


class CreatePaymentRequestSchema(BaseModel):
    plan_id: Optional[int] = None
    installment_id: Optional[int] = None

    doctor_id: Optional[int] = None

    amount: Optional[float] = None
    tip_amount: float = 0

    method: Optional[PaymentMethod] = None
    cashbox_id: Optional[int] = None

    pin: Optional[str] = None
    acting_user_id: Optional[int] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0:
                raise ValueError("Amount cannot be negative")
            return round(v, 2)
        return v

    @model_validator(mode="after")
    def validate_logic(self):
        a = float(self.amount) if self.amount is not None else 0
        t = float(self.tip_amount or 0)

        if a <= 0 and t <= 0:
            raise ValueError("Either amount or tip_amount must be greater than zero.")

        if a > 0 and not (self.plan_id or self.installment_id):
            raise ValueError("Debt payments require plan_id or installment_id.")

        if a <= 0 and t > 0 and not (self.doctor_id or self.plan_id):
            raise ValueError(
                "Pure tip requires doctor_id or must be linked to a plan_id."
            )

        return self


class PaymentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: int
    clinic_id: int
    patient_id: Optional[int]
    doctor_id: int
    plan_id: Optional[int]
    installment_id: Optional[int]

    amount: float
    tip_amount: float
    method: PaymentMethod
    created_at: datetime

    created_by: int
    session_user_id: Optional[int]
    approved_by: Optional[int] = None

    status: str
    target_cashbox_id: Optional[int] = None
