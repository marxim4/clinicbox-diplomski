from __future__ import annotations

from datetime import datetime, date, timedelta
from sqlalchemy import select, func

from ..extensions import db
from ..models import AuditLog


class AuditLogRepository:
    def get_last_for_clinic(self, clinic_id):
        stmt = (
            select(AuditLog)
            .where(AuditLog.clinic_id == clinic_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
            .limit(1)
        )
        return db.session.scalar(stmt)

    def create_log(
            self,
            *,
            clinic_id,
            user_id,
            action,
            entity_name,
            entity_id,
            before_data,
            after_data,
            ip_address,
            device_info,
            prev_hash,
            curr_hash,
            created_at,
    ):
        row = AuditLog(
            clinic_id=clinic_id,
            user_id=user_id,
            action=action,
            entity_name=entity_name,
            entity_id=str(entity_id),
            before_data=before_data,
            after_data=after_data,
            ip_address=ip_address,
            device_info=device_info,
            prev_hash=prev_hash,
            curr_hash=curr_hash,
            created_at=created_at,
        )
        db.session.add(row)
        db.session.flush()
        return row

    def list_for_clinic_chronological(self, clinic_id, limit=None):
        stmt = (
            select(AuditLog)
            .where(AuditLog.clinic_id == clinic_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.audit_id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        return db.session.scalars(stmt).all()

    def search(
            self,
            clinic_id,
            *,
            user_id=None,
            action=None,
            entity_name=None,
            entity_id=None,
            date_from=None,
            date_to=None,
            page=None,
            page_size=None,
    ):
        from ..utils.pagination import validate_pagination, page_meta

        base = select(AuditLog).where(AuditLog.clinic_id == clinic_id)

        if user_id is not None:
            base = base.where(AuditLog.user_id == user_id)
        if action is not None:
            base = base.where(AuditLog.action == action)
        if entity_name is not None:
            base = base.where(AuditLog.entity_name == entity_name)
        if entity_id is not None:
            base = base.where(AuditLog.entity_id == str(entity_id))

        if date_from is not None:
            base = base.where(AuditLog.created_at >= date_from)

        if date_to is not None:
            if isinstance(date_to, datetime) and date_to.hour == 0:
                base = base.where(AuditLog.created_at < date_to + timedelta(days=1))
            else:
                base = base.where(AuditLog.created_at <= date_to)

        if page is None and page_size is None:
            stmt = base.order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
            return db.session.scalars(stmt).all(), None

        page, page_size = validate_pagination(page, page_size)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()
        return items, page_meta(page, page_size, total_items)


audit_log_repo = AuditLogRepository()
