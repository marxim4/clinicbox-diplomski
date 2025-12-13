from __future__ import annotations

from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, PositiveFloat, field_validator


class CreateTipRequestSchema(BaseModel):
    doctor_id: int
    amount: PositiveFloat

    patient_id: Optional[int] = None
    plan_id: Optional[int] = None


class TipResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tip_id: int
    clinic_id: int
    doctor_id: int
    patient_id: int | None
    plan_id: int | None
    amount: float
    created_at: datetime


class DoctorTipBalanceResponseSchema(BaseModel):
    total_earned: float
    total_paid_out: float
    balance: float


class CreateTipPayoutRequestSchema(BaseModel):
    amount: PositiveFloat
    note: Optional[str] = None

    pin: Optional[str] = None
    acting_user_id: Optional[int] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float):
        if v <= 0:
            raise ValueError("amount must be positive")
        return round(v, 2)


class TipPayoutResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payout_id: int
    clinic_id: int
    doctor_id: int
    amount: float
    note: Optional[str]
    created_at: datetime
    created_by: int
    session_user_id: Optional[int] = None