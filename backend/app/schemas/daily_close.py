from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.types import PositiveFloat


class CreateDailyCloseRequestSchema(BaseModel):
    cashbox_id: int
    date: Optional[date] = None  # if None -> today in service
    counted_total: PositiveFloat
    note: Optional[str] = None

    pin: Optional[str] = None
    acting_user_id: Optional[int] = None

    @field_validator("note")
    @classmethod
    def strip_note(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


class DailyCloseResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    close_id: int
    clinic_id: int
    cashbox_id: int
    date: date

    expected_total: float
    counted_total: float
    variance: float

    note: Optional[str] = None
    created_at: datetime

    closed_by: int
    session_user_id: int

    status: str
    approved_by: Optional[int] = None
