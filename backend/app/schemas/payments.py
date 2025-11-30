from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.types import PositiveFloat

from ..enums import PaymentMethod


class CreatePaymentRequestSchema(BaseModel):
    plan_id: Optional[int] = None
    installment_id: Optional[int] = None

    doctor_id: Optional[int] = None

    amount: Optional[PositiveFloat] = None
    tip_amount: float = 0

    method: Optional[PaymentMethod] = None
    cashbox_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_logic(self):
        a = float(self.amount) if self.amount is not None else 0
        t = float(self.tip_amount or 0)

        if a <= 0 and t <= 0:
            raise ValueError("Either amount or tip_amount must be greater than zero.")

        # 2. If it's a debt payment -> require plan_id OR installment_id
        if a > 0 and not (self.plan_id or self.installment_id):
            raise ValueError("Debt payments require plan_id or installment_id.")

        # 3. If it's a pure tip -> require doctor_id
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
