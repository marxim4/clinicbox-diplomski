from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class CreateDailyCloseRequestSchema(BaseModel):
    cashbox_id: int
    date: DateType | None = None

    counted_total: float

    note: str | None = None
    pin: str | None = None
    acting_user_id: int | None = None

    @field_validator("counted_total")
    @classmethod
    def validate_non_negative(cls, v: float):
        if v < 0:
            raise ValueError("Counted total cannot be negative")
        return round(v, 2)

    @field_validator("note")
    @classmethod
    def strip_note(cls, v: str | None):
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


class DailyCloseResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    close_id: int
    clinic_id: int
    cashbox_id: int
    date: DateType

    expected_total: float
    counted_total: float
    variance: float

    note: str | None = None
    created_at: datetime

    closed_by: int
    session_user_id: int

    status: str
    approved_by: int | None = None