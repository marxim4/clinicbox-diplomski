from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Integer,
    String,
    ForeignKey,
    DateTime,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from ..enums import AuditAction


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinic.clinic_id"),
        nullable=False,
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.user_id"),
        nullable=True,
    )

    action: Mapped[AuditAction] = mapped_column(
        db.Enum(AuditAction),
        nullable=False,
    )

    # e.g. "payment", "cash_transaction", "daily_close"
    entity_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # primary key value of the entity (string because could be UUID later)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # JSON snapshots before and after
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)

    # Optional metadata
    ip_address: Mapped[str | None] = mapped_column(String(64))
    device_info: Mapped[str | None] = mapped_column(Text)

    # Hash chain fields for tamper evidence
    prev_hash: Mapped[str | None] = mapped_column(String(128))
    curr_hash: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )


    clinic: Mapped["Clinic"] = relationship("Clinic")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<AuditLog {self.audit_id} {self.action} {self.entity_name}:{self.entity_id}>"
