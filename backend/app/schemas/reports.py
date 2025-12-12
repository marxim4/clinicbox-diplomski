from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DoctorRevenueItemSchema(BaseModel):
    doctor_id: int
    doctor_name: Optional[str] = None
    total_amount: float
    total_tip_amount: float
    payments_count: int


class CategoryExpenseItemSchema(BaseModel):
    category_id: int
    name: str
    total_amount: float


class CashboxSummaryItemSchema(BaseModel):
    cashbox_id: int
    name: str
    total_in: float
    total_out: float
    total_adjustment: float
    net: float


class PatientFinancialSummarySchema(BaseModel):
    patient_id: int
    patient_name: Optional[str] = None

    total_planned: float
    total_paid: float
    total_tips: float
    remaining_debt: float

    active_plans_count: int
    overdue_plans_count: int

    first_payment_date: Optional[datetime] = None
    last_payment_date: Optional[datetime] = None


class TopDebtorItemSchema(BaseModel):
    patient_id: int
    patient_name: Optional[str] = None
    remaining_debt: float
    last_payment_date: Optional[datetime] = None
