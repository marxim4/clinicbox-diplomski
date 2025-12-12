from __future__ import annotations

from datetime import date
from http import HTTPStatus

from flask import Blueprint, jsonify, g, request

from ..extensions import db
from ..utils.wrappers import login_required
from ..utils.validation import use_schema
from ..schemas.installments import (
    CreateInstallmentPlanRequestSchema,
    UpdateInstallmentPlanRequestSchema,
    InstallmentPlanResponseSchema,
    UpcomingInstallmentResponseSchema,
)
from ..schemas.pagination import PageMetaSchema
from ..services.installment_service import installment_service
from ..enums import PlanStatus

bp = Blueprint("installment_plans", __name__, url_prefix="/api/installment-plans")


def _compute_plan_stats(plan):
    installments = list(plan.installments or [])

    total_expected = sum(float(i.expected_amount) for i in installments)
    total_paid = sum(float(i.amount_paid or 0) for i in installments)
    remaining = max(0.0, total_expected - total_paid)

    today = date.today()

    overdue_count = 0
    upcoming_unpaid = []

    for inst in installments:
        expected = float(inst.expected_amount)
        paid = float(inst.amount_paid or 0)

        if inst.due_date and inst.due_date < today and paid < expected:
            overdue_count += 1

        if inst.due_date and inst.due_date >= today and paid < expected:
            upcoming_unpaid.append(inst)

    upcoming_unpaid.sort(key=lambda i: (i.due_date, i.sequence))

    if upcoming_unpaid:
        first = upcoming_unpaid[0]
        next_due_date = first.due_date
        next_due_amount = float(first.expected_amount) - float(first.amount_paid or 0)
    else:
        next_due_date = None
        next_due_amount = None

    return {
        "total_expected": round(total_expected, 2),
        "total_paid": round(total_paid, 2),
        "remaining_amount": round(remaining, 2),
        "overdue_installments": overdue_count,
        "next_due_date": next_due_date,
        "next_due_amount": round(next_due_amount, 2) if next_due_amount is not None else None,
    }


def _serialize_plan(plan):
    base = InstallmentPlanResponseSchema.model_validate(plan).model_dump()
    stats = _compute_plan_stats(plan)
    base.update(stats)
    return base


@bp.post("")
@login_required
@use_schema(CreateInstallmentPlanRequestSchema)
def create_plan(data: CreateInstallmentPlanRequestSchema):
    current_user = g.current_user

    plan, error = installment_service.create_plan(current_user, data)
    if error:
        if error.startswith("patient not found"):
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        if error.startswith("doctor not found"):
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        if error == "user has no clinic assigned":
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()

    return (
        jsonify(msg="installment plan created", plan=_serialize_plan(plan)),
        HTTPStatus.CREATED,
    )


@bp.get("")
@login_required
def list_plans():
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    if not clinic_id:
        return jsonify(msg="user has no clinic assigned"), HTTPStatus.BAD_REQUEST

    patient_id = request.args.get("patient_id", type=int)
    doctor_id = request.args.get("doctor_id", type=int)
    status_param = request.args.get("status", type=str)

    status: PlanStatus | None = None
    if status_param:
        try:
            # must be one of: PLANNED, PARTIALLY_PAID, PAID, OVERDUE, CANCELLED
            status = PlanStatus[status_param.upper()]
        except KeyError:
            return jsonify(msg=f"invalid status '{status_param}'"), HTTPStatus.BAD_REQUEST

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    if page is None and page_size is None:
        plans = installment_service.list_plans_for_clinic(
            clinic_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=status,
        )
        return (
            jsonify(
                plans=[_serialize_plan(p) for p in plans],
            ),
            HTTPStatus.OK,
        )

    items, meta = installment_service.list_plans_for_clinic_paginated(
        clinic_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    return (
        jsonify(
            plans=[_serialize_plan(p) for p in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )


@bp.get("/<int:plan_id>")
@login_required
def get_plan(plan_id: int):
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    if not clinic_id:
        return jsonify(msg="user has no clinic assigned"), HTTPStatus.BAD_REQUEST

    plan = installment_service.get_plan_for_clinic(clinic_id, plan_id)
    if not plan:
        return jsonify(msg="plan not found"), HTTPStatus.NOT_FOUND

    return jsonify(plan=_serialize_plan(plan)), HTTPStatus.OK


@bp.patch("/<int:plan_id>")
@login_required
@use_schema(UpdateInstallmentPlanRequestSchema)
def update_plan(plan_id: int, data: UpdateInstallmentPlanRequestSchema):
    current_user = g.current_user

    updated_plan, error = installment_service.update_plan(current_user, plan_id, data)
    if error:
        if error == "plan not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        if error == "user has no clinic assigned":
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()

    return (
        jsonify(msg="installment plan updated", plan=_serialize_plan(updated_plan)),
        HTTPStatus.OK,
    )


@bp.get("/upcoming-installments")
@login_required
def list_upcoming_installments():
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    if not clinic_id:
        return jsonify(msg="user has no clinic assigned"), HTTPStatus.BAD_REQUEST

    doctor_id = request.args.get("doctor_id", type=int)
    patient_id = request.args.get("patient_id", type=int)
    from_date_str = request.args.get("from_date", type=str)

    if from_date_str:
        try:
            from_date = date.fromisoformat(from_date_str)
        except ValueError:
            return jsonify(msg="invalid from_date, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST
    else:
        from_date = None

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta = installment_service.list_upcoming_installments_for_clinic(
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        from_date=from_date,
        page=page,
        page_size=page_size,
    )

    return (
        jsonify(
            installments=[
                UpcomingInstallmentResponseSchema(**item).model_dump()
                for item in items
            ],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )


@bp.get("/overdue-installments")
@login_required
def list_overdue_installments():
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    if not clinic_id:
        return jsonify(msg="user has no clinic assigned"), HTTPStatus.BAD_REQUEST

    doctor_id = request.args.get("doctor_id", type=int)
    patient_id = request.args.get("patient_id", type=int)
    to_date_str = request.args.get("to_date", type=str)

    if to_date_str:
        try:
            to_date = date.fromisoformat(to_date_str)
        except ValueError:
            return jsonify(msg="invalid to_date, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST
    else:
        to_date = None  # service/repo will default to today

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta = installment_service.list_overdue_installments_for_clinic(
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )

    return (
        jsonify(
            installments=[
                UpcomingInstallmentResponseSchema(**item).model_dump()
                for item in items
            ],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )
