from __future__ import annotations

from http import HTTPStatus
from datetime import datetime, date

from flask import Blueprint, jsonify, g, request

from ..extensions import db
from ..utils.wrappers import login_required
from ..utils.validation import use_schema
from ..schemas.payments import (
    CreatePaymentRequestSchema,
    PaymentResponseSchema,
)
from ..schemas.pagination import PageMetaSchema
from ..services.payment_service import payment_service
from ..enums import PaymentMethod   # <-- make sure this is imported

bp = Blueprint("payments", __name__, url_prefix="/api/payments")


def _serialize_payment(payment):
    return PaymentResponseSchema.model_validate(payment).model_dump()


@bp.post("")
@login_required
@use_schema(CreatePaymentRequestSchema)
def create_payment(data: CreatePaymentRequestSchema):
    current_user = g.current_user

    payment, error = payment_service.create_payment(
        current_user=current_user,
        payload=data,
    )
    if error:
        status = (
            HTTPStatus.BAD_REQUEST
            if "not found" in error
            or "already fully paid" in error
            or "amount must be" in error
            else HTTPStatus.BAD_REQUEST
        )
        return jsonify(msg=error), status

    db.session.commit()

    return (
        jsonify(
            msg="payment created",
            payment=_serialize_payment(payment),
        ),
        HTTPStatus.CREATED,
    )


@bp.get("/<int:payment_id>")
@login_required
def get_payment(payment_id: int):
    current_user = g.current_user

    payment, error = payment_service.get_payment(
        current_user=current_user,
        payment_id=payment_id,
    )
    if error:
        if error == "user has no clinic assigned":
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        if error == "payment not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    return jsonify(payment=_serialize_payment(payment)), HTTPStatus.OK


@bp.get("/by-plan/<int:plan_id>")
@login_required
def list_payments_for_plan(plan_id: int):
    current_user = g.current_user

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta, error = payment_service.list_payments_for_plan(
        current_user=current_user,
        plan_id=plan_id,
        page=page,
        page_size=page_size,
    )
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    if meta is None:
        return (
            jsonify(
                payments=[_serialize_payment(p) for p in items],
            ),
            HTTPStatus.OK,
        )

    return (
        jsonify(
            payments=[_serialize_payment(p) for p in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )


@bp.get("/by-installment/<int:installment_id>")
@login_required
def list_payments_for_installment(installment_id: int):
    current_user = g.current_user

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta, error = payment_service.list_payments_for_installment(
        current_user=current_user,
        installment_id=installment_id,
        page=page,
        page_size=page_size,
    )
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    if meta is None:
        return (
            jsonify(
                payments=[_serialize_payment(p) for p in items],
            ),
            HTTPStatus.OK,
        )

    return (
        jsonify(
            payments=[_serialize_payment(p) for p in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )


@bp.get("/search")
@login_required
def search_payments():
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    if not clinic_id:
        return jsonify(msg="user has no clinic assigned"), HTTPStatus.BAD_REQUEST

    doctor_id = request.args.get("doctor_id", type=int)
    patient_id = request.args.get("patient_id", type=int)
    method_str = request.args.get("method", type=str)
    date_from_str = request.args.get("date_from", type=str)
    date_to_str = request.args.get("date_to", type=str)
    min_amount = request.args.get("min_amount", type=float)
    max_amount = request.args.get("max_amount", type=float)
    has_tip_str = request.args.get("has_tip", type=str)

    method = None
    if method_str:
        try:
            method = PaymentMethod[method_str.upper()]
        except KeyError:
            return jsonify(msg=f"invalid method '{method_str}'"), HTTPStatus.BAD_REQUEST

    def parse_date(s: str | None) -> datetime | None:
        if not s:
            return None
        try:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day)
        except ValueError:
            return None

    date_from = parse_date(date_from_str)
    date_to = parse_date(date_to_str)
    if date_from_str and date_from is None:
        return jsonify(msg="invalid date_from, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST
    if date_to_str and date_to is None:
        return jsonify(msg="invalid date_to, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST

    has_tip = None
    if has_tip_str is not None:
        if has_tip_str.lower() in ("true", "1", "yes"):
            has_tip = True
        elif has_tip_str.lower() in ("false", "0", "no"):
            has_tip = False
        else:
            return jsonify(msg="invalid has_tip, expected true/false"), HTTPStatus.BAD_REQUEST

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta, error = payment_service.search_payments(
        current_user=current_user,
        doctor_id=doctor_id,
        patient_id=patient_id,
        method=method,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
        has_tip=has_tip,
        page=page,
        page_size=page_size,
    )

    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    if meta is None:
        return (
            jsonify(payments=[_serialize_payment(p) for p in items]),
            HTTPStatus.OK,
        )

    return (
        jsonify(
            payments=[_serialize_payment(p) for p in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )
