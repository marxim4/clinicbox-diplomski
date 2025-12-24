from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from ..models import User, CashTransaction
from ..enums import CashTransactionType, TransactionStatus
from ..data_layer.cashbox_repository import cashbox_repo
from ..data_layer.cash_transaction_repository import cash_tx_repo
from ..data_layer.payment_repository import payment_repo
from ..data_layer.category_repository import category_repo
from ..data_layer.clinic_repository import clinic_repo
from ..schemas.cash import (
    CreateCashboxRequestSchema,
    UpdateCashboxRequestSchema,
    CreateCashTransactionRequestSchema,
)


class CashService:
    # -------- cashboxes --------

    def create_cashbox(
            self,
            current_user: User,
            payload: CreateCashboxRequestSchema,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        cashbox = cashbox_repo.create_cashbox(
            clinic_id=clinic_id,
            name=payload.name,
            description=payload.description,
        )
        return cashbox, None

    def list_cashboxes_for_user(
            self,
            current_user: User,
            include_inactive: bool = False,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return [], "user has no clinic assigned"

        items = cashbox_repo.list_for_clinic(
            clinic_id,
            include_inactive=include_inactive,
        )
        return items, None

    def update_cashbox(
            self,
            current_user: User,
            cashbox_id: int,
            payload: UpdateCashboxRequestSchema,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)
        if not cashbox:
            return None, "cashbox not found"

        updated = cashbox_repo.update_cashbox(
            cashbox,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
        )
        return updated, None

    def get_cashbox_balance(
            self,
            current_user: User,
            cashbox_id: int,
            date_from: datetime | None = None,
            date_to: datetime | None = None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)
        if not cashbox:
            return None, "cashbox not found"

        stats = cash_tx_repo.aggregate_for_cashbox(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            date_from=date_from,
            date_to=date_to,
        )

        return stats, None

    # -------- transactions --------

    def _ensure_cashbox_in_clinic(self, clinic_id: int, cashbox_id: int):
        cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)
        if not cashbox:
            return None, "cashbox not found in this clinic"
        if not cashbox.is_active:
            return None, "cashbox is not active"
        return cashbox, None

    def _resolve_links_for_transaction(
            self,
            clinic_id: int,
            payload: CreateCashTransactionRequestSchema,
    ):
        if payload.payment_id is not None:
            payment = payment_repo.get_by_id_in_clinic(payload.payment_id, clinic_id)
            if not payment:
                return "payment not found in this clinic"

        if payload.category_id is not None:
            category = category_repo.get_by_id_in_clinic(payload.category_id, clinic_id)
            if not category:
                return "category not found in this clinic"

        # tip_id / tip_payout_id are assumed already valid if provided
        return None

    def create_transaction(
            self,
            current_user: User,
            session_user: User,
            payload: CreateCashTransactionRequestSchema,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id: return None, "user has no clinic assigned"

        clinic = clinic_repo.get_by_id(clinic_id)

        # 1. Determine Status
        status = TransactionStatus.CONFIRMED.value

        # Logic: If clinic requires approval AND user is a Junior (requires approval)
        if clinic.requires_cash_approval and current_user.requires_approval_for_actions:
            status = TransactionStatus.PENDING.value

        # 2. Validation
        cashbox, err = self._ensure_cashbox_in_clinic(clinic_id, payload.cashbox_id)
        if err: return None, err

        link_error = self._resolve_links_for_transaction(clinic_id, payload)
        if link_error: return None, link_error

        # 3. Create Record
        tx = cash_tx_repo.create_transaction(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            type=payload.type,
            amount=float(payload.amount),
            payment_id=payload.payment_id,
            category_id=payload.category_id,
            tip_id=payload.tip_id,
            tip_payout_id=payload.tip_payout_id,
            note=payload.note,
            status=status,  # <--- Set Status
            occurred_at=payload.occurred_at,
            created_by=current_user.user_id,
            session_user_id=session_user.user_id,
        )

        # 4. Affect Balance (ONLY IF CONFIRMED)
        if status == TransactionStatus.CONFIRMED.value:
            cashbox_repo.adjust_balance_for_transaction(
                cashbox,
                payload.type,
                float(payload.amount),
            )
            # Increment category usage
            if payload.category_id is not None:
                category = category_repo.get_by_id_in_clinic(payload.category_id, clinic_id)
                if category:
                    category_repo.increment_usage(category, datetime.utcnow())

        return tx, None

    def approve_transaction(self, approver: User, tx_id: int) -> Tuple[Optional[CashTransaction], Optional[str]]:
        """
        Finalizes a PENDING Manual Transaction (Expense/Deposit).
        Uses ROW LOCKING to prevent race conditions.
        """
        if not approver.can_approve_financials:
            return None, "permission denied"

        # 1. LOCK
        tx = cash_tx_repo.get_with_lock(tx_id, approver.clinic_id)

        if not tx:
            return None, "transaction not found"

        if tx.status != TransactionStatus.PENDING.value:
            return None, "transaction is not pending"

        # 2. Update Status
        tx.status = TransactionStatus.CONFIRMED.value
        tx.approved_by = approver.user_id

        # 3. Affect Balance NOW
        # We need to fetch the cashbox to adjust it
        cashbox = cashbox_repo.get_in_clinic(tx.cashbox_id, approver.clinic_id)
        if cashbox:
            cashbox_repo.adjust_balance_for_transaction(
                cashbox,
                tx.type,
                float(tx.amount)
            )

        # 4. Update Category Usage
        if tx.category_id:
            category = category_repo.get_by_id_in_clinic(tx.category_id, approver.clinic_id)
            if category:
                category_repo.increment_usage(category, datetime.utcnow())

        return tx, None

    def reject_transaction(self, rejector: User, tx_id: int) -> Tuple[Optional[CashTransaction], Optional[str]]:
        """
        Marks a transaction as REJECTED and records who did it.
        No money moves (balance remains unchanged).
        """
        if not rejector.can_approve_financials:
            return None, "permission denied"

        # Lock to ensure consistency
        tx = cash_tx_repo.get_with_lock(tx_id, rejector.clinic_id)

        if not tx:
            return None, "transaction not found"

        if tx.status != TransactionStatus.PENDING.value:
            return None, "transaction is not pending"

        # 1. Update Status
        tx.status = TransactionStatus.REJECTED.value

        # 2. Record the Actor (Reuse the approved_by field)
        # This provides a permanent audit trail of who rejected the transaction.
        tx.approved_by = rejector.user_id

        return tx, None

    def search_transactions(
            self,
            current_user: User,
            *,
            cashbox_id: int | None,
            type,
            status,
            category_id: int | None,
            payment_id: int | None,
            date_from,
            date_to,
            min_amount,
            max_amount,
            page: int | None,
            page_size: int | None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, None, "user has no clinic assigned"

        items, meta = cash_tx_repo.search(
            clinic_id=clinic_id,
            cashbox_id=cashbox_id,
            type=type,
            status=status,
            category_id=category_id,
            payment_id=payment_id,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
            page=page,
            page_size=page_size,
        )
        return items, meta, None

    def adjust_cashbox_to_counted(
            self,
            current_user: User,
            session_user: User,
            cashbox_id: int,
            counted_total: float,
            note: str | None = None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)
        if not cashbox:
            return None, "cashbox not found"

        current = float(cashbox.current_amount or 0)
        diff = round(counted_total - current, 2)

        if abs(diff) < 0.0001:
            return {
                "adjusted": False,
                "current_amount": current,
                "counted_total": counted_total,
                "difference": 0.0,
            }, None

        tx = cash_tx_repo.create_transaction(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            type=CashTransactionType.ADJUSTMENT,
            amount=diff,
            payment_id=None,
            category_id=None,
            tip_id=None,
            tip_payout_id=None,
            note=note or f"Day close adjustment (diff={diff})",
            status=TransactionStatus.CONFIRMED,
            occurred_at=datetime.utcnow(),
            created_by=current_user.user_id,
            session_user_id=session_user.user_id,
        )

        cashbox_repo.adjust_balance_for_transaction(
            cashbox,
            CashTransactionType.ADJUSTMENT,
            diff,
        )

        return {
            "adjusted": True,
            "current_amount": float(cashbox.current_amount or 0),
            "counted_total": counted_total,
            "difference": diff,
            "tx_id": tx.tx_id,
        }, None


cash_service = CashService()
