from __future__ import annotations

from typing import Tuple, Optional, List

from ..models import User, Patient
from ..data_layer.patient_repository import patient_repo
from ..data_layer.user_repository import user_repo
from ..schemas.patients import CreatePatientRequestSchema, UpdatePatientRequestSchema


class PatientService:

    def create_patient(
            self,
            current_user: User,
            payload: CreatePatientRequestSchema,
    ) -> Tuple[Optional[Patient], Optional[str]]:

        if not current_user.clinic_id:
            return None, "user has no clinic assigned"

        clinic_id = current_user.clinic_id

        doctor = user_repo.get_by_id_in_clinic(payload.doctor_id, clinic_id)
        if not doctor:
            return None, "doctor not found in this clinic"

        if payload.email is not None:
            email_str = str(payload.email)
            existing = patient_repo.get_by_email_in_clinic(email_str, clinic_id)
            if existing:
                return None, "email already in use for another patient in this clinic"
        else:
            email_str = None

        patient = patient_repo.create_patient(
            clinic_id=clinic_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            middle_name=payload.middle_name,
            birth_date=payload.birth_date,
            phone=payload.phone,
            email=email_str,
            note=payload.note,
            doctor_id=doctor.user_id,
        )

        return patient, None

    def archive_patient(self, current_user, patient_id):
        clinic_id = current_user.clinic_id
        if not clinic_id:
            return False, "user has no clinic assigned"

        patient = patient_repo.get_by_id_in_clinic(patient_id, clinic_id)
        if not patient:
            return False, "patient not found"

        patient.is_active = False
        return True, None

    # -------------------------------------------------------------------

    def list_patients_for_clinic(self, clinic_id: int, include_inactive: bool = False):
        return patient_repo.list_for_clinic(clinic_id, include_inactive=include_inactive)

    def list_patients_for_clinic_paginated(
            self,
            clinic_id: int,
            include_inactive: bool = False,
            page: int | None = None,
            page_size: int | None = None,
    ):
        return patient_repo.list_for_clinic_paginated(
            clinic_id,
            page=page,
            page_size=page_size,
            include_inactive=include_inactive
        )

    # -------------------------------------------------------------------

    def get_patient_for_clinic(
            self,
            clinic_id: int,
            patient_id: int,
    ) -> Optional[Patient]:
        return patient_repo.get_by_id_in_clinic(patient_id, clinic_id)

    # -------------------------------------------------------------------

    def update_patient(
            self,
            current_user: User,
            patient_id: int,
            payload: UpdatePatientRequestSchema,
    ) -> Tuple[Optional[Patient], Optional[str]]:

        if not current_user.clinic_id:
            return None, "user has no clinic assigned"

        clinic_id = current_user.clinic_id
        patient = patient_repo.get_by_id_in_clinic(patient_id, clinic_id)
        if not patient:
            return None, "patient not found"

        # Email change
        if payload.email is not None:
            email_str = str(payload.email)
            existing = patient_repo.get_by_email_in_clinic(email_str, clinic_id)
            if existing and existing.patient_id != patient.patient_id:
                return None, "email already in use for another patient in this clinic"
            patient.email = email_str

        # First/Last/Middle name, dob
        if payload.first_name is not None:
            patient.first_name = payload.first_name
        if payload.last_name is not None:
            patient.last_name = payload.last_name
        if payload.middle_name is not None:
            patient.middle_name = payload.middle_name
        if payload.birth_date is not None:
            patient.birth_date = payload.birth_date

        # Other fields
        if payload.phone is not None:
            patient.phone = payload.phone
        if payload.note is not None:
            patient.note = payload.note

        # Doctor change
        if payload.doctor_id is not None:
            doctor = user_repo.get_by_id_in_clinic(payload.doctor_id, clinic_id)
            if not doctor:
                return None, "doctor not found in this clinic"
            patient.doctor_id = doctor.user_id

        if payload.is_active is not None:
            patient.is_active = payload.is_active

        return patient, None

    # -------------------------------------------------------------------

    def list_patients_for_doctor(self, clinic_id: int, doctor_id: int):
        return patient_repo.list_for_doctor(clinic_id, doctor_id)

    def list_patients_for_doctor_paginated(
            self,
            clinic_id: int,
            doctor_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ):
        return patient_repo.list_for_doctor_paginated(
            clinic_id,
            doctor_id,
            page,
            page_size,
        )

    def list_patients_for_doctor_checked(
            self,
            clinic_id: int,
            doctor_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ):
        doctor = user_repo.get_by_id_in_clinic(doctor_id, clinic_id)
        if not doctor:
            return None, None, "doctor not found in this clinic"

        if page is None and page_size is None:
            items = patient_repo.list_for_doctor(clinic_id, doctor_id)
            return items, None, None

        items, meta = patient_repo.list_for_doctor_paginated(
            clinic_id, doctor_id, page, page_size
        )
        return items, meta, None

    # -------------------------------------------------------------------

    def search_patients_for_clinic(
            self,
            clinic_id: int,
            *,
            q: str | None = None,
            include_inactive: bool = False,
            first_name: str | None = None,
            last_name: str | None = None,
            middle_name: str | None = None,
            birth_date: date | None = None,
            phone: str | None = None,
            email: str | None = None,
            doctor_id: int | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ):
        if email:
            email = email.strip().lower()

        if page is None and page_size is None:
            items = patient_repo.search_for_clinic(
                clinic_id=clinic_id,
                q=q,
                include_inactive=include_inactive,
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name,
                birth_date=birth_date,
                phone=phone,
                email=email,
                doctor_id=doctor_id,
            )
            return items, None

        items, meta = patient_repo.search_for_clinic_paginated(
            clinic_id=clinic_id,
            q=q,
            include_inactive=include_inactive,
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
        return items, meta


patient_service = PatientService()
