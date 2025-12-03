from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class CreateCategoryRequestSchema(BaseModel):
    name: str
    is_pinned: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("name must not be empty")
        if len(v2) > 120:
            raise ValueError("name too long (max 120 characters)")
        return v2


class UpdateCategoryRequestSchema(BaseModel):
    name: Optional[str] = None
    is_pinned: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one(self):
        if self.name is None and self.is_pinned is None:
            raise ValueError("Provide at least one field to update.")
        return self

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        if not v2:
            raise ValueError("name must not be empty if provided")
        if len(v2) > 120:
            raise ValueError("name too long (max 120 characters)")
        return v2


class CategoryResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    clinic_id: int
    name: str
    is_pinned: bool
    usage_count: int
    last_used_at: Optional[datetime]
