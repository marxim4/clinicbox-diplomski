from __future__ import annotations

from datetime import date
from typing import Optional, Tuple, List

from sqlalchemy import select, func

from ..extensions import db
from ..models import DailyClose
from ..utils.pagination import validate_pagination, page_meta


class DailyCloseRepository:
    def get_by_id_in_clinic(self, close_id, clinic_id):
        stmt = select(DailyClose).where(
            DailyClose.close_id == close_id,
            DailyClose.clinic_id == clinic_id,
        )
        return db.session.scalar(stmt)

    def get_for_cashbox_and_date(self, clinic_id, cashbox_id, day):
        stmt = select(DailyClose).where(
            DailyClose.clinic_id == clinic_id,
            DailyClose.cashbox_id == cashbox_id,
            DailyClose.date == day,
        )
        return db.session.scalar(stmt)

    def create_close(
        self,
        *,
        clinic_id: int,
        cashbox_id: int,
        day: date,
        expected_total: float,
        counted_total: float,
        variance: float,
        note: str | None,
        closed_by: int,
        session_user_id: int,
        approved_by: int | None = None,
    ):
        close = DailyClose(
            clinic_id=clinic_id,
            cashbox_id=cashbox_id,
            date=day,
            expected_total=expected_total,
            counted_total=counted_total,
            variance=variance,
            note=note,
            closed_by=closed_by,
            session_user_id=session_user_id,
            approved_by=approved_by,
        )
        db.session.add(close)
        db.session.flush()
        return close

    def search(
        self,
        clinic_id: int,
        *,
        cashbox_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> Tuple[List[DailyClose], Optional[dict]]:
        base = select(DailyClose).where(DailyClose.clinic_id == clinic_id)

        if cashbox_id is not None:
            base = base.where(DailyClose.cashbox_id == cashbox_id)
        if date_from is not None:
            base = base.where(DailyClose.date >= date_from)
        if date_to is not None:
            base = base.where(DailyClose.date <= date_to)

        if page is None and page_size is None:
            stmt = base.order_by(
                DailyClose.date.desc(),
                DailyClose.close_id.desc(),
            )
            items = db.session.scalars(stmt).all()
            return items, None

        page, page_size = validate_pagination(page, page_size)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(
                DailyClose.date.desc(),
                DailyClose.close_id.desc(),
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()
        meta = page_meta(page, page_size, total_items)
        return items, meta


daily_close_repo = DailyCloseRepository()
