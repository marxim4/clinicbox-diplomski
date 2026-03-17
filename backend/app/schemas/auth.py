from __future__ import annotations

from typing import Optional
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from ..constants import PASSWORD_REGEX
from app.enums import UserRole


class RegisterOwnerSchema(BaseModel):
    owner_name: str
    email: EmailStr
    password: str
    confirm_password: str
    owner_role: UserRole

    clinic_name: str
    clinic_address: Optional[str] = None
    clinic_type: Optional[str] = None
    currency: Optional[str] = "EUR"
    default_language: Optional[str] = "en"
    timezone: Optional[str] = "UTC"

    @field_validator("owner_name", "clinic_name")
    @classmethod
    def strip_nonempty(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("must not be empty")
        return v2

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("timezone must not be empty")
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"'{v}' is not a valid IANA timezone (e.g. 'Europe/Belgrade', 'UTC')")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                "Password must be at least 8 characters long and contain at least "
                "one uppercase letter, one digit and one special character."
            )
        return v

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginSchema(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                "New password must be at least 8 characters long and contain at least "
                "one uppercase letter, one digit and one special character."
            )
        return v

    @model_validator(mode="after")
    def check_new_passwords_match(self):
        if self.new_password != self.confirm_new_password:
            raise ValueError("New passwords do not match")
        return self
