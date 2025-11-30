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
    def create_plan(
            self,
            current_user: User,
            payload: CreateInstallmentPlanRequestSchema,
    ) -> Tuple[Optional[InstallmentPlan], Optional[str]]:
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
        return installment_plan_repo.get_plan_in_clinic(plan_id, clinic_id)

    def list_plans_for_clinic(
            self,
            clinic_id: int,
            *,
            patient_id: int | None = None,
            doctor_id: int | None = None,
            status: PlanStatus | None = None,
    ):
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
        return installment_plan_repo.list_overdue_installments_for_clinic(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            to_date=to_date,
            page=page,
            page_size=page_size,
        )


installment_service = InstallmentService()
