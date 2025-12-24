from __future__ import annotations

from sqlalchemy import select, func

from ..extensions import db
from ..models import User
from ..enums import UserRole
from ..utils.pagination import validate_pagination, page_meta


class UserRepository:
    def get_by_id(self, user_id: int):
        stmt = select(User).where(User.user_id == user_id)
        return db.session.scalar(stmt)

    def get_by_id_in_clinic(self, user_id: int, clinic_id: int):
        stmt = select(User).where(
            User.user_id == user_id,
            User.clinic_id == clinic_id,
        )
        return db.session.scalar(stmt)

    def get_by_email_in_clinic(self, email: str, clinic_id: int):
        stmt = select(User).where(
            User.email == email,
            User.clinic_id == clinic_id,
        )
        return db.session.scalar(stmt)

    def list_for_clinic(self, clinic_id: int):
        stmt = (
            select(User)
            .where(User.clinic_id == clinic_id)
            .order_by(User.name.asc())
        )
        return db.session.scalars(stmt).all()

    def list_for_clinic_paginated(
            self,
            clinic_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ):
        page, page_size = validate_pagination(page, page_size)

        base = select(User).where(User.clinic_id == clinic_id)

        total_items = db.session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        stmt = (
            base.order_by(User.name.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = db.session.scalars(stmt).all()

        meta = page_meta(page, page_size, total_items)
        return items, meta

    def create_user(
            self,
            *,
            clinic_id: int,
            name: str,
            email: str,
            role: UserRole,
            password: str,
            pin: str | None,
            requires_approval_for_actions: bool = True,
            is_active: bool = True,
    ):
        user = User(
            clinic_id=clinic_id,
            name=name,
            email=email,
            role=role,
            is_active=is_active,
            requires_approval_for_actions=requires_approval_for_actions,
        )
        user.set_password(password)
        if pin is not None:
            user.set_pin(pin)

        db.session.add(user)
        db.session.flush()
        return user

    def set_user_active(self, user: User, is_active: bool):
        user.is_active = is_active
        db.session.flush()
        return user


user_repo = UserRepository()
