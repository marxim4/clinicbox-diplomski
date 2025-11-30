from __future__ import annotations

from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, PositiveFloat


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


class TipPayoutResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payout_id: int
    clinic_id: int
    doctor_id: int
    amount: float
    note: str | None
    created_at: datetime
    created_by: int
