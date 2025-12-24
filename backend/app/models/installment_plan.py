from __future__ import annotations

from datetime import date
from typing import List

from sqlalchemy import Integer, String, ForeignKey, Numeric, Date, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from ..enums import PlanStatus, PaymentMethod


class InstallmentPlan(db.Model):
    __tablename__ = "installment_plan"

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patient.patient_id"),
        nullable=False,
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(String(255))

    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    default_payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod),
        nullable=False,
        default=PaymentMethod.CASH,
    )

    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus),
        default=PlanStatus.PLANNED,
        nullable=False,
    )

    start_date: Mapped[date | None] = mapped_column(Date)

    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="installment_plans")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="installment_plans")
    doctor: Mapped["User"] = relationship("User", back_populates="installment_plans")

    installments: Mapped[List["Installment"]] = relationship(
        "Installment",
        back_populates="plan",
        cascade="all, delete-orphan",
    )

    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="plan",
    )

    def __repr__(self) -> str:
        return f"<InstallmentPlan {self.plan_id} total={self.total_amount}>"
