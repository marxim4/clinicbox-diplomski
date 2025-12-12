from __future__ import annotations

from datetime import datetime
from sqlalchemy import Integer, ForeignKey, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Tip(db.Model):
    __tablename__ = "tip"

    tip_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )

    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patient.patient_id"),
        nullable=True,
    )

    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("installment_plan.plan_id"),
        nullable=True,
    )

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )

    cash_transaction: Mapped["CashTransaction"] = relationship(
        "CashTransaction",
        back_populates="tip",
        uselist=False
    )

    doctor: Mapped["User"] = relationship("User")
    clinic: Mapped["Clinic"] = relationship("Clinic")
    patient: Mapped["Patient"] = relationship("Patient")
    plan: Mapped["InstallmentPlan"] = relationship("InstallmentPlan")
    created_by_user: Mapped["User"] = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Tip {self.tip_id} amount={self.amount}>"
