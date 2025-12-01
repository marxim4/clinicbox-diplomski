from __future__ import annotations

from sqlalchemy import select

from ..enums import CashTransactionType
from ..extensions import db
from ..models import Cashbox


class CashboxRepository:
    def get_in_clinic(self, cashbox_id: int, clinic_id: int):
        stmt = select(Cashbox).where(
            Cashbox.cashbox_id == cashbox_id,
            Cashbox.clinic_id == clinic_id,
        )
        return db.session.scalar(stmt)

    def list_for_clinic(self, clinic_id: int, include_inactive: bool = False):
        base = select(Cashbox).where(Cashbox.clinic_id == clinic_id)
        if not include_inactive:
            base = base.where(Cashbox.is_active.is_(True))
        stmt = base.order_by(Cashbox.name.asc())
        return db.session.scalars(stmt).all()

    def create_cashbox(self, clinic_id: int, name: str, description: str | None):
        cashbox = Cashbox(
            clinic_id=clinic_id,
            name=name,
            description=description,
            is_active=True,
        )
        db.session.add(cashbox)
        db.session.flush()
        return cashbox

    def update_cashbox(
            self,
            cashbox: Cashbox,
            name: str | None = None,
            description: str | None = None,
            is_active: bool | None = None,
    ):
        if name is not None:
            cashbox.name = name
        if description is not None:
            cashbox.description = description
        if is_active is not None:
            cashbox.is_active = is_active
        db.session.flush()
        return cashbox

    def adjust_balance_for_transaction(self, cashbox: Cashbox, tx_type, amount: float):
        if tx_type == CashTransactionType.IN:
            cashbox.current_amount = (cashbox.current_amount or 0) + amount
        elif tx_type == CashTransactionType.OUT:
            cashbox.current_amount = (cashbox.current_amount or 0) - amount
        elif tx_type == CashTransactionType.ADJUSTMENT:
            # adjustment can be + or -
            cashbox.current_amount = (cashbox.current_amount or 0) + amount

        db.session.flush()
        return cashbox


cashbox_repo = CashboxRepository()
