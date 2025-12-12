from __future__ import annotations

import hashlib
import json
from datetime import datetime

from ..data_layer.audit_log_repository import audit_log_repo


class AuditLogService:
    def _stable_json(self, obj):
        if obj is None:
            return ""
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _compute_hash(
        self,
        *,
        prev_hash,
        clinic_id,
        user_id,
        action,
        entity_name,
        entity_id,
        before_data,
        after_data,
        ip_address,
        device_info,
        created_at_iso,
    ):
        payload = "|".join(
            [
                prev_hash or "",
                str(clinic_id),
                str(user_id or ""),
                str(action),
                entity_name or "",
                str(entity_id),
                self._stable_json(before_data),
                self._stable_json(after_data),
                ip_address or "",
                device_info or "",
                created_at_iso,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log(
        self,
        *,
        current_user,
        action,
        entity_name,
        entity_id,
        before_data=None,
        after_data=None,
        ip_address=None,
        device_info=None,
    ):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        last = audit_log_repo.get_last_for_clinic(clinic_id)
        prev_hash = last.curr_hash if last else None

        created_at = datetime.utcnow()
        created_at_iso = created_at.isoformat()

        curr_hash = self._compute_hash(
            prev_hash=prev_hash,
            clinic_id=clinic_id,
            user_id=current_user.user_id,
            action=action,
            entity_name=entity_name,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            ip_address=ip_address,
            device_info=device_info,
            created_at_iso=created_at_iso,
        )

        row = audit_log_repo.create_log(
            clinic_id=clinic_id,
            user_id=current_user.user_id,
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

        return row, None

    def verify_chain(self, current_user, limit=None):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return None, "user has no clinic assigned"

        rows = audit_log_repo.list_for_clinic_chronological(clinic_id, limit=limit)

        expected_prev = None
        checked = 0

        for row in rows:
            created_at_iso = row.created_at.isoformat()

            recomputed = self._compute_hash(
                prev_hash=expected_prev,
                clinic_id=row.clinic_id,
                user_id=row.user_id,
                action=row.action,
                entity_name=row.entity_name,
                entity_id=row.entity_id,
                before_data=row.before_data,
                after_data=row.after_data,
                ip_address=row.ip_address,
                device_info=row.device_info,
                created_at_iso=created_at_iso,
            )

            # Optional extra integrity check:
            # row.prev_hash should match the expected_prev we are chaining from.
            if (row.prev_hash or None) != (expected_prev or None):
                return {
                    "ok": False,
                    "checked": checked,
                    "failed_audit_id": row.audit_id,
                    "reason": "prev_hash_mismatch",
                    "expected_prev_hash": expected_prev,
                    "row_prev_hash": row.prev_hash,
                }, None

            if (row.curr_hash or "") != recomputed:
                return {
                    "ok": False,
                    "checked": checked,
                    "failed_audit_id": row.audit_id,
                    "reason": "curr_hash_mismatch",
                    "expected_curr_hash": recomputed,
                    "row_curr_hash": row.curr_hash,
                }, None

            expected_prev = row.curr_hash
            checked += 1

        return {
            "ok": True,
            "checked": checked,
            "limit": limit,
            "last_audit_id": rows[-1].audit_id if rows else None,
        }, None


audit_log_service = AuditLogService()
