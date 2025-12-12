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
    current_user = g.current_user
    limit = request.args.get("limit", type=int)

    result, error = audit_log_service.verify_chain(current_user, limit=limit)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    return jsonify(result), HTTPStatus.OK
