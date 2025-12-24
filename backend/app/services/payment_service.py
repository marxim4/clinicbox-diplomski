from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Tuple

from ..services.daily_close_service import daily_close_service
from ..extensions import db

from ..models import User, InstallmentPlan, Installment, Payment
from ..enums import (
    PaymentMethod,
    PlanStatus,
    CashTransactionType,
    TransactionStatus,
)
from ..enums.payment_status_enum import PaymentStatus
from ..data_layer.payment_repository import payment_repo
from ..data_layer.patient_repository import patient_repo
from ..data_layer.installment_plan_repository import installment_plan_repo
from ..data_layer.user_repository import user_repo
from ..data_layer.tip_repository import tip_repo
from ..data_layer.cashbox_repository import cashbox_repo
from ..data_layer.cash_transaction_repository import cash_tx_repo
from ..data_layer.clinic_repository import clinic_repo
from ..schemas.payments import CreatePaymentRequestSchema


class PaymentService:
    """
    Service for managing the lifecycle of financial payments.

    This service orchestrates the complex logic of accepting funds, which involves:
    1. Debt Reduction: Applying payments to specific installments using a 'Waterfall' algorithm.
    2. Tip Distribution: Separating gratuities from principal debt.
    3. Cash Management: Interfacing with the Cashbox to record physical money movement.
    4. Concurrency Control: Preventing race conditions when multiple staff members access
       the same patient account simultaneously.
    5. Approval Workflows: Enforcing managerial oversight for high-value or sensitive transactions.
    """

    def _get_plan_and_start_installment(
            self,
            clinic_id: int,
            plan_id: int | None,
            installment_id: int | None,
    ) -> Tuple[Optional[InstallmentPlan], Optional[Installment], Optional[str]]:
        """
        Resolves the target InstallmentPlan and specific starting Installment based on input IDs.
        Ensures all entities belong to the correct clinic context.
        """
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

    def _total_plan_remaining(self, plan: InstallmentPlan) -> float:
        """Calculates the total outstanding debt for a plan."""
        total = 0.0
        for inst in plan.installments:
            expected = float(inst.expected_amount)
            paid = float(getattr(inst, "amount_paid", 0) or 0)
            remaining = max(0.0, expected - paid)
            total += remaining
        return total

    def _recalc_plan_status(self, plan: InstallmentPlan):
        """
        Updates the overall status of an InstallmentPlan based on its constituent installments.
        Transitions state between PLANNED, PARTIALLY_PAID, PAID, and OVERDUE.
        """
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
        """
        Records the gratuity portion of a payment.
        Note: The physical money movement is handled separately via _handle_cash_transaction.
        """
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

    def _handle_cash_transaction(
            self,
            clinic_id: int,
            user_id: int,
            session_user_id: int,
            payment: Payment,
            cashbox_id: int | None,
            total_cash: float,
    ) -> Optional[str]:
        """
        Executes the 'Double-Entry' bookkeeping logic.

        If the payment method is CASH, this creates a corresponding 'IN' transaction
        on the physical Cashbox and updates its current balance.
        """
        if payment.method != PaymentMethod.CASH or total_cash <= 0:
            return None

        if cashbox_id is not None:
            cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)
            if not cashbox:
                return "cashbox not found in this clinic"
        else:
            cashbox = cashbox_repo.get_default_for_clinic(clinic_id)
            if not cashbox:
                # No cashbox configured – fail silently or log warning (business decision)
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
            status=TransactionStatus.CONFIRMED.value,
            occurred_at=payment.created_at,
            created_by=user_id,
            session_user_id=session_user_id,
        )

        cashbox_repo.adjust_balance_for_transaction(
            cashbox,
            CashTransactionType.IN,
            total_cash,
        )

        return None

    def _apply_payment_to_installments(
            self,
            plan: InstallmentPlan,
            start_inst: Optional[Installment],
            amount_to_apply: float
    ):
        """
        Implements the 'Waterfall' Payment Algorithm.

        Money is applied to installments sequentially:
        1. Starts at the specific 'start_inst' (if provided) or the first installment.
        2. Fills the current installment until fully paid.
        3. Spills over any remaining amount to the next installment in the sequence.
        4. Continues until the payment amount is exhausted or the plan is fully paid.
        """
        remaining_to_apply = amount_to_apply

        installments_sorted = sorted(list(plan.installments), key=lambda x: x.sequence)

        start_index = 0
        if start_inst:
            for idx, i in enumerate(installments_sorted):
                if i.installment_id == start_inst.installment_id:
                    start_index = idx
                    break

        for idx in range(start_index, len(installments_sorted)):
            inst = installments_sorted[idx]
            expected = float(inst.expected_amount)
            paid = float(getattr(inst, "amount_paid", 0) or 0)
            rem = max(0.0, expected - paid)

            if rem <= 0 or remaining_to_apply <= 0:
                continue

            if remaining_to_apply >= rem:
                inst.amount_paid = paid + rem
                remaining_to_apply -= rem
            else:
                inst.amount_paid = paid + remaining_to_apply
                remaining_to_apply = 0.0
                break

        self._recalc_plan_status(plan)

    def create_payment(
            self,
            *,
            current_user: User,
            session_user: User,
            payload: CreatePaymentRequestSchema,
    ):
        """
        Initiates a payment transaction.

        This complex workflow handles two primary scenarios:
        1. Pure Tip: A gratuity with no underlying debt.
        2. Debt Payment: Paying off an installment plan (with optional overpayment as tip).

        Concurrency Safety:
        When paying off debt, this method employs Database Row Locking (`get_with_lock`)
        on the Patient record. This ensures that if two receptionists try to pay for the
        same patient simultaneously, one transaction waits for the other, preventing
        financial inconsistencies (e.g., double-paying a debt).

        Status Logic:
        Based on clinic settings (`requires_payment_approval`), the payment is created
        as either PAID (immediate effect) or PENDING (delayed effect pending manager approval).
        """
        if not current_user.clinic_id:
            return None, "user has no clinic assigned"

        # Guard: Prevent payments if the daily books are already closed
        if payload.cashbox_id:
            if daily_close_service.is_today_closed(payload.cashbox_id, current_user.clinic_id):
                return None, "Day is closed. No new payments allowed."

        clinic_id = current_user.clinic_id
        clinic = clinic_repo.get_by_id(clinic_id)

        # Determine Status (Pending vs Paid)
        status = PaymentStatus.PAID.value
        if clinic.requires_payment_approval and current_user.requires_approval_for_actions:
            status = PaymentStatus.PENDING.value

        base_amount = float(payload.amount) if payload.amount is not None else 0.0
        manual_tip = float(payload.tip_amount or 0.0)

        # Resolve Cashbox
        target_box_id = payload.cashbox_id
        if target_box_id is not None:
            box = cashbox_repo.get_in_clinic(target_box_id, clinic_id)
            if not box:
                return None, "cashbox not found in this clinic"
        else:
            box = cashbox_repo.get_default_for_clinic(clinic_id)
            if not box:
                return None, "no default cashbox configured for clinic"
            target_box_id = box.cashbox_id

        # --- Scenario A: Pure Tip (No Debt) ---
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
                target_cashbox_id=target_box_id,
                status=status,
                created_by=current_user.user_id,
                session_user_id=session_user.user_id,
            )

            # Apply effects only if immediately PAID
            if status == PaymentStatus.PAID.value:
                self._create_tip_from_payment(
                    clinic_id=clinic_id,
                    doctor_id=doctor_id,
                    amount=manual_tip,
                    patient_id=patient_id,
                    plan_id=plan_id,
                    created_by=current_user.user_id,
                )

                err = self._handle_cash_transaction(
                    clinic_id=clinic_id,
                    user_id=current_user.user_id,
                    session_user_id=session_user.user_id,
                    payment=payment,
                    cashbox_id=target_box_id,
                    total_cash=manual_tip,
                )
                if err:
                    return None, err

            return payment, None

        # --- Scenario B: Debt Payment ---
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

        # LOCKING: Prevent concurrent updates to the same patient's debt
        patient = None
        if plan.patient_id:
            patient = patient_repo.get_with_lock(plan.patient_id, clinic_id)
            if not patient:
                return None, "patient not found"

        total_remaining_before = self._total_plan_remaining(plan)

        remaining_to_apply = min(base_amount, total_remaining_before)
        debt_applied = remaining_to_apply

        # Calculate "Overpayment" as Tip
        overpay_tip = max(0.0, base_amount - debt_applied)
        total_tip = manual_tip + overpay_tip

        payment = payment_repo.create_payment(
            clinic_id=clinic_id,
            patient_id=patient.patient_id if patient else None,
            doctor_id=plan.doctor_id,
            plan_id=plan.plan_id,
            installment_id=start_installment.installment_id if start_installment else None,
            amount=debt_applied,
            tip_amount=total_tip,
            method=method,
            target_cashbox_id=target_box_id,
            status=status,
            created_by=current_user.user_id,
            session_user_id=session_user.user_id,
        )

        # Apply effects only if immediately PAID
        if status == PaymentStatus.PAID.value:
            # 1. Update Debt (Installments)
            self._apply_payment_to_installments(plan, start_installment, debt_applied)

            db.session.commit()

            # 2. Record Tip
            self._create_tip_from_payment(
                clinic_id=clinic_id,
                doctor_id=plan.doctor_id,
                amount=total_tip,
                patient_id=patient.patient_id if patient else None,
                plan_id=plan.plan_id,
                created_by=current_user.user_id,
            )

            # 3. Move Money
            total_cash = debt_applied + total_tip
            err = self._handle_cash_transaction(
                clinic_id=clinic_id,
                user_id=current_user.user_id,
                session_user_id=session_user.user_id,
                payment=payment,
                cashbox_id=target_box_id,
                total_cash=total_cash,
            )
            if err:
                return None, err

        return payment, None

    def approve_payment(self, approver: User, payment_id: int):
        """
        Finalizes a PENDING payment.

        This method executes the financial logic that was deferred during creation.
        It strictly requires a lock on the Payment record to ensure that a payment
        is not approved twice (preventing double-counting of revenue).
        """
        if not approver.can_approve_financials:
            return None, "permission denied"

        # Lock the row to ensure atomicity
        payment = payment_repo.get_with_lock(payment_id, approver.clinic_id)

        if not payment:
            return None, "payment not found"

        if payment.status != PaymentStatus.PENDING.value:
            return None, "payment is not pending"

        # 1. Update Status
        payment.status = PaymentStatus.PAID.value
        payment.approved_by = approver.user_id

        # 2. Apply Debt Logic (Deferred execution)
        if payment.plan_id and payment.amount > 0:
            plan = installment_plan_repo.get_plan_in_clinic(payment.plan_id, approver.clinic_id)
            start_inst = None
            if payment.installment_id:
                start_inst = installment_plan_repo.get_installment_in_clinic(payment.installment_id, approver.clinic_id)

            if plan:
                self._apply_payment_to_installments(plan, start_inst, float(payment.amount))

        # 3. Apply Tip Logic
        if payment.tip_amount > 0:
            self._create_tip_from_payment(
                clinic_id=payment.clinic_id,
                doctor_id=payment.doctor_id,
                amount=float(payment.tip_amount),
                patient_id=payment.patient_id,
                plan_id=payment.plan_id,
                created_by=payment.created_by,
            )

        # 4. Move Money (Deferred execution)
        total_cash = float(payment.amount) + float(payment.tip_amount)

        err = self._handle_cash_transaction(
            clinic_id=payment.clinic_id,
            user_id=approver.user_id,
            session_user_id=payment.session_user_id,
            payment=payment,
            cashbox_id=payment.target_cashbox_id,
            total_cash=total_cash,
        )
        if err:
            return None, err

        return payment, None

    def reject_payment(self, rejector: User, payment_id: int):
        """
        Marks a pending payment as REJECTED.

        The record is preserved for audit purposes, but no financial effects
        (debt reduction or cash movement) are applied.
        """
        if not rejector.can_approve_financials:
            return None, "permission denied"

        payment = payment_repo.get_with_lock(payment_id, rejector.clinic_id)

        if not payment:
            return None, "payment not found"

        if payment.status != PaymentStatus.PENDING.value:
            return None, "payment is not pending"

        # Update Status
        payment.status = PaymentStatus.REJECTED.value

        # Record the Actor
        payment.approved_by = rejector.user_id

        return payment, None

    def get_payment(
            self,
            *,
            current_user: User,
            payment_id: int,
    ):
        """Retrieves a single payment record within the user's clinic scope."""
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
        """Retrieves payment history for a specific installment plan."""
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
        """Retrieves payment history for a specific installment."""
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
        """
        Advanced search for payments.

        Supports filtering by date range, amount range, payment method,
        and associated entities (Doctor, Patient).
        """
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, None, "user has no clinic assigned"

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
