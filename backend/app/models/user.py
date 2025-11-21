from __future__ import annotations

from typing import List

from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db, bcrypt
from ..enums import UserRole


class User(db.Model):
    __tablename__ = "user"
    __table_args__ = (
        UniqueConstraint("clinic_id", "email", name="uq_user_clinic_email"),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        db.Enum(UserRole),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(default=True)

    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="users")

    requires_approval_for_actions: Mapped[bool] = mapped_column(default=True)

    # Patients where this user is the primary doctor
    patients: Mapped[List["Patient"]] = relationship(
        "Patient",
        back_populates="doctor",
    )

    # Installment plans for which this user is the doctor
    installment_plans: Mapped[List["InstallmentPlan"]] = relationship(
        "InstallmentPlan",
        back_populates="doctor",
    )

    # Dual sign-off on payments
    created_payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="created_by_user",
        foreign_keys="Payment.created_by",
    )
    approved_payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="approved_by_user",
        foreign_keys="Payment.approved_by",
    )

    # Dual sign-off on cash transactions
    created_transactions: Mapped[List["CashTransaction"]] = relationship(
        "CashTransaction",
        back_populates="created_by_user",
        foreign_keys="CashTransaction.created_by",
    )
    approved_transactions: Mapped[List["CashTransaction"]] = relationship(
        "CashTransaction",
        back_populates="approved_by_user",
        foreign_keys="CashTransaction.approved_by",
    )

    closed_days: Mapped[list["DailyClose"]] = relationship(
        "DailyClose",
        back_populates="closed_by_user",
        foreign_keys="DailyClose.closed_by",
    )

    approved_closes: Mapped[list["DailyClose"]] = relationship(
        "DailyClose",
        back_populates="approved_by_user",
        foreign_keys="DailyClose.approved_by",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode()

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.user_id} {self.email}>"
