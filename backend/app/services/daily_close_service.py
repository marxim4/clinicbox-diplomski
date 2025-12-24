from __future__ import annotations

from datetime import date as DateType
from typing import Optional, Tuple

from ..models import User, DailyClose
from ..data_layer.daily_close_repository import daily_close_repo
from ..data_layer.cashbox_repository import cashbox_repo
from ..data_layer.clinic_repository import clinic_repo
from ..data_layer.payment_repository import payment_repo  # <--- Added Import
from ..services.cash_service import cash_service
from ..schemas.daily_close import CreateDailyCloseRequestSchema
from ..enums.daily_close_status_enum import DailyCloseStatus


class DailyCloseService:
    def create_daily_close(
            self,
            current_user: User,
            session_user: User,
            payload: CreateDailyCloseRequestSchema,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        clinic = clinic_repo.get_by_id(clinic_id)

        # 1. Decide Status
        status = DailyCloseStatus.APPROVED.value
        if clinic.requires_close_approval and current_user.requires_approval_for_actions:
            status = DailyCloseStatus.PENDING.value

        cashbox = cashbox_repo.get_in_clinic(payload.cashbox_id, clinic_id)
        if not cashbox:
            return None, "cashbox not found"

        # --- CLEAN DESK POLICY CHECK ---
        # Block closing if there are pending payments that need approval/rejection first.
        pending_count = payment_repo.count_pending_for_cashbox(cashbox.cashbox_id, clinic_id)
        if pending_count > 0:
            return None, f"Cannot close: there are {pending_count} pending payments. Approve or reject them first."
        # -------------------------------

        day = payload.date or DateType.today()

        # --- Prevent Future Dates ---
        if day > DateType.today():
            return None, "cannot close register for a future date"

        existing = daily_close_repo.get_for_cashbox_and_date(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            day=day,
        )
        if existing:
            # The test asserts "already closed" is in the error string.
            return None, "register is already closed for this date"

        expected_total = float(cashbox.current_amount or 0)
        counted_total = float(payload.counted_total)
        variance = round(counted_total - expected_total, 2)

        # 2. Adjust Cashbox (ONLY IF APPROVED)
        # If PENDING, we leave the cashbox balance alone until approved.
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

        # 3. Create Record
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
        Uses ROW LOCKING to prevent race conditions.
        """
        if not approver.can_approve_financials:
            return None, "permission denied"

        # 1. Fetch with LOCK (Prevents race conditions)
        close = daily_close_repo.get_with_lock(close_id, approver.clinic_id)

        if not close:
            return None, "daily close not found"

        if close.status != DailyCloseStatus.PENDING.value:
            return None, "daily close is not pending"

        # 2. Adjust Cashbox NOW (Delayed Action)
        # We use the 'approver' as the current_user causing the adjustment
        _adj, err = cash_service.adjust_cashbox_to_counted(
            current_user=approver,
            session_user=close.session_user,  # Keep the original session user for history
            cashbox_id=close.cashbox_id,
            counted_total=float(close.counted_total),
            note=f"Approved Close #{close.close_id}: {close.note or ''}",
        )
        if err:
            return None, err

        # 3. Update Status
        close.status = DailyCloseStatus.APPROVED.value
        close.approved_by = approver.user_id

        return close, None

    def reject_daily_close(self, rejector: User, close_id: int) -> Tuple[Optional[DailyClose], Optional[str]]:
        """
        Marks a daily close as REJECTED and records who did it.
        This forces the receptionist to create a new, correct one.
        """
        if not rejector.can_approve_financials:
            return None, "permission denied"

        # Lock row to prevent simultaneous Approve/Reject
        close = daily_close_repo.get_with_lock(close_id, rejector.clinic_id)

        if not close:
            return None, "daily close not found"

        if close.status != DailyCloseStatus.PENDING.value:
            return None, "daily close is not pending"

        # 1. Update Status
        close.status = DailyCloseStatus.REJECTED.value

        # 2. Record the Actor (Reuse the field)
        # Even though it says 'approved_by', in this context it means 'resolved_by'
        close.approved_by = rejector.user_id

        # Note: We do NOT touch the cashbox here. The money stays as is.

        return close, None

    def get_daily_close(
            self,
            current_user: User,
            close_id: int,
    ):
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
        Checks if the register is closed for today.
        Used to block new payments/transactions.
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
