from __future__ import annotations

from datetime import datetime, date

from ..models import User
from ..data_layer.report_repository import report_repo


class ReportService:
    def doctor_revenue(
        self,
        current_user: User,
        *,
        date_from: datetime | date | None,
        date_to: datetime | date | None,
        doctor_id: int | None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        items = report_repo.doctor_revenue(
            clinic_id=clinic_id,
            date_from=date_from,
            date_to=date_to,
            doctor_id=doctor_id,
        )
        return items, None

    def category_expenses(
        self,
        current_user: User,
        *,
        date_from: datetime | date | None,
        date_to: datetime | date | None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        items = report_repo.category_expenses(
            clinic_id=clinic_id,
            date_from=date_from,
            date_to=date_to,
        )
        return items, None

    def cashbox_summary(
        self,
        current_user: User,
        *,
        date_from: datetime | date | None,
        date_to: datetime | date | None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        items = report_repo.cashbox_summary(
            clinic_id=clinic_id,
            date_from=date_from,
            date_to=date_to,
        )
        return items, None

    def patient_financial_summary(
        self,
        current_user: User,
        patient_id: int,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        data = report_repo.patient_financial_summary(
            clinic_id=clinic_id,
            patient_id=patient_id,
        )
        if not data:
            return None, "patient not found or no data"
        return data, None

    def top_debtors(
        self,
        current_user: User,
        *,
        limit: int = 20,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        items = report_repo.top_debtors(
            clinic_id=clinic_id,
            limit=limit,
        )
        return items, None


report_service = ReportService()
