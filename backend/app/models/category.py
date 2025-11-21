from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Category(db.Model):
    __tablename__ = "category"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


    clinic: Mapped["Clinic"] = relationship("Clinic", back_populates="categories")

    transactions: Mapped[List["CashTransaction"]] = relationship(
        "CashTransaction",
        back_populates="category",
    )

    def __repr__(self) -> str:
        return f"<Category {self.category_id} {self.name}>"
