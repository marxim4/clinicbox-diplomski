from __future__ import annotations

from typing import Optional, Tuple, List

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


class TipService:
    def _auto_cash_for_tip_payout(
            self,
            clinic_id: int,
            user_id: int,
            session_user_id: int,
            payout: TipPayout,
    ):
        """
        Creates the physical cash transaction (OUT) for a confirmed payout.
        """
        cashbox = cashbox_repo.get_default_for_clinic(clinic_id)
        if not cashbox:
            # no cashbox yet – skip creating cash tx
            return

        amount = float(payout.amount)

        # We use the status value directly or the enum value depending on your DB setup.
        # Assuming TransactionStatus.CONFIRMED.value is a string "CONFIRMED".
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

    # -------- lists --------

    def list_tips_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        return tip_repo.list_tips_for_doctor(clinic_id, doctor_id)

    def list_tips_for_patient(
            self,
            clinic_id: int,
            patient_id: int,
    ):
        return tip_repo.list_tips_for_patient(clinic_id, patient_id)

    def list_tips_for_plan(
            self,
            plan_id: int,
    ):
        return tip_repo.list_tips_for_plan(plan_id)

    # -------- balance --------

    def get_doctor_tip_balance(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        total_earned = tip_repo.sum_tips_for_doctor(clinic_id, doctor_id)
        total_paid_out = tip_payout_repo.sum_payouts_for_doctor(clinic_id, doctor_id)
        balance = total_earned - total_paid_out

        return {
            "total_earned": total_earned,
            "total_paid_out": total_paid_out,
            "balance": balance,
        }

    # -------- payouts --------

    def create_payout(
            self,
            current_user: User,
            session_user: User,
            doctor_id: int,
            amount: float,
            note: str | None,
    ) -> Tuple[Optional[TipPayout], Optional[str]]:
        clinic_id = current_user.clinic_id
        clinic = clinic_repo.get_by_id(clinic_id)

        doctor = user_repo.get_by_id_in_clinic(doctor_id, clinic_id)
        if not doctor:
            return None, "doctor not found in this clinic"

        # 1. Check Balance (Safety Check)
        balance = self.get_doctor_tip_balance(clinic_id, doctor_id)
        if amount > balance["balance"] + 0.0001:
            return None, "payout exceeds current tip balance"

        # 2. Determine Status (Approval Logic)
        status = TransactionStatus.CONFIRMED.value
        # If clinic requires approval AND user is "Junior" (needs approval)
        if clinic.requires_cash_approval and current_user.requires_approval_for_actions:
            status = TransactionStatus.PENDING.value

        # 3. Create Record
        payout = tip_payout_repo.create_payout(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            amount=amount,
            created_by=current_user.user_id,
            session_user_id=session_user.user_id,
            note=note,
            status=status,
            approved_by=current_user.user_id if status == TransactionStatus.CONFIRMED.value else None
        )

        # 4. Move Money (ONLY IF CONFIRMED)
        if status == TransactionStatus.CONFIRMED.value:
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
        """
        if not approver.can_approve_financials:
            return None, "permission denied"

        payout = tip_payout_repo.get_by_id_in_clinic(payout_id, approver.clinic_id)
        if not payout:
            return None, "payout not found"

        if payout.status != TransactionStatus.PENDING.value:
            return None, "payout is not pending"

        # 1. Re-Check Balance (Critical for race conditions)
        # Since pending payouts didn't deduct yet, ensure funds are still there.
        balance = self.get_doctor_tip_balance(approver.clinic_id, payout.doctor_id)
        if float(payout.amount) > balance["balance"] + 0.0001:
            return None, "cannot approve: payout amount exceeds current remaining balance"

        # 2. Update Status
        payout.status = TransactionStatus.CONFIRMED.value
        payout.approved_by = approver.user_id

        # 3. Move Money
        self._auto_cash_for_tip_payout(
            clinic_id=approver.clinic_id,
            user_id=approver.user_id,
            session_user_id=payout.session_user_id,
            payout=payout,
        )

        return payout, None

    def list_payouts_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        return tip_payout_repo.list_payouts_for_doctor(clinic_id, doctor_id)


tip_service = TipService()