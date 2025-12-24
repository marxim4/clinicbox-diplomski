from __future__ import annotations

from typing import List

from sqlalchemy import String, Integer, ForeignKey, Boolean, CheckConstraint
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

    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    is_active: Mapped[bool] = mapped_column(default=True)

    can_approve_financials: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_approval_for_actions: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        CheckConstraint(
            "NOT (can_approve_financials IS TRUE AND requires_approval_for_actions IS TRUE)",
            name="check_user_approval_logic"
        ),
    )

    clinic: Mapped["Clinic"] = relationship(
        "Clinic",
        back_populates="users",
        foreign_keys=[clinic_id],
    )

    owned_clinic: Mapped["Clinic"] = relationship(
        "Clinic",
        back_populates="owner",
        uselist=False,
        foreign_keys="Clinic.owner_user_id",
    )

    patients: Mapped[List["Patient"]] = relationship("Patient", back_populates="doctor")
    installment_plans: Mapped[List["InstallmentPlan"]] = relationship("InstallmentPlan", back_populates="doctor")

    created_payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="created_by_user",
                                                             foreign_keys="Payment.created_by")
    approved_payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="approved_by_user",
                                                              foreign_keys="Payment.approved_by")
    sessions_payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="session_user",
                                                              foreign_keys="Payment.session_user_id")

    created_transactions: Mapped[List["CashTransaction"]] = relationship("CashTransaction",
                                                                         back_populates="created_by_user",
                                                                         foreign_keys="CashTransaction.created_by")
    approved_transactions: Mapped[List["CashTransaction"]] = relationship("CashTransaction",
                                                                          back_populates="approved_by_user",
                                                                          foreign_keys="CashTransaction.approved_by")
    sessions_transactions: Mapped[List["CashTransaction"]] = relationship("CashTransaction",
                                                                          back_populates="session_user",
                                                                          foreign_keys="CashTransaction.session_user_id")

    sessions_closes: Mapped[List["DailyClose"]] = relationship("DailyClose", back_populates="session_user",
                                                               foreign_keys="DailyClose.session_user_id")
    closed_days: Mapped[list["DailyClose"]] = relationship("DailyClose", back_populates="closed_by_user",
                                                           foreign_keys="DailyClose.closed_by")
    approved_closes: Mapped[list["DailyClose"]] = relationship("DailyClose", back_populates="approved_by_user",
                                                               foreign_keys="DailyClose.approved_by")

    sessions_payouts: Mapped[List["TipPayout"]] = relationship("TipPayout", back_populates="session_user",
                                                               foreign_keys="TipPayout.session_user_id")
    approved_payouts: Mapped[List["TipPayout"]] = relationship("TipPayout", back_populates="approved_by_user",
                                                               foreign_keys="TipPayout.approved_by")

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode()
        current_version = self.token_version or 0
        self.token_version = current_version + 1

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    def set_pin(self, pin: str) -> None:
        self.pin_hash = bcrypt.generate_password_hash(pin).decode()

    def check_pin(self, pin: str) -> bool:
        if not self.pin_hash:
            return False
        return bcrypt.check_password_hash(self.pin_hash, pin)

    def __repr__(self) -> str:
        return f"<User {self.user_id} {self.email}>"
