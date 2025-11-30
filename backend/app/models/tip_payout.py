from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, ForeignKey, Numeric, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class TipPayout(db.Model):
    __tablename__ = "tip_payout"

    payout_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
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

    note: Mapped[str | None] = mapped_column(Text)

    clinic: Mapped["Clinic"] = relationship("Clinic")
    doctor: Mapped["User"] = relationship("User", foreign_keys=[doctor_id])
    created_by_user: Mapped["User"] = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<TipPayout {self.payout_id} doctor={self.doctor_id} amount={self.amount}>"
