from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator, ConfigDict

from ..constants import PASSWORD_REGEX, PIN_REGEX
from ..enums import UserRole


class CreateUserRequestSchema(BaseModel):
    name: str
    email: EmailStr
    role: UserRole
    password: str
    confirm_password: str
    pin: Optional[str] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("must not be empty")
        return v2

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str):
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str):
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                "Password must be at least 8 characters long and contain at least "
                "one uppercase letter, one digit and one special character."
            )
        return v

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        if not re.fullmatch(PIN_REGEX, v2):
            raise ValueError("PIN must be exactly 4 digits")
        return v2

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class ChangePinRequestSchema(BaseModel):
    current_pin: Optional[str] = None
    new_pin: str
    confirm_new_pin: str

    @field_validator("new_pin", "confirm_new_pin")
    @classmethod
    def validate_new_pin(cls, v: str) -> str:
        v2 = v.strip()
        if not re.fullmatch(PIN_REGEX, v2):
            raise ValueError("PIN must be exactly 4 digits")
        return v2

    @model_validator(mode="after")
    def check_new_pins_match(self):
        if self.new_pin != self.confirm_new_pin:
            raise ValueError("New PINs do not match")
        return self


class SetUserStatusRequestSchema(BaseModel):
    is_active: bool


class UpdateUserRequestSchema(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    pin: Optional[str] = None
    clear_pin: Optional[bool] = None
    requires_approval_for_actions: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        if not v2:
            raise ValueError("must not be empty")
        return v2

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: Optional[EmailStr]) -> Optional[EmailStr]:
        if v is None:
            return v
        return EmailStr(str(v).strip().lower())

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        if not re.fullmatch(PIN_REGEX, v2):
            raise ValueError("PIN must be exactly 4 digits")
        return v2

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any(
                [
                    self.name is not None,
                    self.email is not None,
                    self.role is not None,
                    self.pin is not None,
                    self.clear_pin is not None,
                    self.requires_approval_for_actions is not None,
                ]
        ):
            raise ValueError("Provide at least one field to update.")
        return self


class UpdateMeRequestSchema(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        if not v2:
            raise ValueError("must not be empty")
        return v2

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: Optional[EmailStr]):
        if v is None:
            return v
        return EmailStr(str(v).strip().lower())

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.name is None and self.email is None:
            raise ValueError("Provide at least one field to update.")
        return self


class VerifyPinRequestSchema(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        v2 = v.strip()
        if not re.fullmatch(PIN_REGEX, v2):
            raise ValueError("PIN must be exactly 4 digits")
        return v2


class UserResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    clinic_id: int
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    has_pin: bool
    requires_approval_for_actions: bool
