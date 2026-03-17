from __future__ import annotations

from typing import Optional

from ..extensions import db
from ..models import Clinic


class ClinicRepository:
    def get_by_id(self, clinic_id: int) -> Optional[Clinic]:
        return db.session.get(Clinic, clinic_id)

    def update_basic_info(
            self,
            clinic: Clinic,
            *,
            name: str | None = None,
            address: str | None = None,
            currency: str | None = None,
            default_language: str | None = None,
            timezone: str | None = None,
    ):
        if name is not None:
            clinic.name = name
        if address is not None:
            clinic.address = address
        if currency is not None:
            clinic.currency = currency
        if default_language is not None:
            clinic.default_language = default_language
        if timezone is not None:
            clinic.timezone = timezone

        db.session.flush()
        return clinic

    def update_settings(
            self,
            clinic: Clinic,
            *,
            requires_payment_approval: bool | None = None,
            requires_cash_approval: bool | None = None,
            requires_close_approval: bool | None = None,
            use_shared_terminal_mode: bool | None = None,
            require_pin_for_actions: bool | None = None,
            require_pin_for_signoff: bool | None = None,
    ):
        if requires_payment_approval is not None:
            clinic.requires_payment_approval = requires_payment_approval
        if requires_cash_approval is not None:
            clinic.requires_cash_approval = requires_cash_approval
        if requires_close_approval is not None:
            clinic.requires_close_approval = requires_close_approval

        if use_shared_terminal_mode is not None:
            clinic.use_shared_terminal_mode = use_shared_terminal_mode
        if require_pin_for_actions is not None:
            clinic.require_pin_for_actions = require_pin_for_actions
        if require_pin_for_signoff is not None:
            clinic.require_pin_for_signoff = require_pin_for_signoff

        db.session.flush()
        return clinic


clinic_repo = ClinicRepository()
