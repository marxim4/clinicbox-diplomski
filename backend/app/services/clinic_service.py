from __future__ import annotations
from typing import Tuple, Optional
from ..models import User, Clinic
from ..data_layer.clinic_repository import clinic_repo
from ..schemas.clinic import UpdateClinicSettingsSchema, UpdateClinicDetailsSchema


class ClinicService:
    def get_current_clinic(self, current_user: User):
        if not current_user.clinic_id:
            return None, "user has no clinic"

        clinic = clinic_repo.get_by_id(current_user.clinic_id)
        if not clinic:
            return None, "clinic not found"
        return clinic, None

    def update_details(
            self,
            current_user: User,
            payload: UpdateClinicDetailsSchema
    ):

        clinic, error = self.get_current_clinic(current_user)
        if error: return None, error

        updated_clinic = clinic_repo.update_basic_info(
            clinic,
            name=payload.name,
            address=payload.address,
            currency=payload.currency,
            default_language=payload.default_language,
        )
        return updated_clinic, None

    def update_settings(
            self,
            current_user: User,
            payload: UpdateClinicSettingsSchema
    ):

        clinic, error = self.get_current_clinic(current_user)
        if error: return None, error

        updated_clinic = clinic_repo.update_settings(
            clinic,
            requires_payment_approval=payload.requires_payment_approval,
            requires_cash_approval=payload.requires_cash_approval,
            requires_close_approval=payload.requires_close_approval,
            use_shared_terminal_mode=payload.use_shared_terminal_mode,
            require_pin_for_actions=payload.require_pin_for_actions,
            require_pin_for_signoff=payload.require_pin_for_signoff,
        )
        return updated_clinic, None


clinic_service = ClinicService()
