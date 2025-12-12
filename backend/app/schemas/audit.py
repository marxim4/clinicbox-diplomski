from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ..enums import AuditAction


class CreateAuditLogRequestSchema(BaseModel):
    action: AuditAction
    entity_name: str
    entity_id: str

    before_data: dict | None = None
    after_data: dict | None = None

    ip_address: str | None = None
    device_info: str | None = None

    @field_validator("entity_name")
    @classmethod
    def strip_entity_name(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("entity_name must not be empty")
        return v

    @field_validator("entity_id")
    @classmethod
    def strip_entity_id(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("entity_id must not be empty")
        return v


class AuditLogResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: int
    clinic_id: int
    user_id: int | None

    action: AuditAction
    entity_name: str
    entity_id: str

    before_data: dict | None
    after_data: dict | None

    ip_address: str | None
    device_info: str | None

    prev_hash: str | None
    curr_hash: str | None

    created_at: datetime


class AuditLogSearchResponseItemSchema(BaseModel):
    audit_id: int
    created_at: datetime
    user_id: int | None
    action: AuditAction
    entity_name: str
    entity_id: str
