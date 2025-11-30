from __future__ import annotations

from typing import List, Optional
from datetime import datetime

from sqlalchemy import select, func

from ..extensions import db
from ..models import Tip


class TipRepository:

    def create_tip(
            self,
            *,
            clinic_id: int,
            doctor_id: int,
            amount: float,
            patient_id: int | None,
            plan_id: int | None,
            created_by: int,
    ):
        tip = Tip(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            plan_id=plan_id,
            amount=amount,
            created_by=created_by,
        )
        db.session.add(tip)
        db.session.flush()
        return tip

    def list_tips_for_doctor(self, clinic_id: int, doctor_id: int):
        stmt = (
            select(Tip)
            .where(
                Tip.clinic_id == clinic_id,
                Tip.doctor_id == doctor_id,
            )
            .order_by(Tip.created_at.desc())
        )
        return db.session.scalars(stmt).all()

    def list_tips_for_patient(self, clinic_id: int, patient_id: int) -> List[Tip]:
        stmt = select(Tip).where(
            Tip.clinic_id == clinic_id,
            Tip.patient_id == patient_id,
        )
        return db.session.scalars(stmt).all()

    def list_tips_for_plan(self, plan_id: int) -> List[Tip]:
        stmt = select(Tip).where(Tip.plan_id == plan_id)
        return db.session.scalars(stmt).all()

    def sum_tips_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
            date_from: Optional[datetime] = None,
            date_to: Optional[datetime] = None,
    ):
        stmt = select(func.coalesce(func.sum(Tip.amount), 0)).where(
            Tip.clinic_id == clinic_id,
            Tip.doctor_id == doctor_id,
        )
        if date_from is not None:
            stmt = stmt.where(Tip.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Tip.created_at <= date_to)

        total = db.session.scalar(stmt)
        return float(total or 0)

    def sum_tips_for_clinic(
            self,
            clinic_id: int,
            date_from: Optional[datetime] = None,
            date_to: Optional[datetime] = None,
    ) -> float:
        stmt = select(func.coalesce(func.sum(Tip.amount), 0)).where(
            Tip.clinic_id == clinic_id,
        )
        if date_from is not None:
            stmt = stmt.where(Tip.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(Tip.created_at <= date_to)

        total = db.session.scalar(stmt)
        return float(total or 0)


tip_repo = TipRepository()
