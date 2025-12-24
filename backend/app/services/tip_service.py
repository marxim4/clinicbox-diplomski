from __future__ import annotations

from typing import Optional, Tuple

from ..models import User, Tip, TipPayout

from ..data_layer.tip_repository import tip_repo
from ..data_layer.tip_payout_repository import tip_payout_repo
from ..data_layer.user_repository import user_repo
from ..data_layer.patient_repository import patient_repo
from ..data_layer.installment_plan_repository import installment_plan_repo
from ..data_layer.cashbox_repository import cashbox_repo
from ..data_layer.cash_transaction_repository import cash_tx_repo
from ..data_layer.clinic_repository import clinic_repo

from ..schemas.tips import CreateTipRequestSchema
from ..enums import CashTransactionType, TransactionStatus
from ..enums.tip_payout_status_enum import TipPayoutStatus


class TipService:
    """
    Service for managing the Tip (Gratuity) lifecycle.

    This service maintains a 'Secondary Ledger' for staff gratuities, distinct from
    the clinic's main revenue stream. It handles:
    1. Accumulation: Recording tips earned via payments or direct contributions.
    2. Accounting: Calculating real-time balances for each doctor.
    3. Disbursement: Managing the payout workflow (withdrawal of funds), including
       approval logic and physical cashbox reconciliation.
    """

    def _auto_cash_for_tip_payout(
            self,
            clinic_id: int,
            user_id: int,
            session_user_id: int,
            payout: TipPayout,
    ):
        """
        Internal helper to execute the physical cash movement for a confirmed payout.

        When a doctor withdraws tips, this method creates a 'Cash Out' transaction
        in the system, decreasing the physical cashbox balance to reflect the
        handover of currency.
        """
        cashbox_id = getattr(payout, 'cashbox_id', None)
        if cashbox_id:
            cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)
        else:
            cashbox = cashbox_repo.get_default_for_clinic(clinic_id)

        if not cashbox:
            return

        amount = float(payout.amount)

        cash_tx_repo.create_transaction(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            type=CashTransactionType.OUT,
            amount=amount,
            payment_id=None,
            category_id=None,
            tip_id=None,
            tip_payout_id=payout.payout_id,
            note=f"Tip payout #{payout.payout_id}",
            status=TransactionStatus.CONFIRMED.value,
            occurred_at=payout.created_at,
            created_by=user_id,
            session_user_id=session_user_id,
        )

        cashbox_repo.adjust_balance_for_transaction(
            cashbox,
            CashTransactionType.OUT,
            amount,
        )

    def create_tip(
            self,
            current_user: User,
            payload: CreateTipRequestSchema,
    ) -> Tuple[Optional[Tip], Optional[str]]:
        """
        Records a new tip entry.

        This is typically invoked automatically during payment processing but can
        be called directly for standalone tips.
        """
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        doctor = user_repo.get_by_id_in_clinic(payload.doctor_id, clinic_id)
        if not doctor:
            return None, "doctor not found in this clinic"

        if payload.patient_id is not None:
            patient = patient_repo.get_by_id_in_clinic(payload.patient_id, clinic_id)
            if not patient:
                return None, "patient not found in this clinic"

        if payload.plan_id is not None:
            plan = installment_plan_repo.get_plan_in_clinic(payload.plan_id, clinic_id)
            if not plan:
                return None, "plan not found in this clinic"

        tip = tip_repo.create_tip(
            clinic_id=clinic_id,
            doctor_id=payload.doctor_id,
            amount=payload.amount,
            patient_id=payload.patient_id,
            plan_id=payload.plan_id,
            created_by=current_user.user_id,
        )
        return tip, None

    def list_tips_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        """Retrieves tip history for a specific doctor."""
        return tip_repo.list_tips_for_doctor(clinic_id, doctor_id)

    def list_tips_for_patient(
            self,
            clinic_id: int,
            patient_id: int,
    ):
        """Retrieves tip history associated with a specific patient."""
        return tip_repo.list_tips_for_patient(clinic_id, patient_id)

    def list_tips_for_plan(
            self,
            plan_id: int,
    ):
        """Retrieves tips linked to a specific installment plan."""
        return tip_repo.list_tips_for_plan(plan_id)

    def get_doctor_tip_balance(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        """
        Calculates the current available tip balance for a doctor.

        Formula: Balance = (Total Lifetime Tips) - (Total Lifetime Payouts).
        """
        total_earned = tip_repo.sum_tips_for_doctor(clinic_id, doctor_id)
        total_paid_out = tip_payout_repo.sum_payouts_for_doctor(clinic_id, doctor_id)
        balance = total_earned - total_paid_out

        return {
            "total_earned": total_earned,
            "total_paid_out": total_paid_out,
            "balance": balance,
        }

    def create_payout(
            self,
            current_user: User,
            session_user: User,
            doctor_id: int,
            amount: float,
            note: str | None,
    ) -> Tuple[Optional[TipPayout], Optional[str]]:
        """
        Initiates a request to withdraw accumulated tips.

        Logic:
        1. Solvency Check: Ensures the doctor has sufficient funds accumulated.
        2. Policy Check: Determines if the payout requires Manager approval based on
           clinic configuration (`requires_cash_approval`).
        3. Execution: If approved immediately, money is moved. If pending, money
           movement is deferred.
        """
        clinic_id = current_user.clinic_id
        clinic = clinic_repo.get_by_id(clinic_id)

        doctor = user_repo.get_by_id_in_clinic(doctor_id, clinic_id)
        if not doctor:
            return None, "doctor not found in this clinic"

        balance = self.get_doctor_tip_balance(clinic_id, doctor_id)
        if amount > balance["balance"] + 0.0001:
            return None, "payout exceeds current tip balance"

        status = TipPayoutStatus.PAID.value

        if clinic.requires_cash_approval and current_user.requires_approval_for_actions:
            status = TipPayoutStatus.PENDING.value

        payout = tip_payout_repo.create_payout(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            amount=amount,
            created_by=current_user.user_id,
            session_user_id=session_user.user_id,
            note=note,
            status=status,
            approved_by=current_user.user_id if status == TipPayoutStatus.PAID.value else None
        )

        if status == TipPayoutStatus.PAID.value:
            self._auto_cash_for_tip_payout(
                clinic_id=clinic_id,
                user_id=current_user.user_id,
                session_user_id=session_user.user_id,
                payout=payout,
            )

        return payout, None

    def approve_payout(
            self,
            approver: User,
            payout_id: int
    ) -> Tuple[Optional[TipPayout], Optional[str]]:
        """
        Finalizes a PENDING tip payout.

        Uses database row locking to prevent race conditions (e.g., approving the
        same payout twice). Includes a secondary solvency check to ensure funds
        weren't withdrawn via another channel while this request was pending.
        """
        if not approver.can_approve_financials:
            return None, "permission denied"

        payout = tip_payout_repo.get_with_lock(payout_id, approver.clinic_id)

        if not payout:
            return None, "payout not found"

        if payout.status != TipPayoutStatus.PENDING.value:
            return None, "payout is not pending"

        # Re-verify balance to ensure solvency has not changed during the pending period
        balance = self.get_doctor_tip_balance(approver.clinic_id, payout.doctor_id)
        if float(payout.amount) > balance["balance"] + 0.0001:
            return None, "cannot approve: payout amount exceeds current remaining balance"

        payout.status = TipPayoutStatus.PAID.value
        payout.approved_by = approver.user_id

        self._auto_cash_for_tip_payout(
            clinic_id=approver.clinic_id,
            user_id=approver.user_id,
            session_user_id=payout.session_user_id,
            payout=payout,
        )

        return payout, None

    def reject_payout(
            self,
            rejector: User,
            payout_id: int
    ) -> Tuple[Optional[TipPayout], Optional[str]]:
        """
        Marks a tip payout request as REJECTED.

        The funds remain in the doctor's balance, and no physical cash is moved.
        The rejection is audit-logged using the rejector's ID.
        """
        if not rejector.can_approve_financials:
            return None, "permission denied"

        payout = tip_payout_repo.get_with_lock(payout_id, rejector.clinic_id)

        if not payout:
            return None, "payout not found"

        if payout.status != TipPayoutStatus.PENDING.value:
            return None, "payout is not pending"

        payout.status = TipPayoutStatus.REJECTED.value
        payout.approved_by = rejector.user_id

        return payout, None

    def list_payouts_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        """Retrieves payout history for a specific doctor."""
        return tip_payout_repo.list_payouts_for_doctor(clinic_id, doctor_id)


tip_service = TipService()
