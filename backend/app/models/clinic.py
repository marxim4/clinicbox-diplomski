from __future__ import annotations

from typing import List

from sqlalchemy import String, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from ..enums import ClinicType


class Clinic(db.Model):
    __tablename__ = "clinic"

    clinic_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))

    currency: Mapped[str] = mapped_column(String(10), default="EUR")
    default_language: Mapped[str] = mapped_column(String(10), default="en")

    clinic_type: Mapped[ClinicType] = mapped_column(
        Enum(ClinicType),
        default=ClinicType.DENTAL,
        nullable=False,
    )

    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    requires_payment_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    requires_cash_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    requires_close_approval: Mapped[bool] = mapped_column(default=False, nullable=False)

    patients: Mapped[List["Patient"]] = relationship(
        "Patient",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    installment_plans: Mapped[List["InstallmentPlan"]] = relationship(
        "InstallmentPlan",
        back_populates="clinic",
    )

    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="clinic",
    )

    cashboxes: Mapped[List["Cashbox"]] = relationship(
        "Cashbox",
        back_populates="clinic",
    )

    categories: Mapped[List["Category"]] = relationship(
        "Category",
        back_populates="clinic",
    )

    cash_transactions: Mapped[List["CashTransaction"]] = relationship(
        "CashTransaction",
        back_populates="clinic",
    )

    closes: Mapped[List["DailyClose"]] = relationship(
        "DailyClose",
        back_populates="clinic",
    )

    def __repr__(self) -> str:
        return f"<Clinic {self.clinic_id} {self.name}>"
