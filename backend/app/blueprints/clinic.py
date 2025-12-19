from http import HTTPStatus
from flask import Blueprint, jsonify, g

from ..extensions import db
from ..utils.wrappers import login_required, owner_only
from ..utils.validation import use_schema
from ..schemas.clinic import UpdateClinicSettingsSchema, UpdateClinicDetailsSchema
from ..services.clinic_service import clinic_service

bp = Blueprint("clinic", __name__, url_prefix="/api/clinic")


def _serialize_clinic(clinic):
    return {
        "clinic_id": clinic.clinic_id,
        "name": clinic.name,
        "address": clinic.address,
        "currency": clinic.currency,
        "default_language": clinic.default_language,
        "clinic_type": clinic.clinic_type.name if clinic.clinic_type else None,

        "requires_payment_approval": clinic.requires_payment_approval,
        "requires_cash_approval": clinic.requires_cash_approval,
        "requires_close_approval": clinic.requires_close_approval,
        "use_shared_terminal_mode": clinic.use_shared_terminal_mode,
        "require_pin_for_actions": clinic.require_pin_for_actions,
        "require_pin_for_signoff": clinic.require_pin_for_signoff,
    }


@bp.get("")
@login_required
def get_my_clinic():
    current_user = g.current_user
    clinic, error = clinic_service.get_current_clinic(current_user)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    return jsonify(clinic=_serialize_clinic(clinic)), HTTPStatus.OK


@bp.patch("")
@login_required
@owner_only
@use_schema(UpdateClinicDetailsSchema)
def update_details(data: UpdateClinicDetailsSchema):
    current_user = g.current_user

    clinic, error = clinic_service.update_details(current_user, data)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return jsonify(msg="clinic details updated", clinic=_serialize_clinic(clinic)), HTTPStatus.OK


@bp.patch("/settings")
@login_required
@owner_only
@use_schema(UpdateClinicSettingsSchema)
def update_settings(data: UpdateClinicSettingsSchema):
    current_user = g.current_user

    clinic, error = clinic_service.update_settings(current_user, data)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return jsonify(msg="clinic settings updated", clinic=_serialize_clinic(clinic)), HTTPStatus.OK