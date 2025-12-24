from __future__ import annotations

from decimal import Decimal
from sqlalchemy import select, update
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

    def get_default_for_clinic(self, clinic_id: int) -> Cashbox | None:
        """
        Fetch the cashbox marked explicitly as default.
        """
        stmt = select(Cashbox).where(
            Cashbox.clinic_id == clinic_id,
            Cashbox.is_default.is_(True)
        )
        return db.session.scalar(stmt)

    def _unset_other_defaults(self, clinic_id: int):
        """
        Helper to ensure only one cashbox is default at a time.
        We run this before setting a new one to True to satisfy the DB constraint.
        """
        stmt = (
            update(Cashbox)
            .where(Cashbox.clinic_id == clinic_id)
            .where(Cashbox.is_default.is_(True))
            .values(is_default=False)
        )
        db.session.execute(stmt)

    def create_cashbox(self, clinic_id: int, name: str, description: str | None, is_default: bool = False):
        if is_default:
            self._unset_other_defaults(clinic_id)

        cashbox = Cashbox(
            clinic_id=clinic_id,
            name=name,
            description=description,
            is_active=True,
        )
        if is_default:
            cashbox.is_default = True

        db.session.add(cashbox)
        db.session.flush()
        return cashbox

    def update_cashbox(
            self,
            cashbox: Cashbox,
            name: str | None = None,
            description: str | None = None,
            is_active: bool | None = None,
            is_default: bool | None = None
    ):
        if name is not None:
            cashbox.name = name
        if description is not None:
            cashbox.description = description
        if is_active is not None:
            cashbox.is_active = is_active

        if is_default is True and not cashbox.is_default:
            self._unset_other_defaults(cashbox.clinic_id)
            cashbox.is_default = True
        elif is_default is False:
            cashbox.is_default = False

        db.session.flush()
        return cashbox

    def adjust_balance_for_transaction(self, cashbox: Cashbox, tx_type, amount: float):
        amount_dec = Decimal(str(amount))
        current_dec = cashbox.current_amount if cashbox.current_amount is not None else Decimal("0.00")

        if tx_type == CashTransactionType.IN:
            cashbox.current_amount = current_dec + amount_dec
        elif tx_type == CashTransactionType.OUT:
            cashbox.current_amount = current_dec - amount_dec
        elif tx_type == CashTransactionType.ADJUSTMENT:
            cashbox.current_amount = current_dec + amount_dec

        db.session.flush()
        return cashbox


cashbox_repo = CashboxRepository()
