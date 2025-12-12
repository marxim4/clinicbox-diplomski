from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, g

from ..extensions import db
from ..utils.wrappers import login_required, owner_only
from ..utils.validation import use_schema
from ..schemas.tips import (
    CreateTipRequestSchema,
    TipResponseSchema,
    DoctorTipBalanceResponseSchema,
    CreateTipPayoutRequestSchema,
    TipPayoutResponseSchema,
)
from ..services.tip_service import tip_service

bp = Blueprint("tips", __name__, url_prefix="/api/tips")


def _serialize_tip(tip):
    return TipResponseSchema(
        tip_id=tip.tip_id,
        clinic_id=tip.clinic_id,
        doctor_id=tip.doctor_id,
        patient_id=tip.patient_id,
        plan_id=tip.plan_id,
        amount=float(tip.amount),
        created_at=tip.created_at,
    ).model_dump()


def _serialize_payout(payout):
    return TipPayoutResponseSchema(
        payout_id=payout.payout_id,
        clinic_id=payout.clinic_id,
        doctor_id=payout.doctor_id,
        amount=float(payout.amount),
        note=payout.note,
        created_at=payout.created_at,
        created_by=payout.created_by,
    ).model_dump()



@bp.post("")
@login_required
@use_schema(CreateTipRequestSchema)
def create_tip(data: CreateTipRequestSchema):
    user = g.current_user

    tip, error = tip_service.create_tip(user, data)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return jsonify(msg="tip created", tip=_serialize_tip(tip)), HTTPStatus.CREATED



@bp.get("/doctor/<int:doctor_id>")
@login_required
def list_tips_for_doctor(doctor_id: int):
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    tips = tip_service.list_tips_for_doctor(clinic_id, doctor_id)
    return (
        jsonify(tips=[_serialize_tip(t) for t in tips]),
        HTTPStatus.OK,
    )


@bp.get("/patient/<int:patient_id>")
@login_required
def list_tips_for_patient(patient_id: int):
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    tips = tip_service.list_tips_for_patient(clinic_id, patient_id)
    return (
        jsonify(tips=[_serialize_tip(t) for t in tips]),
        HTTPStatus.OK,
    )


@bp.get("/plan/<int:plan_id>")
@login_required
def list_tips_for_plan(plan_id: int):
    tips = tip_service.list_tips_for_plan(plan_id)
    return (
        jsonify(tips=[_serialize_tip(t) for t in tips]),
        HTTPStatus.OK,
    )



@bp.get("/doctor/<int:doctor_id>/balance")
@login_required
def get_doctor_balance(doctor_id: int):
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    balance_data = tip_service.get_doctor_tip_balance(
        clinic_id=clinic_id,
        doctor_id=doctor_id,
    )

    return (
        jsonify(DoctorTipBalanceResponseSchema(**balance_data).model_dump()),
        HTTPStatus.OK,
    )



@bp.post("/doctor/<int:doctor_id>/payout")
@owner_only
@use_schema(CreateTipPayoutRequestSchema)
def create_tip_payout(doctor_id: int, data: CreateTipPayoutRequestSchema):
    owner = g.current_user

    payout, error = tip_service.create_payout(
        owner,
        doctor_id=doctor_id,
        amount=data.amount,
        note=data.note,
    )
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="tip payout created", payout=_serialize_payout(payout)),
        HTTPStatus.CREATED,
    )


@bp.get("/doctor/<int:doctor_id>/payouts")
@owner_only
def list_tip_payouts_for_doctor(doctor_id: int):
    owner = g.current_user
    clinic_id = owner.clinic_id

    payouts = tip_service.list_payouts_for_doctor(clinic_id, doctor_id)
    return (
        jsonify(payouts=[_serialize_payout(p) for p in payouts]),
        HTTPStatus.OK,
    )
