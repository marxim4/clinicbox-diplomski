from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Integer,
    ForeignKey,
    Numeric,
    Date,
    DateTime,
    Text, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..enums.daily_close_status_enum import DailyCloseStatus
from ..extensions import db


class DailyClose(db.Model):
    __tablename__ = "daily_close"

    close_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    cashbox_id: Mapped[int] = mapped_column(
        ForeignKey("cashbox.cashbox_id"),
        nullable=False,
    )

    # Business day being closed (e.g. 2025-11-21)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # Calculated from transactions by the system
    expected_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Counted by staff
    counted_total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # counted_total - expected_total (can be negative)
    variance: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    note: Mapped[str | None] = mapped_column(Text)

    closed_by: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=DailyCloseStatus.APPROVED,
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

    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    clinic: Mapped["Clinic"] = relationship(
        "Clinic",
        back_populates="closes",
    )

    cashbox: Mapped["Cashbox"] = relationship(
        "Cashbox",
        back_populates="closes",
    )

    closed_by_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[closed_by],
        back_populates="closed_days",
    )

    approved_by_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[approved_by],
        back_populates="approved_closes",
    )

    session_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[session_user_id],
        back_populates="sessions_closes",
    )

    def __repr__(self) -> str:
        return (
            f"<DailyClose {self.close_id} clinic={self.clinic_id} "
            f"cashbox={self.cashbox_id} date={self.date}>"
        )
