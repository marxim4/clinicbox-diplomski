from __future__ import annotations

from datetime import date
from typing import List, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import InstallmentPlan, Installment
from ..enums import PlanStatus
from ..utils.pagination import validate_pagination, page_meta


class InstallmentPlanRepository:
    def get_plan_in_clinic(
            self,
            plan_id: int,
            clinic_id: int,
    ):
        stmt = (
            select(InstallmentPlan)
            .options(joinedload(InstallmentPlan.installments))
            .where(
                InstallmentPlan.plan_id == plan_id,
                InstallmentPlan.clinic_id == clinic_id,
            )
        )
        return db.session.scalar(stmt)

    def get_installment_in_clinic(self, installment_id, clinic_id):
        stmt = (
            select(Installment)
            .join(InstallmentPlan, Installment.plan_id == InstallmentPlan.plan_id)
            .where(
                Installment.installment_id == installment_id,
                InstallmentPlan.clinic_id == clinic_id,
            )
        )
        return db.session.scalar(stmt)

    def list_for_clinic(
            self,
            clinic_id: int,
            *,
            patient_id: int | None = None,
            doctor_id: int | None = None,
            status: PlanStatus | None = None,
    ):
        base = (
            select(InstallmentPlan)
            .options(joinedload(InstallmentPlan.installments))
            .where(InstallmentPlan.clinic_id == clinic_id)
        )

        if patient_id is not None:
            base = base.where(InstallmentPlan.patient_id == patient_id)
        if doctor_id is not None:
            base = base.where(InstallmentPlan.doctor_id == doctor_id)
        if status is not None:
            base = base.where(InstallmentPlan.status == status)

        stmt = base.order_by(
            InstallmentPlan.start_date.asc().nulls_last(),
            InstallmentPlan.plan_id.asc(),
        )
        return db.session.scalars(stmt).all()

    def list_for_clinic_paginated(
            self,
            clinic_id: int,
            *,
            patient_id: int | None = None,
            doctor_id: int | None = None,
            status: PlanStatus | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ) -> Tuple[List[InstallmentPlan], dict]:
        page, page_size = validate_pagination(page, page_size)

        base = select(InstallmentPlan).where(InstallmentPlan.clinic_id == clinic_id)

        if patient_id is not None:
            base = base.where(InstallmentPlan.patient_id == patient_id)
        if doctor_id is not None:
            base = base.where(InstallmentPlan.doctor_id == doctor_id)
        if status is not None:
            base = base.where(InstallmentPlan.status == status)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.options(joinedload(InstallmentPlan.installments))
            .order_by(
                InstallmentPlan.start_date.asc().nulls_last(),
                InstallmentPlan.plan_id.asc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()

        meta = page_meta(page, page_size, total_items)
        return items, meta

    def create_plan(
            self,
            *,
            clinic_id: int,
            patient_id: int,
            doctor_id: int,
            description: str | None,
            total_amount: float,
            status: PlanStatus,
            start_date,
            installments_data: list[dict] | None,
    ) -> InstallmentPlan:
        plan = InstallmentPlan(
            clinic_id=clinic_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            description=description,
            total_amount=total_amount,
            status=status,
            start_date=start_date,
        )
        db.session.add(plan)
        db.session.flush()

        if installments_data:
            self._replace_installments(plan, installments_data)

        return plan

    def update_plan_basic(
            self,
            plan: InstallmentPlan,
            *,
            description: str | None = None,
            total_amount: float | None = None,
            status: PlanStatus | None = None,
            start_date=None,
    ) -> InstallmentPlan:
        if description is not None:
            plan.description = description
        if total_amount is not None:
            plan.total_amount = total_amount
        if status is not None:
            plan.status = status
        if start_date is not None:
            plan.start_date = start_date
        db.session.flush()
        return plan

    def replace_installments(
            self,
            plan: InstallmentPlan,
            installments_data: list[dict],
    ) -> InstallmentPlan:
        self._replace_installments(plan, installments_data)
        return plan

    def _replace_installments(
            self,
            plan: InstallmentPlan,
            installments_data: list[dict],
    ):
        plan.installments.clear()
        db.session.flush()

        for idx, inst in enumerate(installments_data, start=1):
            installment = Installment(
                plan_id=plan.plan_id,
                sequence=idx,
                due_date=inst["due_date"],
                expected_amount=inst["expected_amount"],
            )
            db.session.add(installment)

        db.session.flush()

    def list_upcoming_installments_for_clinic(
            self,
            clinic_id: int,
            *,
            doctor_id: int | None = None,
            patient_id: int | None = None,
            from_date: date | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ):
        if from_date is None:
            from_date = date.today()

        page, page_size = validate_pagination(page, page_size)

        base = (
            select(Installment, InstallmentPlan.patient_id, InstallmentPlan.doctor_id)
            .join(InstallmentPlan, Installment.plan_id == InstallmentPlan.plan_id)
            .where(
                InstallmentPlan.clinic_id == clinic_id,
                Installment.due_date >= from_date,
                Installment.amount_paid < Installment.expected_amount,
            )
        )

        if doctor_id is not None:
            base = base.where(InstallmentPlan.doctor_id == doctor_id)
        if patient_id is not None:
            base = base.where(InstallmentPlan.patient_id == patient_id)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(
                Installment.due_date.asc(),
                Installment.sequence.asc(),
                Installment.installment_id.asc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )

        rows = db.session.execute(stmt).all()

        items = [
            {
                "installment_id": inst.installment_id,
                "plan_id": inst.plan_id,
                "due_date": inst.due_date,
                "expected_amount": float(inst.expected_amount),
                "patient_id": patient_id_,
                "doctor_id": doctor_id_,
            }
            for inst, patient_id_, doctor_id_ in rows
        ]

        meta = page_meta(page, page_size, total_items)
        return items, meta

    def list_overdue_installments_for_clinic(
            self,
            clinic_id: int,
            *,
            doctor_id: int | None = None,
            patient_id: int | None = None,
            to_date: date | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ):
        if to_date is None:
            to_date = date.today()

        page, page_size = validate_pagination(page, page_size)

        base = (
            select(Installment, InstallmentPlan.patient_id, InstallmentPlan.doctor_id)
            .join(InstallmentPlan, Installment.plan_id == InstallmentPlan.plan_id)
            .where(
                InstallmentPlan.clinic_id == clinic_id,
                Installment.due_date < to_date,
                Installment.amount_paid < Installment.expected_amount,
            )
        )

        if doctor_id is not None:
            base = base.where(InstallmentPlan.doctor_id == doctor_id)
        if patient_id is not None:
            base = base.where(InstallmentPlan.patient_id == patient_id)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(
                Installment.due_date.asc(),
                Installment.sequence.asc(),
                Installment.installment_id.asc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )

        rows = db.session.execute(stmt).all()

        items = [
            {
                "installment_id": inst.installment_id,
                "plan_id": inst.plan_id,
                "due_date": inst.due_date,
                "expected_amount": float(inst.expected_amount),
                "patient_id": patient_id_,
                "doctor_id": doctor_id_,
            }
            for inst, patient_id_, doctor_id_ in rows
        ]

        meta = page_meta(page, page_size, total_items)
        return items, meta


installment_plan_repo = InstallmentPlanRepository()
