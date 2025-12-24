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
    """
    Service for managing Physical Cash Registers (Cashboxes) and their Transactions.

    This service enforces the 'Double-Entry' principle where a Cashbox balance is strictly
    the sum of its confirmed transactions. It also implements the 'Four-Eyes Principle'
    (Approval Workflow) for manual transactions created by junior staff.
    """

    def create_cashbox(
            self,
            current_user: User,
            payload: CreateCashboxRequestSchema,
    ):
        """
        Creates a new physical cash register (Cashbox) for the clinic.
        """
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
        """
        Retrieves all cashboxes assigned to the user's clinic.
        """
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
        """
        Updates metadata for a specific cashbox (name, description, active status).
        """
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
        """
        Calculates the aggregate financial stats (Total In, Total Out, Net Balance)
        for a specific cashbox over a given time period.
        """
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

    def _ensure_cashbox_in_clinic(self, clinic_id: int, cashbox_id: int):
        """Helper to validate that a cashbox belongs to the clinic and is active."""
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
        """Helper to ensure referenced entities (Payment, Category) exist in the clinic."""
        if payload.payment_id is not None:
            payment = payment_repo.get_by_id_in_clinic(payload.payment_id, clinic_id)
            if not payment:
                return "payment not found in this clinic"

        if payload.category_id is not None:
            category = category_repo.get_by_id_in_clinic(payload.category_id, clinic_id)
            if not category:
                return "category not found in this clinic"

        return None

    def create_transaction(
            self,
            current_user: User,
            session_user: User,
            payload: CreateCashTransactionRequestSchema,
    ):
        """
        Creates a new cash transaction (In/Out).

        Logic:
        1. Checks clinic settings (`requires_cash_approval`).
        2. Checks user role permissions (`requires_approval_for_actions`).
        3. If approval is required, the transaction is created as `PENDING`, and the
           cashbox balance is NOT updated.
        4. If approval is not required, the transaction is `CONFIRMED`, and the
           cashbox balance is updated immediately.
        """
        clinic_id = current_user.clinic_id
        if not clinic_id: return None, "user has no clinic assigned"

        clinic = clinic_repo.get_by_id(clinic_id)

        status = TransactionStatus.CONFIRMED.value

        if clinic.requires_cash_approval and current_user.requires_approval_for_actions:
            status = TransactionStatus.PENDING.value

        cashbox, err = self._ensure_cashbox_in_clinic(clinic_id, payload.cashbox_id)
        if err: return None, err

        link_error = self._resolve_links_for_transaction(clinic_id, payload)
        if link_error: return None, link_error

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
            status=status,
            occurred_at=payload.occurred_at,
            created_by=current_user.user_id,
            session_user_id=session_user.user_id,
        )

        if status == TransactionStatus.CONFIRMED.value:
            cashbox_repo.adjust_balance_for_transaction(
                cashbox,
                payload.type,
                float(payload.amount),
            )
            if payload.category_id is not None:
                category = category_repo.get_by_id_in_clinic(payload.category_id, clinic_id)
                if category:
                    category_repo.increment_usage(category, datetime.utcnow())

        return tx, None

    def approve_transaction(self, approver: User, tx_id: int) -> Tuple[Optional[CashTransaction], Optional[str]]:
        """
        Finalizes a PENDING transaction (e.g., an Expense created by a junior).

        This operation uses a database row lock to prevent race conditions.
        Once confirmed, the Cashbox balance is updated to reflect the movement.
        """
        if not approver.can_approve_financials:
            return None, "permission denied"

        tx = cash_tx_repo.get_with_lock(tx_id, approver.clinic_id)

        if not tx:
            return None, "transaction not found"

        if tx.status != TransactionStatus.PENDING.value:
            return None, "transaction is not pending"

        tx.status = TransactionStatus.CONFIRMED.value
        tx.approved_by = approver.user_id

        cashbox = cashbox_repo.get_in_clinic(tx.cashbox_id, approver.clinic_id)
        if cashbox:
            cashbox_repo.adjust_balance_for_transaction(
                cashbox,
                tx.type,
                float(tx.amount)
            )

        if tx.category_id:
            category = category_repo.get_by_id_in_clinic(tx.category_id, approver.clinic_id)
            if category:
                category_repo.increment_usage(category, datetime.utcnow())

        return tx, None

    def reject_transaction(self, rejector: User, tx_id: int) -> Tuple[Optional[CashTransaction], Optional[str]]:
        """
        Marks a pending transaction as REJECTED.

        The transaction remains in the database for audit purposes (with the rejector's ID),
        but the Cashbox balance is never impacted.
        """
        if not rejector.can_approve_financials:
            return None, "permission denied"

        tx = cash_tx_repo.get_with_lock(tx_id, rejector.clinic_id)

        if not tx:
            return None, "transaction not found"

        if tx.status != TransactionStatus.PENDING.value:
            return None, "transaction is not pending"

        tx.status = TransactionStatus.REJECTED.value
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
        """
        Searches financial transactions with support for filtering by date, type, status,
        and linked entities (Payment/Category).
        """
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
        """
        Performs a 'Reconciliation Adjustment'.

        Calculates the difference between the system's theoretical balance and the
        physical count. If a difference exists, creates an automatic ADJUSTMENT transaction
        to synchronize the system state with reality.
        """
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
