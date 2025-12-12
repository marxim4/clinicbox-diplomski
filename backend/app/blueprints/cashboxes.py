from __future__ import annotations

from datetime import datetime, date
from http import HTTPStatus

from flask import Blueprint, jsonify, g, request

from ..extensions import db
from ..utils.wrappers import login_required
from ..utils.validation import use_schema
from ..schemas.cash import (
    CreateCashboxRequestSchema,
    UpdateCashboxRequestSchema,
    CashboxResponseSchema,
    CashboxBalanceResponseSchema,
)
from ..services.cash_service import cash_service

bp = Blueprint("cashboxes", __name__, url_prefix="/api/cashboxes")


def _serialize_cashbox(cb):
    return CashboxResponseSchema.model_validate(cb).model_dump()


@bp.post("")
@login_required
@use_schema(CreateCashboxRequestSchema)
def create_cashbox(data: CreateCashboxRequestSchema):
    current_user = g.current_user

    cashbox, error = cash_service.create_cashbox(current_user, data)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="cashbox created", cashbox=_serialize_cashbox(cashbox)),
        HTTPStatus.CREATED,
    )


@bp.get("")
@login_required
def list_cashboxes():
    current_user = g.current_user
    include_inactive = request.args.get("include_inactive", type=str)

    include = False
    if include_inactive is not None and include_inactive.lower() in ("true", "1", "yes"):
        include = True

    items, error = cash_service.list_cashboxes_for_user(
        current_user,
        include_inactive=include,
    )
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    return (
        jsonify(cashboxes=[_serialize_cashbox(c) for c in items]),
        HTTPStatus.OK,
    )


@bp.patch("/<int:cashbox_id>")
@login_required
@use_schema(UpdateCashboxRequestSchema)
def update_cashbox(cashbox_id: int, data: UpdateCashboxRequestSchema):
    current_user = g.current_user

    cashbox, error = cash_service.update_cashbox(current_user, cashbox_id, data)
    if error == "cashbox not found":
        return jsonify(msg=error), HTTPStatus.NOT_FOUND
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="cashbox updated", cashbox=_serialize_cashbox(cashbox)),
        HTTPStatus.OK,
    )


@bp.get("/<int:cashbox_id>/balance")
@login_required
def get_cashbox_balance(cashbox_id: int):
    current_user = g.current_user

    def parse_dt(s: str | None):
        if not s:
            return None
        try:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day)
        except ValueError:
            return None

    date_from_str = request.args.get("date_from", type=str)
    date_to_str = request.args.get("date_to", type=str)

    date_from = parse_dt(date_from_str)
    date_to = parse_dt(date_to_str)

    if date_from_str and date_from is None:
        return jsonify(msg="invalid date_from, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST
    if date_to_str and date_to is None:
        return jsonify(msg="invalid date_to, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST

    stats, error = cash_service.get_cashbox_balance(
        current_user,
        cashbox_id=cashbox_id,
        date_from=date_from,
        date_to=date_to,
    )
    if error == "cashbox not found":
        return jsonify(msg=error), HTTPStatus.NOT_FOUND
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    return (
        jsonify(CashboxBalanceResponseSchema(**stats).model_dump()),
        HTTPStatus.OK,
    )
