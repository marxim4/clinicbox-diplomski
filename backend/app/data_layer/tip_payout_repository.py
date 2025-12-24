from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timedelta

from sqlalchemy import select, func

from ..extensions import db
from ..models import TipPayout
from ..enums import TransactionStatus


class TipPayoutRepository:
    def get_by_id_in_clinic(self, payout_id: int, clinic_id: int) -> Optional[TipPayout]:
        return db.session.scalar(
            select(TipPayout).where(
                TipPayout.payout_id == payout_id,
                TipPayout.clinic_id == clinic_id
            )
        )

    def create_payout(
            self,
            *,
            clinic_id: int,
            doctor_id: int,
            amount: float,
            created_by: int,
            session_user_id: int,
            note: str | None = None,
            status: str,
            approved_by: int | None = None,
    ):
        payout = TipPayout(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            amount=amount,
            created_by=created_by,
            session_user_id=session_user_id,
            note=note,
            status=status,
            approved_by=approved_by,
        )
        db.session.add(payout)
        db.session.flush()
        return payout

    def list_payouts_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        stmt = (
            select(TipPayout)
            .where(
                TipPayout.clinic_id == clinic_id,
                TipPayout.doctor_id == doctor_id,
            )
            .order_by(TipPayout.created_at.desc())
        )
        return db.session.scalars(stmt).all()

    def sum_payouts_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
            date_from: Optional[datetime] = None,
            date_to: Optional[datetime] = None,
    ):
        stmt = select(func.coalesce(func.sum(TipPayout.amount), 0)).where(
            TipPayout.clinic_id == clinic_id,
            TipPayout.doctor_id == doctor_id,
            TipPayout.status == TransactionStatus.CONFIRMED.value
        )

        if date_from is not None:
            stmt = stmt.where(TipPayout.created_at >= date_from)
        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0 and date_to.minute == 0:
                stmt = stmt.where(TipPayout.created_at < date_to + timedelta(days=1))
            else:
                stmt = stmt.where(TipPayout.created_at <= date_to)

        total = db.session.scalar(stmt)
        return float(total or 0)

    def get_with_lock(self, payout_id: int, clinic_id: int):
        return (
            db.session.query(TipPayout)
            .filter_by(payout_id=payout_id, clinic_id=clinic_id)
            .with_for_update()
            .first()
        )


tip_payout_repo = TipPayoutRepository()
