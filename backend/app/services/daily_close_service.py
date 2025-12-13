from __future__ import annotations

from datetime import date as DateType, datetime
from typing import Optional, Tuple

from ..models import User, DailyClose
from ..data_layer.daily_close_repository import daily_close_repo
from ..data_layer.cashbox_repository import cashbox_repo
from ..services.cash_service import cash_service  # reuse adjust_cashbox_to_counted
from ..schemas.daily_close import CreateDailyCloseRequestSchema


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

        cashbox = cashbox_repo.get_in_clinic(payload.cashbox_id, clinic_id)
        if not cashbox:
            return None, "cashbox not found"

        day = payload.date or DateType.today()

        existing = daily_close_repo.get_for_cashbox_and_date(
            clinic_id=clinic_id,
            cashbox_id=cashbox.cashbox_id,
            day=day,
        )
        if existing:
            return None, "daily close already exists for this cashbox and date"

        expected_total = float(cashbox.current_amount or 0)
        counted_total = float(payload.counted_total)
        variance = round(counted_total - expected_total, 2)

        _adjust_result, adjust_error = cash_service.adjust_cashbox_to_counted(
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
            approved_by=None,
        )
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


daily_close_service = DailyCloseService()
