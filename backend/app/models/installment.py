from __future__ import annotations

from datetime import date

from sqlalchemy import Integer, ForeignKey, Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Installment(db.Model):
    __tablename__ = "installment"

    installment_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("installment_plan.plan_id"),
        nullable=False,
    )

    # Order of installment inside the plan
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Target due-date
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Expected for this installment
    expected_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    amount_paid: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    plan: Mapped["InstallmentPlan"] = relationship("InstallmentPlan", back_populates="installments")

    def __repr__(self) -> str:
        return f"<Installment {self.installment_id} seq={self.sequence} due={self.due_date}>"
