from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, g, request

from ..extensions import db
from ..utils.wrappers import login_required
from ..utils.validation import use_schema
from ..schemas.patients import (
    CreatePatientRequestSchema,
    UpdatePatientRequestSchema,
    PatientResponseSchema,
)
from ..schemas.pagination import PageMetaSchema
from ..services.patient_service import patient_service

bp = Blueprint("patients", __name__, url_prefix="/patients")


def _serialize_patient(patient):
    return PatientResponseSchema(
        patient_id=patient.patient_id,
        clinic_id=patient.clinic_id,
        first_name=patient.first_name,
        last_name=patient.last_name,
        phone=patient.phone,
        email=patient.email,
        note=patient.note,
        doctor_id=patient.doctor_id,
    ).model_dump()


@bp.post("")
@login_required
@use_schema(CreatePatientRequestSchema)
def create_patient(data: CreatePatientRequestSchema):
    current_user = g.current_user

    patient, error = patient_service.create_patient(current_user, data)
    if error:
        if "email already in use" in error:
            return jsonify(msg=error), HTTPStatus.CONFLICT
        if "doctor not found" in error:
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()

    return (
        jsonify(msg="patient created", patient=_serialize_patient(patient)),
        HTTPStatus.CREATED,
    )


@bp.get("")
@login_required
def list_patients():
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    if page is None and page_size is None:
        patients = patient_service.list_patients_for_clinic(clinic_id)
        return (
            jsonify(
                patients=[_serialize_patient(p) for p in patients],
            ),
            HTTPStatus.OK,
        )

    items, meta = patient_service.list_patients_for_clinic_paginated(
        clinic_id,
        page,
        page_size,
    )

    return (
        jsonify(
            patients=[_serialize_patient(p) for p in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )


@bp.get("/<int:patient_id>")
@login_required
def get_patient(patient_id: int):
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    patient = patient_service.get_patient_for_clinic(clinic_id, patient_id)
    if not patient:
        return jsonify(msg="patient not found"), HTTPStatus.NOT_FOUND

    return jsonify(patient=_serialize_patient(patient)), HTTPStatus.OK


@bp.patch("/<int:patient_id>")
@login_required
@use_schema(UpdatePatientRequestSchema)
def update_patient(patient_id: int, data: UpdatePatientRequestSchema):
    current_user = g.current_user

    updated_patient, error = patient_service.update_patient(current_user, patient_id, data)
    if error:
        if error == "patient not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        if "email already in use" in error:
            return jsonify(msg=error), HTTPStatus.CONFLICT
        if "doctor not found" in error:
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()

    return (
        jsonify(msg="patient updated", patient=_serialize_patient(updated_patient)),
        HTTPStatus.OK,
    )


@bp.get("/doctor/<int:doctor_id>")
@login_required
def list_patients_for_doctor(doctor_id: int):
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta, error = patient_service.list_patients_for_doctor_checked(
        clinic_id,
        doctor_id,
        page,
        page_size,
    )
    if error == "doctor not found in this clinic":
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    if page is None and page_size is None:
        return (
            jsonify(
                patients=[_serialize_patient(p) for p in items],
            ),
            HTTPStatus.OK,
        )

    return (
        jsonify(
            patients=[_serialize_patient(p) for p in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )


@bp.get("/search")
@login_required
def search_patients():
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    q = request.args.get("q", type=str)
    first_name = request.args.get("first_name", type=str)
    last_name = request.args.get("last_name", type=str)
    phone = request.args.get("phone", type=str)
    email = request.args.get("email", type=str)
    doctor_id = request.args.get("doctor_id", type=int)

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta = patient_service.search_patients_for_clinic(
        clinic_id=clinic_id,
        q=q,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        doctor_id=doctor_id,
        page=page,
        page_size=page_size,
    )

    if page is None and page_size is None:
        return (
            jsonify(
                patients=[_serialize_patient(p) for p in items],
            ),
            HTTPStatus.OK,
        )

    return (
        jsonify(
            patients=[_serialize_patient(p) for p in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True),
        ),
        HTTPStatus.OK,
    )
