from __future__ import annotations

from typing import Optional, Tuple

from ..models import User, InstallmentPlan
from ..data_layer.installment_plan_repository import installment_plan_repo
from ..data_layer.patient_repository import patient_repo
from ..data_layer.user_repository import user_repo
from ..schemas.installments import (
    CreateInstallmentPlanRequestSchema,
    UpdateInstallmentPlanRequestSchema,
)
from ..enums import PlanStatus


class InstallmentService:
    """
    Service for managing patient financial plans (Installment Plans).

    This service handles the lifecycle of payment plans, including creation,
    scheduling, updates, and cancellation. It enforces strict data integrity rules,
    such as preventing the restructuring of installment schedules once payments
    have commenced.
    """

    def create_plan(
            self,
            current_user: User,
            payload: CreateInstallmentPlanRequestSchema,
    ) -> Tuple[Optional[InstallmentPlan], Optional[str]]:
        """
        Creates a new installment plan for a patient.

        Validates that both the patient and the assigned doctor belong to the
        current user's clinic before creating the plan and its scheduled installments.
        """
        if not current_user.clinic_id:
            return None, "user has no clinic assigned"

        clinic_id = current_user.clinic_id

        patient = patient_repo.get_by_id_in_clinic(payload.patient_id, clinic_id)
        if not patient:
            return None, "patient not found in this clinic"

        doctor = user_repo.get_by_id_in_clinic(payload.doctor_id, clinic_id)
        if not doctor:
            return None, "doctor not found in this clinic"

        installments_data = (
                [
                    {
                        "due_date": inst.due_date,
                        "expected_amount": inst.expected_amount,
                    }
                    for inst in (payload.installments or [])
                ]
                or None
        )

        plan = installment_plan_repo.create_plan(
            clinic_id=clinic_id,
            patient_id=patient.patient_id,
            doctor_id=doctor.user_id,
            description=payload.description,
            total_amount=payload.total_amount,
            status=PlanStatus.PLANNED,
            start_date=payload.start_date,
            installments_data=installments_data,
        )
        return plan, None

    def get_plan_for_clinic(
            self,
            clinic_id: int,
            plan_id: int,
    ):
        """Retrieves a specific plan, ensuring it belongs to the clinic."""
        return installment_plan_repo.get_plan_in_clinic(plan_id, clinic_id)

    def list_plans_for_clinic(
            self,
            clinic_id: int,
            *,
            patient_id: int | None = None,
            doctor_id: int | None = None,
            status: PlanStatus | None = None,
    ):
        """Lists all plans for a clinic, with optional filtering."""
        return installment_plan_repo.list_for_clinic(
            clinic_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=status,
        )

    def list_plans_for_clinic_paginated(
            self,
            clinic_id: int,
            *,
            patient_id: int | None = None,
            doctor_id: int | None = None,
            status: PlanStatus | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ):
        """Paginated list of plans for UI display."""
        return installment_plan_repo.list_for_clinic_paginated(
            clinic_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=status,
            page=page,
            page_size=page_size,
        )

    def update_plan(
            self,
            current_user: User,
            plan_id: int,
            payload: UpdateInstallmentPlanRequestSchema,
    ) -> Tuple[Optional[InstallmentPlan], Optional[str]]:
        """
        Updates an existing installment plan.

        Crucial Logic: This method checks if any payments have already been made
        towards this plan. If payments exist, modification of the installment
        structure (amounts/dates) is blocked to preserve the audit trail and
        financial integrity. Only basic metadata can be updated in that case.
        """
        if not current_user.clinic_id:
            return None, "user has no clinic assigned"

        clinic_id = current_user.clinic_id
        plan = installment_plan_repo.get_plan_in_clinic(plan_id, clinic_id)
        if not plan:
            return None, "plan not found"

        installment_plan_repo.update_plan_basic(
            plan,
            description=payload.description,
            total_amount=payload.total_amount,
            status=payload.status,
            start_date=payload.start_date,
        )

        if payload.installments is not None:
            has_payments = False
            for inst in plan.installments:
                if (inst.amount_paid or 0) > 0:
                    has_payments = True
                    break

            if has_payments:
                return None, "cannot change installments because payments have already been made"

            installments_data = [
                {
                    "due_date": inst.due_date,
                    "expected_amount": inst.expected_amount,
                }
                for inst in payload.installments
            ]
            installment_plan_repo.replace_installments(plan, installments_data)

        return plan, None

    def list_upcoming_installments_for_clinic(
            self,
            clinic_id: int,
            *,
            doctor_id: int | None = None,
            patient_id: int | None = None,
            from_date=None,
            page: int | None = None,
            page_size: int | None = None,
    ):
        """
        Retrieves installments due in the future (Expected Revenue).
        """
        return installment_plan_repo.list_upcoming_installments_for_clinic(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            from_date=from_date,
            page=page,
            page_size=page_size,
        )

    def list_overdue_installments_for_clinic(
            self,
            clinic_id: int,
            *,
            doctor_id: int | None = None,
            patient_id: int | None = None,
            to_date=None,
            page: int | None = None,
            page_size: int | None = None,
    ):
        """
        Retrieves installments that are past their due date and unpaid (Arrears).
        """
        return installment_plan_repo.list_overdue_installments_for_clinic(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            to_date=to_date,
            page=page,
            page_size=page_size,
        )

    def cancel_plan(
            self,
            current_user: User,
            plan_id: int
    ):
        """
        Marks a plan as CANCELLED.

        This halts any future billing but retains the record for historical purposes.
        """
        if not current_user.clinic_id:
            return None, "user has no clinic assigned"

        clinic_id = current_user.clinic_id
        plan = installment_plan_repo.get_plan_in_clinic(plan_id, clinic_id)
        if not plan:
            return None, "plan not found"

        installment_plan_repo.update_plan_basic(plan, status=PlanStatus.CANCELLED)

        return plan, None


installment_service = InstallmentService()
