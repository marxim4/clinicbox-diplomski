from __future__ import annotations

from datetime import date, datetime
from http import HTTPStatus

from flask import Blueprint, jsonify, g, request

from ..extensions import db
from ..utils.wrappers import login_required, require_pin
from ..utils.validation import use_schema
from ..schemas.daily_close import (
    CreateDailyCloseRequestSchema,
    DailyCloseResponseSchema,
)
from ..schemas.pagination import PageMetaSchema
from ..services.daily_close_service import daily_close_service

bp = Blueprint("daily_closes", __name__, url_prefix="/api/daily-closes")


def _serialize_close(close):
    return DailyCloseResponseSchema.model_validate(close).model_dump()


@bp.post("")
@login_required
@use_schema(CreateDailyCloseRequestSchema)
@require_pin
def create_daily_close(data: CreateDailyCloseRequestSchema):
    acting_user = g.current_user
    session_user = getattr(g, "session_user", acting_user)

    close, error = daily_close_service.create_daily_close(
        current_user=acting_user,
        session_user=session_user,
        payload=data
    )

    if error == "cashbox not found":
        return jsonify(msg=error), HTTPStatus.NOT_FOUND
    if error == "user has no clinic assigned":
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error == "daily close already exists for this cashbox and date":
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="daily close created", close=_serialize_close(close)),
        HTTPStatus.CREATED,
    )


@bp.post("/<int:close_id>/approve")
@login_required
def approve_daily_close(close_id: int):
    current_user = g.current_user

    close, error = daily_close_service.approve_daily_close(current_user, close_id)
    if error:
        status = HTTPStatus.BAD_REQUEST
        if "permission" in error: status = HTTPStatus.FORBIDDEN
        if "not found" in error: status = HTTPStatus.NOT_FOUND
        return jsonify(msg=error), status

    db.session.commit()
    return jsonify(msg="daily close approved", close=_serialize_close(close)), HTTPStatus.OK


@bp.get("/<int:close_id>")
@login_required
def get_daily_close(close_id: int):
    current_user = g.current_user

    close, error = daily_close_service.get_daily_close(current_user, close_id)
    if error == "user has no clinic assigned":
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error == "daily close not found":
        return jsonify(msg=error), HTTPStatus.NOT_FOUND

    return jsonify(close=_serialize_close(close)), HTTPStatus.OK


@bp.get("")
@login_required
def list_daily_closes():
    current_user = g.current_user

    cashbox_id = request.args.get("cashbox_id", type=int)
    date_from_str = request.args.get("date_from", type=str)
    date_to_str = request.args.get("date_to", type=str)

    def parse_date(s: str | None):
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None

    date_from = parse_date(date_from_str)
    date_to = parse_date(date_to_str)

    if date_from_str and date_from is None:
        return jsonify(msg="invalid date_from, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST
    if date_to_str and date_to is None:
        return jsonify(msg="invalid date_to, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta, error = daily_close_service.search_daily_closes(
        current_user=current_user,
        cashbox_id=cashbox_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if error == "user has no clinic assigned":
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    if meta is None:
        return (
            jsonify(closes=[_serialize_close(c) for c in items]),
            HTTPStatus.OK,
        )

    return (
        jsonify(
            closes=[_serialize_close(c) for c in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )
