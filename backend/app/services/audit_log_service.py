from __future__ import annotations

import hashlib
import json
from datetime import datetime

from ..data_layer.audit_log_repository import audit_log_repo


class AuditLogService:
    """
    Service responsible for creating and verifying immutable audit logs.

    This service implements a tamper-evident logging system using cryptographic chaining.
    Each log entry contains a SHA-256 hash that is computed based on:
      1. The entry's own data (action, entity, changes).
      2. The hash of the strictly previous entry (`prev_hash`).

    This chaining mechanism ensures that any modification, deletion, or insertion
    of a log entry breaks the chain, allowing the system to detect database tampering.
    """

    def _stable_json(self, obj) -> str:
        """
        Serializes an object to a canonical JSON string for hashing.

        Ensures keys are sorted and whitespace is stripped so that the same dictionary
        always produces the exact same string representation, which is critical for
        consistent cryptographic hashing.
        """
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
    ) -> str:
        """
        Computes the SHA-256 hash for a specific log entry.

        The payload is constructed by joining all critical fields with a pipe '|' delimiter.
        This includes the `prev_hash`, binding this entry mathematically to the previous one.
        """
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
        """
        Creates a new audit log entry linked to the previous entry.

        Retrieves the most recent log for the clinic to establish the `prev_hash`.
        If this is the first log for the clinic, `prev_hash` will be None.

        Args:
            current_user: The user performing the action.
            action (AuditAction): The type of action (CREATE, UPDATE, DELETE).
            entity_name (str): The name of the resource being modified (e.g., 'Payment').
            entity_id (int|str): The ID of the resource.
            before_data (dict, optional): State before change (for updates/deletes).
            after_data (dict, optional): State after change (for creates/updates).
            ip_address (str, optional): IP address of the client.
            device_info (str, optional): User agent or device string.

        Returns:
            tuple: (Created Log Object, Error String)
        """
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
        """
        Verifies the cryptographic integrity of the audit log chain for a clinic.

        Iterates through logs chronologically and re-computes the hash for each entry
        using its stored data and the hash of the previous row. If the re-computed
        hash does not match the stored `curr_hash`, or if the `prev_hash` pointer
        is broken, the chain is considered compromised.

        Args:
            current_user: The user requesting the verification (must belong to the clinic).
            limit (int, optional): Number of recent logs to verify.

        Returns:
            tuple: (Result Dictionary, Error String)
        """
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

            # Integrity Check 1: Chain Continuity
            if (row.prev_hash or None) != (expected_prev or None):
                return {
                    "ok": False,
                    "checked": checked,
                    "failed_audit_id": row.audit_id,
                    "reason": "prev_hash_mismatch",
                    "expected_prev_hash": expected_prev,
                    "row_prev_hash": row.prev_hash,
                }, None

            # Integrity Check 2: Data Fidelity
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
