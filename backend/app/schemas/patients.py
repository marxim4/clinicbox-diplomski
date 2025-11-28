from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator, ConfigDict


class CreatePatientRequestSchema(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    note: Optional[str] = None
    doctor_id: int

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_nonempty(cls, v: str) -> str:
        v2 = v.strip()
        if not v2:
            raise ValueError("must not be empty")
        return v2

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: Optional[EmailStr]) -> Optional[EmailStr]:
        if v is None:
            return v
        return EmailStr(str(v).strip().lower())

    @field_validator("note")
    @classmethod
    def strip_note(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


class UpdatePatientRequestSchema(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    note: Optional[str] = None
    doctor_id: Optional[int] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        if not v2:
            raise ValueError("must not be empty")
        return v2

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: Optional[EmailStr]) -> Optional[EmailStr]:
        if v is None:
            return v
        return EmailStr(str(v).strip().lower())

    @field_validator("note")
    @classmethod
    def strip_note(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not any(
                [
                    self.first_name is not None,
                    self.last_name is not None,
                    self.phone is not None,
                    self.email is not None,
                    self.note is not None,
                    self.doctor_id is not None,
                ]
        ):
            raise ValueError("Provide at least one field to update.")
        return self


class PatientResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: int
    clinic_id: int
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    note: Optional[str] = None
    doctor_id: int
