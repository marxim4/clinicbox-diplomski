from __future__ import annotations

from datetime import datetime, date, timedelta

from sqlalchemy import select, func, case
from sqlalchemy.orm import aliased

from ..extensions import db
from ..models import (
    Payment,
    User,
    CashTransaction,
    Cashbox,
    Category,
    InstallmentPlan,
    Installment,
    Patient,
)
from ..enums import CashTransactionType, PlanStatus


class ReportRepository:
    def doctor_revenue(
        self,
        clinic_id: int,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
        doctor_id: int | None = None,
    ):
        base = (
            select(
                Payment.doctor_id,
                func.coalesce(func.sum(Payment.amount), 0).label("total_amount"),
                func.coalesce(func.sum(Payment.tip_amount), 0).label("total_tip_amount"),
                func.count(Payment.payment_id).label("payments_count"),
            )
            .where(Payment.clinic_id == clinic_id)
        )

        if doctor_id is not None:
            base = base.where(Payment.doctor_id == doctor_id)

        if date_from is not None:
            base = base.where(Payment.created_at >= date_from)
        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0 and date_to.minute == 0:
                base = base.where(Payment.created_at < date_to + timedelta(days=1))
            else:
                base = base.where(Payment.created_at <= date_to)

        base = base.group_by(Payment.doctor_id)

        user_alias = aliased(User)
        stmt = (
            select(
                base.subquery().c.doctor_id,
                base.subquery().c.total_amount,
                base.subquery().c.total_tip_amount,
                base.subquery().c.payments_count,
                user_alias.first_name,
                user_alias.last_name,
            )
            .join(
                user_alias,
                user_alias.user_id == base.subquery().c.doctor_id,
                isouter=True,
            )
            .order_by(base.subquery().c.total_amount.desc())
        )

        rows = db.session.execute(stmt).all()

        items = []
        for row in rows:
            doctor_id, total_amount, total_tip, payments_count, first_name, last_name = row
            if first_name or last_name:
                name = f"{first_name or ''} {last_name or ''}".strip()
            else:
                name = None

            items.append(
                {
                    "doctor_id": doctor_id,
                    "doctor_name": name,
                    "total_amount": float(total_amount or 0),
                    "total_tip_amount": float(total_tip or 0),
                    "payments_count": int(payments_count or 0),
                }
            )

        return items

    def category_expenses(
        self,
        clinic_id: int,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
    ):
        base = (
            select(
                Category.category_id,
                Category.name,
                func.coalesce(func.sum(CashTransaction.amount), 0).label("total_amount"),
            )
            .join(
                CashTransaction,
                CashTransaction.category_id == Category.category_id,
            )
            .where(
                Category.clinic_id == clinic_id,
                CashTransaction.clinic_id == clinic_id,
                CashTransaction.type == CashTransactionType.OUT,
            )
        )

        if date_from is not None:
            base = base.where(CashTransaction.occurred_at >= date_from)
        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0 and date_to.minute == 0:
                base = base.where(CashTransaction.occurred_at < date_to + timedelta(days=1))
            else:
                base = base.where(CashTransaction.occurred_at <= date_to)

        base = base.group_by(Category.category_id, Category.name)
        base = base.order_by(func.coalesce(func.sum(CashTransaction.amount), 0).desc())

        rows = db.session.execute(base).all()

        return [
            {
                "category_id": cid,
                "name": name,
                "total_amount": float(total or 0),
            }
            for cid, name, total in rows
        ]

    def cashbox_summary(
        self,
        clinic_id: int,
        date_from: datetime | date | None = None,
        date_to: datetime | date | None = None,
    ):
        base = (
            select(
                CashTransaction.cashbox_id,
                func.sum(
                    case(
                        (CashTransaction.type == CashTransactionType.IN, CashTransaction.amount),
                        else_=0,
                    )
                ).label("total_in"),
                func.sum(
                    case(
                        (CashTransaction.type == CashTransactionType.OUT, CashTransaction.amount),
                        else_=0,
                    )
                ).label("total_out"),
                func.sum(
                    case(
                        (CashTransaction.type == CashTransactionType.ADJUSTMENT, CashTransaction.amount),
                        else_=0,
                    )
                ).label("total_adjustment"),
            )
            .where(CashTransaction.clinic_id == clinic_id)
            .group_by(CashTransaction.cashbox_id)
        )

        if date_from is not None:
            base = base.where(CashTransaction.occurred_at >= date_from)
        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0 and date_to.minute == 0:
                base = base.where(CashTransaction.occurred_at < date_to + timedelta(days=1))
            else:
                base = base.where(CashTransaction.occurred_at <= date_to)

        subq = base.subquery()

        stmt = (
            select(
                Cashbox.cashbox_id,
                Cashbox.name,
                func.coalesce(subq.c.total_in, 0),
                func.coalesce(subq.c.total_out, 0),
                func.coalesce(subq.c.total_adjustment, 0),
            )
            .join(subq, subq.c.cashbox_id == Cashbox.cashbox_id)
            .where(Cashbox.clinic_id == clinic_id)
            .order_by(Cashbox.name.asc())
        )

        rows = db.session.execute(stmt).all()
        items = []
        for cashbox_id, name, total_in, total_out, total_adj in rows:
            total_in = float(total_in or 0)
            total_out = float(total_out or 0)
            total_adj = float(total_adj or 0)
            net = total_in - total_out + total_adj
            items.append(
                {
                    "cashbox_id": cashbox_id,
                    "name": name,
                    "total_in": total_in,
                    "total_out": total_out,
                    "total_adjustment": total_adj,
                    "net": round(net, 2),
                }
            )
        return items

    def patient_financial_summary(
        self,
        clinic_id: int,
        patient_id: int,
    ):
        planned_stmt = (
            select(func.coalesce(func.sum(InstallmentPlan.total_amount), 0))
            .where(
                InstallmentPlan.clinic_id == clinic_id,
                InstallmentPlan.patient_id == patient_id,
            )
        )
        total_planned = float(db.session.scalar(planned_stmt) or 0)

        paid_stmt = (
            select(
                func.coalesce(func.sum(Payment.amount), 0),
                func.coalesce(func.sum(Payment.tip_amount), 0),
                func.min(Payment.created_at),
                func.max(Payment.created_at),
            )
            .where(
                Payment.clinic_id == clinic_id,
                Payment.patient_id == patient_id,
            )
        )
        paid_sum, tips_sum, first_dt, last_dt = db.session.execute(paid_stmt).one()
        total_paid = float(paid_sum or 0)
        total_tips = float(tips_sum or 0)

        debt_stmt = (
            select(
                func.coalesce(
                    func.sum(
                        Installment.expected_amount - func.coalesce(Installment.amount_paid, 0)
                    ),
                    0,
                )
            )
            .join(InstallmentPlan, Installment.plan_id == InstallmentPlan.plan_id)
            .where(
                InstallmentPlan.clinic_id == clinic_id,
                InstallmentPlan.patient_id == patient_id,
            )
        )
        remaining_debt = float(db.session.scalar(debt_stmt) or 0)

        active_stmt = (
            select(
                func.count(InstallmentPlan.plan_id),
                func.count(
                    func.nullif(
                        case(
                            (InstallmentPlan.status == PlanStatus.OVERDUE, 1),
                            else_=0,
                        ),
                        0,
                    )
                ),
            )
            .where(
                InstallmentPlan.clinic_id == clinic_id,
                InstallmentPlan.patient_id == patient_id,
            )
        )
        active_count, overdue_count = db.session.execute(active_stmt).one()
        active_plans_count = int(active_count or 0)
        overdue_plans_count = int(overdue_count or 0)

        p_stmt = (
            select(Patient.first_name, Patient.last_name)
            .where(
                Patient.clinic_id == clinic_id,
                Patient.patient_id == patient_id,
            )
        )
        p_row = db.session.execute(p_stmt).one_or_none()
        if p_row:
            first_name, last_name = p_row
            patient_name = f"{first_name or ''} {last_name or ''}".strip() or None
        else:
            patient_name = None

        return {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "total_planned": round(total_planned, 2),
            "total_paid": round(total_paid, 2),
            "total_tips": round(total_tips, 2),
            "remaining_debt": round(remaining_debt, 2),
            "active_plans_count": active_plans_count,
            "overdue_plans_count": overdue_plans_count,
            "first_payment_date": first_dt,
            "last_payment_date": last_dt,
        }

    def top_debtors(
        self,
        clinic_id: int,
        limit: int = 20,
    ):
        debt_subq = (
            select(
                InstallmentPlan.patient_id.label("patient_id"),
                func.coalesce(
                    func.sum(
                        Installment.expected_amount
                        - func.coalesce(Installment.amount_paid, 0)
                    ),
                    0,
                ).label("remaining_debt"),
            )
            .join(InstallmentPlan, Installment.plan_id == InstallmentPlan.plan_id)
            .where(
                InstallmentPlan.clinic_id == clinic_id,
                InstallmentPlan.patient_id.isnot(None),
            )
            .group_by(InstallmentPlan.patient_id)
        ).subquery()

        pay_subq = (
            select(
                Payment.patient_id.label("patient_id"),
                func.max(Payment.created_at).label("last_payment_date"),
            )
            .where(
                Payment.clinic_id == clinic_id,
                Payment.patient_id.isnot(None),
            )
            .group_by(Payment.patient_id)
        ).subquery()

        stmt = (
            select(
                debt_subq.c.patient_id,
                Patient.first_name,
                Patient.last_name,
                debt_subq.c.remaining_debt,
                pay_subq.c.last_payment_date,
            )
            .join(
                Patient,
                Patient.patient_id == debt_subq.c.patient_id,
            )
            .join(
                pay_subq,
                pay_subq.c.patient_id == debt_subq.c.patient_id,
                isouter=True,
            )
            .where(debt_subq.c.remaining_debt > 0)
            .order_by(debt_subq.c.remaining_debt.desc())
            .limit(limit)
        )

        rows = db.session.execute(stmt).all()

        items = []
        for pid, first_name, last_name, remaining, last_dt in rows:
            name = f"{first_name or ''} {last_name or ''}".strip() or None
            items.append(
                {
                    "patient_id": pid,
                    "patient_name": name,
                    "remaining_debt": round(float(remaining or 0), 2),
                    "last_payment_date": last_dt,
                }
            )
        return items


report_repo = ReportRepository()
