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
        "timezone": clinic.timezone,
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
    """
    Get My Clinic
    ---
    tags:
      - Clinic Management
    security:
      - Bearer: []
    summary: Retrieve current clinic details and configuration settings.
    responses:
      200:
        description: Clinic details
        schema:
          type: object
          properties:
            clinic:
              type: object
              properties:
                name:
                  type: string
                currency:
                  type: string
                requires_payment_approval:
                  type: boolean
                requires_cash_approval:
                  type: boolean
    """
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
    """
    Update Clinic Profile
    ---
    tags:
      - Clinic Management
    security:
      - Bearer: []
    summary: Update basic clinic information (Name, Address, Language).
    description: Only available to the Clinic Owner.
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            address:
              type: string
            default_language:
              type: string
    responses:
      200:
        description: Updated successfully
      403:
        description: Permission denied (Not Owner)
    """
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
    """
    Update Clinic Settings
    ---
    tags:
      - Clinic Management
    security:
      - Bearer: []
    summary: Configure critical business rules and security policies.
    description: >
      Enable/disable approval workflows for payments, cash movements, and daily closes.
      Toggle Shared Terminal Mode and PIN requirements.
      Only available to the Clinic Owner.
    parameters:
      - name: body
        in: body
        schema:
          type: object
          properties:
            requires_payment_approval:
              type: boolean
            requires_cash_approval:
              type: boolean
            requires_close_approval:
              type: boolean
            use_shared_terminal_mode:
              type: boolean
            require_pin_for_actions:
              type: boolean
            require_pin_for_signoff:
              type: boolean
    responses:
      200:
        description: Settings updated
      403:
        description: Permission denied
    """
    current_user = g.current_user

    clinic, error = clinic_service.update_settings(current_user, data)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return jsonify(msg="clinic settings updated", clinic=_serialize_clinic(clinic)), HTTPStatus.OK
