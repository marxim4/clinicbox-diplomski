from __future__ import annotations

from datetime import date as DateType
from typing import Optional, Tuple

from ..models import User, DailyClose
from ..data_layer.daily_close_repository import daily_close_repo
from ..data_layer.cashbox_repository import cashbox_repo
from ..data_layer.clinic_repository import clinic_repo
from ..data_layer.payment_repository import payment_repo
from ..services.cash_service import cash_service
from ..schemas.daily_close import CreateDailyCloseRequestSchema
from ..enums.daily_close_status_enum import DailyCloseStatus


class DailyCloseService:
    """
    Service for managing the End-of-Day (EOD) financial reconciliation.

    This service handles the 'Daily Close' workflow, which involves:
    1. Reconciling physical cash counts with system expectations.
    2. Calculating and recording variance (Overage/Shortage).
    3. Enforcing the 'Clean Desk Policy' (blocking closure if payments are pending).
    4. Managing the approval workflow for closes with significant discrepancies.
    """

    def create_daily_close(
            self,
            current_user: User,
            session_user: User,
            payload: CreateDailyCloseRequestSchema,
    ):
        """
        Initiates a Daily Close for a specific cashbox.

        Logic:
        1. Enforces 'Clean Desk Policy': The register cannot be closed if there are
           pending payments waiting for approval.
        2. Validates the date (cannot close for the future or duplicate closes).
        3. Calculates variance (Counted - Expected).
        4. Determines status based on user role and clinic settings.
        5. If immediately APPROVED, automatically adjusts the cashbox balance to match
           the physical count via an adjustment transaction.
        """
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        clinic = clinic_repo.get_by_id(clinic_id)

        # Determine if approval is required
        status = DailyCloseStatus.APPROVED.value
        if clinic.requires_close_approval and current_user.requires_approval_for_actions:
            status = DailyCloseStatus.PENDING.value

        cashbox = cashbox_repo.get_in_clinic(payload.cashbox_id, clinic_id)
        if not cashbox:
            return None, "cashbox not found"

        # Check for pending payments (Clean Desk Policy)
        pending_count = payment_repo.count_pending_for_cashbox(cashbox.cashbox_id, clinic_id)
        if pending_count > 0:
            return None, f"Cannot close: there are {pending_count} pending payments. Approve or reject them first."

        day = payload.date or DateType.today()

        if day > DateType.today():
            return None, "cannot close register for a future date"

        existing = daily_close_repo.get_for_cashbox_and_date(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            day=day,
        )
        if existing:
            return None, "register is already closed for this date"

        expected_total = float(cashbox.current_amount or 0)
        counted_total = float(payload.counted_total)
        variance = round(counted_total - expected_total, 2)

        # If Approved immediately, adjust the cashbox now.
        # If Pending, the cashbox balance remains 'incorrect' until the Manager approves.
        if status == DailyCloseStatus.APPROVED.value:
            _adj, adjust_error = cash_service.adjust_cashbox_to_counted(
                current_user=current_user,
                session_user=session_user,
                cashbox_id=cashbox.cashbox_id,
                counted_total=counted_total,
                note=payload.note,
            )
            if adjust_error:
                return None, adjust_error

        close = daily_close_repo.create_close(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            day=day,
            expected_total=expected_total,
            counted_total=counted_total,
            variance=variance,
            note=payload.note,
            closed_by=current_user.user_id,
            session_user_id=session_user.user_id,
            approved_by=current_user.user_id if status == DailyCloseStatus.APPROVED.value else None,
            status=status
        )
        return close, None

    def approve_daily_close(self, approver: User, close_id: int) -> Tuple[Optional[DailyClose], Optional[str]]:
        """
        Finalizes a PENDING daily close.

        This action is delayed until a Manager reviews the discrepancy.
        Once approved, the system creates the necessary adjustment transaction
        to synchronize the cashbox balance with the reported physical count.
        """
        if not approver.can_approve_financials:
            return None, "permission denied"

        # Lock to prevent race conditions during approval
        close = daily_close_repo.get_with_lock(close_id, approver.clinic_id)

        if not close:
            return None, "daily close not found"

        if close.status != DailyCloseStatus.PENDING.value:
            return None, "daily close is not pending"

        # Apply the delayed balance adjustment
        _adj, err = cash_service.adjust_cashbox_to_counted(
            current_user=approver,
            session_user=close.session_user,  # Preserve original session context
            cashbox_id=close.cashbox_id,
            counted_total=float(close.counted_total),
            note=f"Approved Close #{close.close_id}: {close.note or ''}",
        )
        if err:
            return None, err

        close.status = DailyCloseStatus.APPROVED.value
        close.approved_by = approver.user_id

        return close, None

    def reject_daily_close(self, rejector: User, close_id: int) -> Tuple[Optional[DailyClose], Optional[str]]:
        """
        Marks a daily close as REJECTED.

        This forces the staff to recount and submit a new Daily Close request.
        The rejected record is kept for audit purposes.
        """
        if not rejector.can_approve_financials:
            return None, "permission denied"

        close = daily_close_repo.get_with_lock(close_id, rejector.clinic_id)

        if not close:
            return None, "daily close not found"

        if close.status != DailyCloseStatus.PENDING.value:
            return None, "daily close is not pending"

        close.status = DailyCloseStatus.REJECTED.value
        close.approved_by = rejector.user_id

        return close, None

    def get_daily_close(
            self,
            current_user: User,
            close_id: int,
    ):
        """Retrieves a specific daily close record."""
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        close = daily_close_repo.get_by_id_in_clinic(close_id, clinic_id)
        if not close:
            return None, "daily close not found"

        return close, None

    def search_daily_closes(
            self,
            current_user: User,
            *,
            cashbox_id: int | None,
            date_from,
            date_to,
            page: int | None,
            page_size: int | None,
    ):
        """Searches daily close history with filters."""
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, None, "user has no clinic assigned"

        items, meta = daily_close_repo.search(
            clinic_id=clinic_id,
            cashbox_id=cashbox_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
        return items, meta, None

    def is_today_closed(self, cashbox_id: int, clinic_id: int) -> bool:
        """
        Checks if the register is closed for the current day.

        Used as a guard clause in other services (e.g., PaymentService) to block
        financial activity after the books have been closed.
        """
        cashbox = cashbox_repo.get_in_clinic(cashbox_id, clinic_id)

        if not cashbox:
            return False

        existing = daily_close_repo.get_for_cashbox_and_date(
            clinic_id=clinic_id,
            cashbox_id=cashbox_id,
            day=DateType.today(),
        )

        if existing and existing.status != DailyCloseStatus.REJECTED.value:
            return True

        return False


daily_close_service = DailyCloseService()
