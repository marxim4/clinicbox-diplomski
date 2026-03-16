from __future__ import annotations

from datetime import datetime, date
from http import HTTPStatus

from flask import Blueprint, jsonify, g, request

from ..utils.wrappers import login_required
from ..schemas.pagination import PageMetaSchema
from ..schemas.audit import AuditLogResponseSchema
from ..services.audit_log_service import audit_log_service
from ..enums import AuditAction

bp = Blueprint("audit_logs", __name__, url_prefix="/api/audit-logs")


def _serialize(row):
    return AuditLogResponseSchema.model_validate(row).model_dump()


@bp.get("")
@login_required
def search_audit_logs():
    """
    Search Audit Logs
    ---
    tags:
      - Audit Logs
    security:
      - Bearer: []
    summary: Retrieve a paginated list of audit trail entries.
    parameters:
      - name: user_id
        in: query
        type: integer
        description: Filter by the ID of the user who performed the action.
      - name: action
        in: query
        type: string
        enum: [CREATE, UPDATE, DELETE, LOGIN, LOGOUT, APPROVE, REJECT]
        description: Filter by the type of action performed.
      - name: entity_name
        in: query
        type: string
        description: Filter by the target resource type (e.g., 'Payment', 'Patient').
      - name: entity_id
        in: query
        type: string
        description: Filter by the specific ID of the target resource.
      - name: date_from
        in: query
        type: string
        format: date
        description: Start date filter (YYYY-MM-DD).
      - name: date_to
        in: query
        type: string
        format: date
        description: End date filter (YYYY-MM-DD).
      - name: page
        in: query
        type: integer
        default: 1
        description: Page number for pagination.
      - name: page_size
        in: query
        type: integer
        default: 20
        description: Items per page.
    responses:
      200:
        description: A list of audit logs matching the criteria.
        schema:
          type: object
          properties:
            audit_logs:
              type: array
              items:
                type: object
                properties:
                  log_id:
                    type: integer
                  action:
                    type: string
                  entity_name:
                    type: string
                  entity_id:
                    type: string
                  user_id:
                    type: integer
                  created_at:
                    type: string
                    format: date-time
            meta:
              type: object
              properties:
                total_items:
                  type: integer
                total_pages:
                  type: integer
                current_page:
                  type: integer
                page_size:
                  type: integer
      400:
        description: Invalid parameters (e.g., bad date format).
    """
    current_user = g.current_user

    user_id = request.args.get("user_id", type=int)
    action_str = request.args.get("action", type=str)
    entity_name = request.args.get("entity_name", type=str)
    entity_id = request.args.get("entity_id", type=str)

    date_from_str = request.args.get("date_from", type=str)
    date_to_str = request.args.get("date_to", type=str)

    action = None
    if action_str:
        try:
            action = AuditAction[action_str.upper()]
        except KeyError:
            return jsonify(msg=f"invalid action '{action_str}'"), HTTPStatus.BAD_REQUEST

    def parse_dt(s):
        if not s:
            return None
        try:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day)
        except ValueError:
            return None

    date_from = parse_dt(date_from_str)
    date_to = parse_dt(date_to_str)
    if date_from_str and date_from is None:
        return jsonify(msg="invalid date_from, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST
    if date_to_str and date_to is None:
        return jsonify(msg="invalid date_to, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta, error = audit_log_service.search(
        current_user=current_user,
        user_id=user_id,
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    if meta is None:
        return jsonify(audit_logs=[_serialize(x) for x in items]), HTTPStatus.OK

    return (
        jsonify(
            audit_logs=[_serialize(x) for x in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )


@bp.get("/verify")
@login_required
def verify_audit_chain():
    """
    Verify Audit Chain Integrity
    ---
    tags:
      - Audit Logs
    security:
      - Bearer: []
    summary: Cryptographically verify the hash chain to detect database tampering.
    description: >
      Iterates through the audit log chain and recomputes hashes to ensure that
      no records have been altered or deleted directly in the database.
    parameters:
      - name: limit
        in: query
        type: integer
        default: 100
        description: Number of recent logs to verify (verifying all logs can be slow).
    responses:
      200:
        description: Verification result.
        schema:
          type: object
          properties:
            tampered:
              type: boolean
              description: True if a discrepancy was found.
            broken_chain_at_id:
              type: integer
              description: The ID of the log where the hash mismatch occurred (if any).
            details:
              type: string
              description: Textual explanation of the result.
      400:
        description: Error processing the request.
    """
    current_user = g.current_user
    limit = request.args.get("limit", type=int)

    result, error = audit_log_service.verify_chain(current_user, limit=limit)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    return jsonify(result), HTTPStatus.OK
