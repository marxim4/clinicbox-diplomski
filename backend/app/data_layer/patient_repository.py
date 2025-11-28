from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, func, or_

from ..extensions import db
from ..models import Patient
from ..utils.pagination import validate_pagination, page_meta


class PatientRepository:
    def get_by_id_in_clinic(self, patient_id: int, clinic_id: int) -> Optional[Patient]:
        stmt = select(Patient).where(
            Patient.patient_id == patient_id,
            Patient.clinic_id == clinic_id,
        )
        return db.session.scalar(stmt)

    def get_by_email(self, email: str) -> Optional[Patient]:
        # email is globally unique in the model, so we don't scope by clinic
        stmt = select(Patient).where(Patient.email == email)
        return db.session.scalar(stmt)

    def list_for_clinic(self, clinic_id: int) -> List[Patient]:
        stmt = (
            select(Patient)
            .where(Patient.clinic_id == clinic_id)
            .order_by(Patient.last_name.asc(), Patient.first_name.asc())
        )
        return db.session.scalars(stmt).all()

    def list_for_clinic_paginated(
            self,
            clinic_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ):
        page, page_size = validate_pagination(page, page_size)

        base = select(Patient).where(Patient.clinic_id == clinic_id)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(Patient.last_name.asc(), Patient.first_name.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()

        meta = page_meta(page, page_size, total_items)
        return items, meta

    def create_patient(
            self,
            *,
            clinic_id: int,
            first_name: str,
            last_name: str,
            phone: str | None,
            email: str | None,
            note: str | None,
            doctor_id: int,
    ) -> Patient:
        patient = Patient(
            clinic_id=clinic_id,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            note=note,
            doctor_id=doctor_id,
        )
        db.session.add(patient)
        db.session.flush()
        return patient

    def list_for_doctor(
            self,
            clinic_id: int,
            doctor_id: int,
    ):
        stmt = (
            select(Patient)
            .where(
                Patient.clinic_id == clinic_id,
                Patient.doctor_id == doctor_id,
            )
            .order_by(Patient.last_name.asc(), Patient.first_name.asc())
        )
        return db.session.scalars(stmt).all()

    def list_for_doctor_paginated(
            self,
            clinic_id: int,
            doctor_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ):
        page, page_size = validate_pagination(page, page_size)

        base = select(Patient).where(
            Patient.clinic_id == clinic_id,
            Patient.doctor_id == doctor_id,
        )

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(Patient.last_name.asc(), Patient.first_name.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()

        meta = page_meta(page, page_size, total_items)
        return items, meta

    def search_for_clinic(
            self,
            clinic_id: int,
            *,
            q: str | None = None,
            first_name: str | None = None,
            last_name: str | None = None,
            phone: str | None = None,
            email: str | None = None,
            doctor_id: int | None = None,
    ):
        base = select(Patient).where(Patient.clinic_id == clinic_id)

        # field filters
        if doctor_id is not None:
            base = base.where(Patient.doctor_id == doctor_id)

        if first_name:
            like = f"%{first_name.strip()}%"
            base = base.where(Patient.first_name.ilike(like))

        if last_name:
            like = f"%{last_name.strip()}%"
            base = base.where(Patient.last_name.ilike(like))

        if phone:
            like = f"%{phone.strip()}%"
            base = base.where(Patient.phone.ilike(like))

        if email:
            like = f"%{email.strip().lower()}%"
            base = base.where(Patient.email.ilike(like))

        if q:
            q_like = f"%{q.strip()}%"
            base = base.where(
                or_(
                    Patient.first_name.ilike(q_like),
                    Patient.last_name.ilike(q_like),
                    Patient.phone.ilike(q_like),
                    Patient.email.ilike(q_like),
                )
            )

        stmt = base.order_by(Patient.last_name.asc(), Patient.first_name.asc())
        return db.session.scalars(stmt).all()

    def search_for_clinic_paginated(
            self,
            clinic_id: int,
            *,
            q: str | None = None,
            first_name: str | None = None,
            last_name: str | None = None,
            phone: str | None = None,
            email: str | None = None,
            doctor_id: int | None = None,
            page: int | None = None,
            page_size: int | None = None,
    ):
        page, page_size = validate_pagination(page, page_size)

        base = select(Patient).where(Patient.clinic_id == clinic_id)

        if doctor_id is not None:
            base = base.where(Patient.doctor_id == doctor_id)

        if first_name:
            like = f"%{first_name.strip()}%"
            base = base.where(Patient.first_name.ilike(like))

        if last_name:
            like = f"%{last_name.strip()}%"
            base = base.where(Patient.last_name.ilike(like))

        if phone:
            like = f"%{phone.strip()}%"
            base = base.where(Patient.phone.ilike(like))

        if email:
            like = f"%{email.strip().lower()}%"
            base = base.where(Patient.email.ilike(like))

        if q:
            q_like = f"%{q.strip()}%"
            base = base.where(
                or_(
                    Patient.first_name.ilike(q_like),
                    Patient.last_name.ilike(q_like),
                    Patient.phone.ilike(q_like),
                    Patient.email.ilike(q_like),
                )
            )

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(Patient.last_name.asc(), Patient.first_name.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()

        meta = page_meta(page, page_size, total_items)
        return items, meta


patient_repo = PatientRepository()
