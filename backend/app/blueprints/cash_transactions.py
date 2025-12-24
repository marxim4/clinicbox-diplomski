from __future__ import annotations

from datetime import datetime, date
from http import HTTPStatus

from flask import Blueprint, jsonify, g, request

from ..extensions import db
from ..utils.wrappers import login_required, require_pin
from ..utils.validation import use_schema
from ..schemas.cash import (
    CreateCashTransactionRequestSchema,
    CashTransactionResponseSchema,
)
from ..schemas.pagination import PageMetaSchema
from ..services.cash_service import cash_service
from ..enums import CashTransactionType, TransactionStatus

bp = Blueprint("cash_transactions", __name__, url_prefix="/api/cash-transactions")


def _serialize_tx(tx):
    return CashTransactionResponseSchema.model_validate(tx).model_dump()


@bp.post("")
@login_required
@use_schema(CreateCashTransactionRequestSchema)
@require_pin
def create_cash_transaction(data: CreateCashTransactionRequestSchema):
    acting_user = g.current_user
    session_user = getattr(g, "session_user", acting_user)

    tx, error = cash_service.create_transaction(
        current_user=acting_user,
        session_user=session_user,
        payload=data
    )

    if error:
        if "not found" in error:
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()

    return (
        jsonify(msg="cash transaction created", transaction=_serialize_tx(tx)),
        HTTPStatus.CREATED,
    )


@bp.post("/<int:tx_id>/approve")
@login_required
def approve_transaction(tx_id: int):
    current_user = g.current_user

    tx, error = cash_service.approve_transaction(current_user, tx_id)

    if error:
        status = HTTPStatus.BAD_REQUEST
        if "permission" in error:
            status = HTTPStatus.FORBIDDEN
        elif "not found" in error:
            status = HTTPStatus.NOT_FOUND
        elif "not pending" in error:
            status = HTTPStatus.CONFLICT

        return jsonify(msg=error), status

    db.session.commit()
    return jsonify(msg="transaction approved", transaction=_serialize_tx(tx)), HTTPStatus.OK


@bp.post("/<int:tx_id>/reject")
@login_required
def reject_transaction(tx_id: int):
    tx, error = cash_service.reject_transaction(g.current_user, tx_id)

    if error:
        status = HTTPStatus.BAD_REQUEST
        if "permission" in error:
            status = HTTPStatus.FORBIDDEN
        elif "not found" in error:
            status = HTTPStatus.NOT_FOUND
        return jsonify(msg=error), status

    db.session.commit()

    return jsonify(
        msg="transaction rejected",
        transaction=_serialize_tx(tx)
    ), HTTPStatus.OK


@bp.get("")
@login_required
def search_transactions():
    current_user = g.current_user

    cashbox_id = request.args.get("cashbox_id", type=int)
    type_str = request.args.get("type", type=str)
    status_str = request.args.get("status", type=str)
    category_id = request.args.get("category_id", type=int)
    payment_id = request.args.get("payment_id", type=int)

    date_from_str = request.args.get("date_from", type=str)
    date_to_str = request.args.get("date_to", type=str)
    min_amount = request.args.get("min_amount", type=float)
    max_amount = request.args.get("max_amount", type=float)

    tx_type = None
    if type_str:
        try:
            tx_type = CashTransactionType[type_str.upper()]
        except KeyError:
            return jsonify(msg=f"invalid type '{type_str}'"), HTTPStatus.BAD_REQUEST

    status = None
    if status_str:
        try:
            st_enum = TransactionStatus[status_str.upper()]
            status = st_enum.value
        except KeyError:
            return jsonify(msg=f"invalid status '{status_str}'"), HTTPStatus.BAD_REQUEST

    def parse_dt(s: str | None):
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

    items, meta, error = cash_service.search_transactions(
        current_user=current_user,
        cashbox_id=cashbox_id,
        type=tx_type,
        status=status,
        category_id=category_id,
        payment_id=payment_id,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
        page=page,
        page_size=page_size,
    )
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    if meta is None:
        return (
            jsonify(transactions=[_serialize_tx(t) for t in items]),
            HTTPStatus.OK,
        )

    return (
        jsonify(
            transactions=[_serialize_tx(t) for t in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )
