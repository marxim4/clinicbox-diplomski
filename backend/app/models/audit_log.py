from __future__ import annotations

import hashlib
import json
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

    __table_args__ = (
        db.Index("ix_audit_log_clinic_created_at", "clinic_id", "created_at"),
        db.Index("ix_audit_log_clinic_entity", "clinic_id", "entity_name", "entity_id"),
        db.Index("ix_audit_log_clinic_action", "clinic_id", "action"),
        db.UniqueConstraint("clinic_id", "curr_hash", name="uq_audit_log_clinic_curr_hash"),
    )

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

    # primary key value of the entity
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # JSON snapshots
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)

    # Metadata
    ip_address: Mapped[str | None] = mapped_column(String(64))
    device_info: Mapped[str | None] = mapped_column(Text)

    # Hash chain
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
