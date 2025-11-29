from __future__ import annotations

from datetime import date
from typing import Optional, List

from pydantic import BaseModel, field_validator, model_validator, ConfigDict

from ..enums import PlanStatus


class InstallmentItemInputSchema(BaseModel):
    due_date: date
    expected_amount: float

    @field_validator("expected_amount")
    @classmethod
    def validate_expected_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("expected_amount must be greater than 0")
        # normalize to 2 decimals
        return round(v, 2)


class CreateInstallmentPlanRequestSchema(BaseModel):
    patient_id: int
    doctor_id: int
    description: Optional[str] = None
    total_amount: float
    start_date: Optional[date] = None
    # optional explicit installment schedule
    installments: Optional[List[InstallmentItemInputSchema]] = None

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("total_amount must be greater than 0")
        return round(v, 2)

    @model_validator(mode="after")
    def validate_installments_sum(self):
        # If user provided installments, ensure they sum to total_amount
        if self.installments:
            total_installments = round(
                sum(i.expected_amount for i in self.installments), 2
            )
            if total_installments != round(self.total_amount, 2):
                raise ValueError(
                    "sum of installments expected_amount must equal total_amount"
                )
        return self


class UpdateInstallmentPlanRequestSchema(BaseModel):
    description: Optional[str] = None
    total_amount: Optional[float] = None
    status: Optional[PlanStatus] = None
    start_date: Optional[date] = None
    # full replacement of installments (optional)
    installments: Optional[List[InstallmentItemInputSchema]] = None

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None

    @field_validator("total_amount")
    @classmethod
    def validate_total_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v <= 0:
            raise ValueError("total_amount must be greater than 0")
        return round(v, 2)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if (
                self.description is None
                and self.total_amount is None
                and self.status is None
                and self.start_date is None
                and self.installments is None
        ):
            raise ValueError("Provide at least one field to update.")
        return self

    @model_validator(mode="after")
    def validate_installments_sum(self):
        # Only enforce when both total_amount and installments are provided together
        if self.installments is not None and self.total_amount is not None:
            total_installments = round(
                sum(i.expected_amount for i in self.installments), 2
            )
            if total_installments != round(self.total_amount, 2):
                raise ValueError(
                    "sum of installments expected_amount must equal total_amount"
                )
        return self


class InstallmentItemResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    installment_id: int
    plan_id: int
    sequence: int
    due_date: date
    expected_amount: float


class InstallmentPlanResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: int
    clinic_id: int
    patient_id: int
    doctor_id: int
    description: Optional[str] = None
    total_amount: float
    status: PlanStatus
    start_date: Optional[date] = None

    installments: list[InstallmentItemResponseSchema] = []


class UpcomingInstallmentResponseSchema(BaseModel):
    installment_id: int
    plan_id: int
    due_date: date
    expected_amount: float
    patient_id: int
    doctor_id: int
