from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple

from sqlalchemy import select, func

from ..extensions import db
from ..models import CashTransaction
from ..enums import CashTransactionType, TransactionStatus
from ..utils.pagination import validate_pagination, page_meta


class CashTransactionRepository:
    def get_by_id_in_clinic(self, tx_id: int, clinic_id: int) -> Optional[CashTransaction]:
        return db.session.scalar(
            select(CashTransaction).where(
                CashTransaction.tx_id == tx_id,
                CashTransaction.clinic_id == clinic_id
            )
        )

    def create_transaction(
            self,
            *,
            clinic_id: int,
            cashbox_id: int,
            type: CashTransactionType,
            amount: float,
            payment_id: int | None,
            category_id: int | None,
            tip_id: int | None,
            tip_payout_id: int | None,
            note: str | None,
            status: str,
            occurred_at: datetime | None,
            created_by: int,
            session_user_id: int,
            approved_by: int | None = None,
    ):
        tx = CashTransaction(
            clinic_id=clinic_id,
            cashbox_id=cashbox_id,
            type=type,
            payment_id=payment_id,
            category_id=category_id,
            tip_id=tip_id,
            tip_payout_id=tip_payout_id,
            amount=amount,
            occurred_at=occurred_at or datetime.utcnow(),
            status=status,
            note=note,
            created_by=created_by,
            session_user_id=session_user_id,
            approved_by=approved_by,
        )
        db.session.add(tx)
        db.session.flush()
        return tx

    def search(
            self,
            clinic_id: int,
            *,
            cashbox_id: int | None = None,
            type: CashTransactionType | None = None,
            status: str | None = None,
            category_id: int | None = None,
            payment_id: int | None = None,
            date_from: datetime | date | None = None,
            date_to: datetime | date | None = None,
            min_amount: float | None = None,
            max_amount: float | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ) -> Tuple[List[CashTransaction], Optional[dict]]:
        base = select(CashTransaction).where(
            CashTransaction.clinic_id == clinic_id
        )

        if cashbox_id is not None:
            base = base.where(CashTransaction.cashbox_id == cashbox_id)
        if type is not None:
            base = base.where(CashTransaction.type == type)
        if status is not None:
            base = base.where(CashTransaction.status == status)
        if category_id is not None:
            base = base.where(CashTransaction.category_id == category_id)
        if payment_id is not None:
            base = base.where(CashTransaction.payment_id == payment_id)

        if date_from is not None:
            base = base.where(CashTransaction.occurred_at >= date_from)
        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0:
                base = base.where(CashTransaction.occurred_at < date_to + timedelta(days=1))
            else:
                base = base.where(CashTransaction.occurred_at <= date_to)

        if min_amount is not None:
            base = base.where(CashTransaction.amount >= min_amount)
        if max_amount is not None:
            base = base.where(CashTransaction.amount <= max_amount)

        if page is None and page_size is None:
            stmt = base.order_by(CashTransaction.occurred_at.desc(), CashTransaction.tx_id.desc())
            items = db.session.scalars(stmt).all()
            return items, None

        page, page_size = validate_pagination(page, page_size)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(CashTransaction.occurred_at.desc(), CashTransaction.tx_id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()
        meta = page_meta(page, page_size, total_items)
        return items, meta

    def aggregate_for_cashbox(
            self,
            clinic_id: int,
            cashbox_id: int,
            *,
            date_from: datetime | date | None = None,
            date_to: datetime | date | None = None,
    ):
        base = select(CashTransaction).where(
            CashTransaction.clinic_id == clinic_id,
            CashTransaction.cashbox_id == cashbox_id,
            CashTransaction.status == TransactionStatus.CONFIRMED.value
        )

        if date_from is not None:
            base = base.where(CashTransaction.occurred_at >= date_from)
        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0:
                base = base.where(CashTransaction.occurred_at < date_to + timedelta(days=1))
            else:
                base = base.where(CashTransaction.occurred_at <= date_to)

        subq = base.subquery()

        sum_in = func.coalesce(
            select(func.sum(subq.c.amount))
            .where(subq.c.type == CashTransactionType.IN)
            .scalar_subquery(),
            0,
        )
        sum_out = func.coalesce(
            select(func.sum(subq.c.amount))
            .where(subq.c.type == CashTransactionType.OUT)
            .scalar_subquery(),
            0,
        )
        sum_adj = func.coalesce(
            select(func.sum(subq.c.amount))
            .where(subq.c.type == CashTransactionType.ADJUSTMENT)
            .scalar_subquery(),
            0,
        )

        total_in = db.session.scalar(select(sum_in)) or 0.0
        total_out = db.session.scalar(select(sum_out)) or 0.0
        total_adj = db.session.scalar(select(sum_adj)) or 0.0

        net = float(total_in) - float(total_out) + float(total_adj)

        return {
            "total_in": float(total_in),
            "total_out": float(total_out),
            "total_adjustment": float(total_adj),
            "net": round(net, 2),
        }

    def get_with_lock(self, transaction_id: int, clinic_id: int):
        stmt = select(CashTransaction).where(
            CashTransaction.transaction_id == transaction_id,
            CashTransaction.clinic_id == clinic_id
        ).with_for_update()
        return db.session.scalar(stmt)


cash_tx_repo = CashTransactionRepository()
