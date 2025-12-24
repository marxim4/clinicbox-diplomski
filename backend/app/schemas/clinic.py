from typing import Optional
from pydantic import BaseModel, field_validator


class UpdateClinicDetailsSchema(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    currency: Optional[str] = None
    default_language: Optional[str] = None

    @field_validator("name", "currency", "default_language")
    @classmethod
    def strip_nonempty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        if not v2:
            raise ValueError("must not be empty")
        return v2


class UpdateClinicSettingsSchema(BaseModel):
    requires_payment_approval: Optional[bool] = None
    requires_cash_approval: Optional[bool] = None
    requires_close_approval: Optional[bool] = None

    use_shared_terminal_mode: Optional[bool] = None
    require_pin_for_actions: Optional[bool] = None
    require_pin_for_signoff: Optional[bool] = None
