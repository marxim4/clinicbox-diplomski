from __future__ import annotations

from datetime import date
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

bp = Blueprint("patients", __name__, url_prefix="/api/patients")


def _serialize_patient(patient):
    return PatientResponseSchema(
        patient_id=patient.patient_id,
        clinic_id=patient.clinic_id,
        first_name=patient.first_name,
        last_name=patient.last_name,
        middle_name=patient.middle_name,
        birth_date=patient.birth_date,
        phone=patient.phone,
        email=patient.email,
        note=patient.note,
        doctor_id=patient.doctor_id,
    ).model_dump()


@bp.post("")
@login_required
@use_schema(CreatePatientRequestSchema)
def create_patient(data: CreatePatientRequestSchema):
    """
    Create Patient
    ---
    tags:
      - Patients
    security:
      - Bearer: []
    summary: Register a new patient.
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - first_name
            - last_name
            - email
          properties:
            first_name:
              type: string
            last_name:
              type: string
            email:
              type: string
              format: email
            phone:
              type: string
            birth_date:
              type: string
              format: date
            doctor_id:
              type: integer
              description: Primary physician ID.
    responses:
      201:
        description: Patient created
      409:
        description: Email already in use
      400:
        description: Validation error
    """
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
    """
    List Patients
    ---
    tags:
      - Patients
    security:
      - Bearer: []
    summary: Retrieve all patients for the clinic.
    parameters:
      - name: page
        in: query
        type: integer
      - name: page_size
        in: query
        type: integer
    responses:
      200:
        description: List of patients
    """
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
    """
    Get Patient Details
    ---
    tags:
      - Patients
    security:
      - Bearer: []
    summary: Retrieve a single patient by ID.
    parameters:
      - name: patient_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Patient details
      404:
        description: Patient not found
    """
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
    """
    Update Patient
    ---
    tags:
      - Patients
    security:
      - Bearer: []
    summary: Modify patient details.
    parameters:
      - name: patient_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        schema:
          type: object
          properties:
            first_name:
              type: string
            last_name:
              type: string
            email:
              type: string
            phone:
              type: string
            doctor_id:
              type: integer
    responses:
      200:
        description: Update successful
      404:
        description: Patient not found
    """
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
    """
    List Patients by Doctor
    ---
    tags:
      - Patients
    security:
      - Bearer: []
    summary: Retrieve all patients assigned to a specific doctor.
    parameters:
      - name: doctor_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: List of patients
    """
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
    """
    Search Patients
    ---
    tags:
      - Patients
    security:
      - Bearer: []
    summary: Advanced search for patients.
    parameters:
      - name: q
        in: query
        type: string
        description: General search query (name, email, phone).
      - name: first_name
        in: query
        type: string
      - name: last_name
        in: query
        type: string
      - name: email
        in: query
        type: string
      - name: doctor_id
        in: query
        type: integer
      - name: page
        in: query
        type: integer
        default: 1
      - name: page_size
        in: query
        type: integer
        default: 20
    responses:
      200:
        description: Search results
    """
    current_user = g.current_user
    clinic_id = current_user.clinic_id

    q = request.args.get("q", type=str)
    first_name = request.args.get("first_name", type=str)
    last_name = request.args.get("last_name", type=str)
    middle_name = request.args.get("middle_name", type=str)
    phone = request.args.get("phone", type=str)
    email = request.args.get("email", type=str)
    doctor_id = request.args.get("doctor_id", type=int)

    birth_date_str = request.args.get("birth_date", type=str)
    birth_date = None
    if birth_date_str:
        try:
            birth_date = date.fromisoformat(birth_date_str)
        except ValueError:
            return jsonify(msg="invalid birth_date format, expected YYYY-MM-DD"), HTTPStatus.BAD_REQUEST

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    items, meta = patient_service.search_patients_for_clinic(
        clinic_id=clinic_id,
        q=q,
        first_name=first_name,
        last_name=last_name,
        middle_name=middle_name,
        birth_date=birth_date,
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


@bp.delete("/<int:patient_id>")
@login_required
def delete_patient(patient_id: int):
    """
    Archive Patient
    ---
    tags:
      - Patients
    security:
      - Bearer: []
    summary: Soft-delete a patient.
    description: Only possible if the patient has no active financial plans.
    parameters:
      - name: patient_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Patient archived
      400:
        description: Cannot delete (e.g. active plans)
      404:
        description: Patient not found
    """
    current_user = g.current_user

    success, error = patient_service.archive_patient(current_user, patient_id)
    if not success:
        if error == "patient not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return jsonify(msg="patient archived"), HTTPStatus.OK
