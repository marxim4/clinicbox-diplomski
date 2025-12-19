from __future__ import annotations

from typing import List, Optional, Tuple

from datetime import datetime, date, timedelta

from sqlalchemy import select, func, and_

from ..extensions import db
from ..models import Payment
from ..enums import PaymentMethod
from ..utils.pagination import validate_pagination, page_meta


class PaymentRepository:
    def get_by_id_in_clinic(self, payment_id: int, clinic_id: int):
        stmt = select(Payment).where(
            Payment.payment_id == payment_id,
            Payment.clinic_id == clinic_id,
        )
        return db.session.scalar(stmt)

    def list_for_plan(
            self,
            clinic_id: int,
            plan_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ) -> Tuple[List[Payment], Optional[dict]]:
        base = select(Payment).where(
            Payment.clinic_id == clinic_id,
            Payment.plan_id == plan_id,
        )

        if page is None and page_size is None:
            stmt = base.order_by(Payment.created_at.desc())
            items = db.session.scalars(stmt).all()
            return items, None

        page, page_size = validate_pagination(page, page_size)
        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(Payment.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()

        meta = page_meta(page, page_size, total_items)
        return items, meta

    def list_for_installment(
            self,
            clinic_id: int,
            installment_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ) -> Tuple[List[Payment], Optional[dict]]:
        base = select(Payment).where(
            Payment.clinic_id == clinic_id,
            Payment.installment_id == installment_id,
        )

        if page is None and page_size is None:
            stmt = base.order_by(Payment.created_at.desc())
            items = db.session.scalars(stmt).all()
            return items, None

        page, page_size = validate_pagination(page, page_size)
        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(Payment.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()

        meta = page_meta(page, page_size, total_items)
        return items, meta

    def create_payment(
            self,
            *,
            clinic_id: int,
            patient_id: int | None,
            doctor_id: int,
            plan_id: int | None,
            installment_id: int | None,
            amount: float,
            tip_amount: float,
            method: PaymentMethod,
            created_by: int,
            session_user_id: int,
            status: str,
            target_cashbox_id: int | None = None,
    ):
        payment = Payment(
            clinic_id=clinic_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            plan_id=plan_id,
            installment_id=installment_id,
            amount=amount,
            tip_amount=tip_amount,
            method=method,
            created_by=created_by,
            session_user_id=session_user_id,
            status=status,
            target_cashbox_id=target_cashbox_id,
        )
        db.session.add(payment)
        db.session.flush()
        return payment

    def search(
            self,
            clinic_id: int,
            *,
            doctor_id: int | None = None,
            patient_id: int | None = None,
            method: PaymentMethod | None = None,
            date_from: datetime | date | None = None,
            date_to: datetime | date | None = None,
            min_amount: float | None = None,
            max_amount: float | None = None,
            has_tip: bool | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ) -> Tuple[List[Payment], Optional[dict]]:
        base = select(Payment).where(Payment.clinic_id == clinic_id)

        if doctor_id is not None:
            base = base.where(Payment.doctor_id == doctor_id)
        if patient_id is not None:
            base = base.where(Payment.patient_id == patient_id)
        if method is not None:
            base = base.where(Payment.method == method)

        if date_from is not None:
            base = base.where(Payment.created_at >= date_from)
        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0 and date_to.minute == 0:
                base = base.where(Payment.created_at < date_to + timedelta(days=1))
            else:
                base = base.where(Payment.created_at <= date_to)

        if min_amount is not None:
            base = base.where(Payment.amount >= min_amount)
        if max_amount is not None:
            base = base.where(Payment.amount <= max_amount)

        if has_tip is True:
            base = base.where(Payment.tip_amount > 0)
        elif has_tip is False:
            base = base.where(Payment.tip_amount <= 0)

        if page is None and page_size is None:
            stmt = base.order_by(Payment.created_at.desc())
            items = db.session.scalars(stmt).all()
            return items, None

        page, page_size = validate_pagination(page, page_size)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(Payment.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()
        meta = page_meta(page, page_size, total_items)
        return items, meta


payment_repo = PaymentRepository()
