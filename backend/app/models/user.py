from __future__ import annotations

from typing import List

from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db, bcrypt
from ..enums import UserRole


class User(db.Model):
    __tablename__ = "user"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        db.Enum(UserRole),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(default=True)

    # main clinic this user belongs to
    clinic: Mapped["Clinic"] = relationship(
        "Clinic",
        back_populates="users",
        foreign_keys=[clinic_id],  # <-- important
    )

    # clinic where this user is the OWNER (1–1)
    owned_clinic: Mapped["Clinic"] = relationship(
        "Clinic",
        back_populates="owner",
        uselist=False,
        foreign_keys="Clinic.owner_user_id",
    )

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

    # Payments where this user was the logged-in session
    sessions_payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="session_user",
        foreign_keys="Payment.session_user_id",
    )

    # Cash Transactions where this user was the logged-in session
    sessions_transactions: Mapped[List["CashTransaction"]] = relationship(
        "CashTransaction",
        back_populates="session_user",
        foreign_keys="CashTransaction.session_user_id",
    )

    # Daily Closes where this user was the logged-in session
    sessions_closes: Mapped[List["DailyClose"]] = relationship(
        "DailyClose",
        back_populates="session_user",
        foreign_keys="DailyClose.session_user_id",
    )

    # Tip Payouts where this user was the logged-in session
    sessions_payouts: Mapped[List["TipPayout"]] = relationship(
        "TipPayout",
        back_populates="session_user",
        foreign_keys="TipPayout.session_user_id",
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

    def set_pin(self, pin: str) -> None:
        # pin is 4 digits, but we hash it like a password
        self.pin_hash = bcrypt.generate_password_hash(pin).decode()

    def check_pin(self, pin: str) -> bool:
        if not self.pin_hash:
            return False
        return bcrypt.check_password_hash(self.pin_hash, pin)

    def __repr__(self) -> str:
        return f"<User {self.user_id} {self.email}>"
