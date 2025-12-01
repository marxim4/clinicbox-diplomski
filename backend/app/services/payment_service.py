from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Tuple

from ..models import User, Patient, InstallmentPlan, Installment, Payment
from ..enums import (
    PaymentMethod,
    PlanStatus,
    CashTransactionType,
    TransactionStatus,
)
from ..data_layer.payment_repository import payment_repo
from ..data_layer.patient_repository import patient_repo  # currently unused but ok
from ..data_layer.installment_plan_repository import installment_plan_repo
from ..data_layer.user_repository import user_repo
from ..data_layer.tip_repository import tip_repo
from ..data_layer.cashbox_repository import cashbox_repo
from ..data_layer.cash_transaction_repository import cash_tx_repo
from ..schemas.payments import CreatePaymentRequestSchema


class PaymentService:
    def _get_plan_and_start_installment(
            self,
            clinic_id: int,
            plan_id: int | None,
            installment_id: int | None,
    ) -> Tuple[Optional[InstallmentPlan], Optional[Installment], Optional[str]]:
        plan: Optional[InstallmentPlan] = None
        start_installment: Optional[Installment] = None

        if installment_id is not None:
            inst = installment_plan_repo.get_installment_in_clinic(
                installment_id,
                clinic_id,
            )
            if not inst:
                return None, None, "installment not found"

            plan = inst.plan
            if not plan or plan.clinic_id != clinic_id:
                return None, None, "installment not found in this clinic"

            start_installment = inst

        else:
            if plan_id is None:
                return None, None, "plan_id or installment_id must be provided"

            plan = installment_plan_repo.get_plan_in_clinic(plan_id, clinic_id)
            if not plan or plan.clinic_id != clinic_id:
                return None, None, "plan not found in this clinic"

        return plan, start_installment, None

    def _total_plan_remaining(self, plan: InstallmentPlan):
        total = 0.0
        for inst in plan.installments:
            expected = float(inst.expected_amount)
            paid = float(getattr(inst, "amount_paid", 0) or 0)
            remaining = max(0.0, expected - paid)
            total += remaining
        return total

    def _recalc_plan_status(self, plan: InstallmentPlan):
        installments = list(plan.installments)
        if not installments:
            plan.status = PlanStatus.PLANNED
            return

        today = date.today()

        all_paid = True
        any_paid = False
        any_overdue_unpaid = False

        for inst in installments:
            expected = float(inst.expected_amount)
            paid = float(getattr(inst, "amount_paid", 0) or 0)

            if paid >= expected:
                any_paid = True
            else:
                all_paid = False
                if paid > 0:
                    any_paid = True
                if inst.due_date and inst.due_date < today:
                    any_overdue_unpaid = True

        if all_paid:
            plan.status = PlanStatus.PAID
        elif any_overdue_unpaid:
            plan.status = PlanStatus.OVERDUE
        elif any_paid:
            plan.status = PlanStatus.PARTIALLY_PAID
        else:
            plan.status = PlanStatus.PLANNED

    def _create_tip_from_payment(
            self,
            *,
            clinic_id: int,
            doctor_id: int,
            amount: float,
            patient_id: int | None,
            plan_id: int | None,
            created_by: int,
    ):
        if amount <= 0:
            return

        tip_repo.create_tip(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            amount=amount,
            patient_id=patient_id,
            plan_id=plan_id,
            created_by=created_by,
        )

    def _auto_cash_for_payment(
            self,
            clinic_id: int,
            user_id: int,
            payment: Payment,
            cashbox_id: int | None,
            total_cash: float,
    ) -> Optional[str]:
        if payment.method != PaymentMethod.CASH or total_cash <= 0:
            return None

        if cashbox_id is not None:
            cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)
            if not cashbox:
                return "cashbox not found in this clinic"
        else:
            cashbox = cashbox_repo.get_default_for_clinic(clinic_id)
            if not cashbox:
                # no cashbox configured – silently skip
                return None

        cash_tx_repo.create_transaction(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            type=CashTransactionType.IN,
            amount=total_cash,
            payment_id=payment.payment_id,
            category_id=None,
            tip_id=None,
            tip_payout_id=None,
            note=f"Payment #{payment.payment_id}",
            status=TransactionStatus.CONFIRMED,
            occurred_at=payment.created_at,
            created_by=user_id,
        )

        cashbox_repo.adjust_balance_for_transaction(
            cashbox,
            CashTransactionType.IN,
            total_cash,
        )

        return None

    def create_payment(
            self,
            *,
            current_user: User,
            payload: CreatePaymentRequestSchema,
    ):
        if not current_user.clinic_id:
            return None, "user has no clinic assigned"

        clinic_id = current_user.clinic_id

        base_amount = float(payload.amount) if payload.amount is not None else 0.0
        manual_tip = float(payload.tip_amount or 0.0)

        if base_amount <= 0 and manual_tip > 0:
            doctor_id: int
            patient_id: int | None = None
            plan_id: int | None = None
            method: PaymentMethod

            if payload.plan_id is not None:
                plan = installment_plan_repo.get_plan_in_clinic(payload.plan_id, clinic_id)
                if not plan or plan.clinic_id != clinic_id:
                    return None, "plan not found in this clinic"

                doctor_id = plan.doctor_id
                patient_id = plan.patient_id
                plan_id = plan.plan_id
                method = (
                        payload.method
                        or plan.default_payment_method
                        or PaymentMethod.CASH
                )
            elif payload.doctor_id is not None:
                # Pure tip to a doctor (no plan)
                doctor = user_repo.get_by_id_in_clinic(payload.doctor_id, clinic_id)
                if not doctor:
                    return None, "doctor not found in this clinic"
                doctor_id = doctor.user_id
                patient_id = None
                plan_id = None
                method = payload.method or PaymentMethod.CASH
            else:
                return None, "pure tip requires plan_id or doctor_id"

            payment = payment_repo.create_payment(
                clinic_id=clinic_id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                plan_id=plan_id,
                installment_id=None,
                amount=0.0,
                tip_amount=manual_tip,
                method=method,
                created_by=current_user.user_id,
            )

            self._create_tip_from_payment(
                clinic_id=clinic_id,
                doctor_id=doctor_id,
                amount=manual_tip,
                patient_id=patient_id,
                plan_id=plan_id,
                created_by=current_user.user_id,
            )

            err = self._auto_cash_for_payment(
                clinic_id=clinic_id,
                user_id=current_user.user_id,
                payment=payment,
                cashbox_id=payload.cashbox_id,
                total_cash=manual_tip,
            )
            if err:
                return None, err

            return payment, None

        # --- Case 1: debt payment (+ maybe tip) ---
        if base_amount <= 0:
            return None, "amount must be positive for debt payment"

        plan, start_installment, err = self._get_plan_and_start_installment(
            clinic_id=clinic_id,
            plan_id=payload.plan_id,
            installment_id=payload.installment_id,
        )
        if err:
            return None, err
        assert plan is not None

        method = (
                payload.method
                or plan.default_payment_method
                or PaymentMethod.CASH
        )

        patient = patient_repo.get_by_id_in_clinic(plan.patient_id, clinic_id) if plan.patient_id else None

        total_remaining_before = self._total_plan_remaining(plan)
        if total_remaining_before <= 0:
            return None, "plan is already fully paid"

        remaining_to_apply = min(base_amount, total_remaining_before)
        debt_applied = 0.0

        installments_sorted = sorted(
            list(plan.installments), key=lambda inst: inst.sequence
        )

        start_index = 0
        if start_installment is not None:
            for idx, inst in enumerate(installments_sorted):
                if inst.installment_id == start_installment.installment_id:
                    start_index = idx
                    break

        for idx in range(start_index, len(installments_sorted)):
            inst = installments_sorted[idx]
            expected = float(inst.expected_amount)
            paid = float(getattr(inst, "amount_paid", 0) or 0)
            remaining = max(0.0, expected - paid)

            if remaining <= 0 or remaining_to_apply <= 0:
                continue

            if remaining_to_apply >= remaining:
                # fully pay this installment
                inst.amount_paid = paid + remaining
                debt_applied += remaining
                remaining_to_apply -= remaining
            else:
                # partially pay this installment
                inst.amount_paid = paid + remaining_to_apply
                debt_applied += remaining_to_apply
                remaining_to_apply = 0.0
                break

        # Recalculate plan status
        self._recalc_plan_status(plan)

        # Overpay beyond current plan remaining becomes extra tip
        overpay_tip = max(0.0, base_amount - debt_applied)
        total_tip = manual_tip + overpay_tip

        payment = payment_repo.create_payment(
            clinic_id=clinic_id,
            patient_id=patient.patient_id if patient else None,
            doctor_id=plan.doctor_id,
            plan_id=plan.plan_id,
            installment_id=start_installment.installment_id
            if start_installment is not None
            else None,
            amount=debt_applied,
            tip_amount=total_tip,
            method=method,
            created_by=current_user.user_id,
        )

        # Create Tip for total_tip (if any)
        self._create_tip_from_payment(
            clinic_id=clinic_id,
            doctor_id=plan.doctor_id,
            amount=total_tip,
            patient_id=patient.patient_id if patient else None,
            plan_id=plan.plan_id,
            created_by=current_user.user_id,
        )

        total_cash = debt_applied + total_tip
        err = self._auto_cash_for_payment(
            clinic_id=clinic_id,
            user_id=current_user.user_id,
            payment=payment,
            cashbox_id=payload.cashbox_id,
            total_cash=total_cash,
        )
        if err:
            return None, err

        return payment, None

    def get_payment(
            self,
            *,
            current_user: User,
            payment_id: int,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        payment = payment_repo.get_by_id_in_clinic(payment_id, clinic_id)
        if not payment:
            return None, "payment not found"

        return payment, None

    def list_payments_for_plan(
            self,
            *,
            current_user: User,
            plan_id: int,
            page: int | None,
            page_size: int | None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, None, "user has no clinic assigned"

        items, meta = payment_repo.list_for_plan(
            clinic_id=clinic_id,
            plan_id=plan_id,
            page=page,
            page_size=page_size,
        )
        return items, meta, None

    def list_payments_for_installment(
            self,
            *,
            current_user: User,
            installment_id: int,
            page: int | None,
            page_size: int | None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, None, "user has no clinic assigned"

        items, meta = payment_repo.list_for_installment(
            clinic_id=clinic_id,
            installment_id=installment_id,
            page=page,
            page_size=page_size,
        )
        return items, meta, None

    def search_payments(
            self,
            *,
            current_user: User,
            doctor_id: int | None,
            patient_id: int | None,
            method: PaymentMethod | None,
            date_from: datetime | None,
            date_to: datetime | None,
            min_amount: float | None,
            max_amount: float | None,
            has_tip: bool | None,
            page: int | None = None,
            page_size: int | None = None,
    ):

        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, None, "user has no clinic assigned"

        # In the future: permission rules go here (owners vs doctors, etc.)

        items, meta = payment_repo.search(
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            method=method,
            date_from=date_from,
            date_to=date_to,
            min_amount=min_amount,
            max_amount=max_amount,
            has_tip=has_tip,
            page=page,
            page_size=page_size,
        )

        return items, meta, None


payment_service = PaymentService()
