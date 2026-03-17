from __future__ import annotations

from typing import Tuple, Optional

from ..models import User, Clinic
from ..data_layer.clinic_repository import clinic_repo
from ..schemas.clinic import UpdateClinicSettingsSchema, UpdateClinicDetailsSchema


class ClinicService:
    """
    Service for managing Clinic-level configurations and details.

    This service acts as the 'Policy Engine' for the application. It handles the
    modification of the clinic entity, including its operational settings
    (e.g., approval workflows, shared terminal modes) and basic metadata.
    """

    def get_current_clinic(self, current_user: User) -> Tuple[Optional[Clinic], Optional[str]]:
        """
        Retrieves the clinic associated with the current authenticated user.

        Validates that the user has a valid clinic assignment before returning
        the clinic entity.
        """
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
    ) -> Tuple[Optional[Clinic], Optional[str]]:
        """
        Updates the basic metadata of the clinic.

        This includes display name, physical address, and localization settings
        (currency, default language) which affect how data is presented to all users.
        """
        clinic, error = self.get_current_clinic(current_user)
        if error:
            return None, error

        updated_clinic = clinic_repo.update_basic_info(
            clinic,
            name=payload.name,
            address=payload.address,
            currency=payload.currency,
            default_language=payload.default_language,
            timezone=payload.timezone,
        )
        return updated_clinic, None

    def update_settings(
            self,
            current_user: User,
            payload: UpdateClinicSettingsSchema
    ) -> Tuple[Optional[Clinic], Optional[str]]:
        """
        Updates the operational configuration (Security Policy) of the clinic.

        These settings determine the strictness of the application's workflows,
        such as requiring manager approval for financial actions or enforcing
        PIN verification for shared terminal usage.
        """
        clinic, error = self.get_current_clinic(current_user)
        if error:
            return None, error

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
