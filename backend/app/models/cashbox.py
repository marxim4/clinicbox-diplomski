from __future__ import annotations

from typing import List

from sqlalchemy import Integer, String, Text, ForeignKey, Boolean, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Cashbox(db.Model):
    __tablename__ = "cashbox"

    cashbox_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    current_amount: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0,
    )

    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="cashboxes")

    transactions: Mapped[List["CashTransaction"]] = relationship(
        "CashTransaction",
        back_populates="cashbox",
        cascade="all, delete-orphan",
    )

    closes: Mapped[List["DailyClose"]] = relationship(
        "DailyClose",
        back_populates="cashbox",
    )

    def __repr__(self) -> str:
        return f"<Cashbox {self.cashbox_id} {self.name}>"
