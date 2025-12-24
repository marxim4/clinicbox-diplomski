from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Integer,
    ForeignKey,
    Numeric,
    DateTime,
    Enum, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..enums.payment_status_enum import PaymentStatus
from ..extensions import db
from ..enums import PaymentMethod


class Payment(db.Model):
    __tablename__ = "payment"

    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )
    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patient.patient_id"),
        nullable=True,
    )

    doctor_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"), nullable=False)

    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("installment_plan.plan_id"),
        nullable=True,
    )
    installment_id: Mapped[int | None] = mapped_column(
        ForeignKey("installment.installment_id"),
        nullable=True,
    )

    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    tip_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod),
        default=PaymentMethod.CASH,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=PaymentStatus.PAID.value,
        nullable=False
    )
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=True,
    )
    session_user_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )
    target_cashbox_id: Mapped[int | None] = mapped_column(
        ForeignKey("cashbox.cashbox_id"),
        nullable=True,
    )

    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="payments")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="payments")
    plan: Mapped["InstallmentPlan"] = relationship("InstallmentPlan", back_populates="payments")
    installment: Mapped["Installment"] = relationship("Installment")

    created_by_user: Mapped["User"] = relationship(
        "User",
        back_populates="created_payments",
        foreign_keys=[created_by],
    )
    approved_by_user: Mapped["User"] = relationship(
        "User",
        back_populates="approved_payments",
        foreign_keys=[approved_by],
    )
    session_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[session_user_id],
        back_populates="sessions_payments",
    )

    cash_transaction: Mapped["CashTransaction"] = relationship(
        "CashTransaction",
        back_populates="payment",
        uselist=False,
    )

    target_cashbox: Mapped["Cashbox"] = relationship(
        "Cashbox",
        foreign_keys=[target_cashbox_id]
    )

    def __repr__(self) -> str:
        return f"<Payment {self.payment_id} amount={self.amount} tip={self.tip_amount}>"
