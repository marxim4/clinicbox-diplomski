from __future__ import annotations

from typing import Tuple, Optional, List

from ..models import User
from ..data_layer.user_repository import user_repo
from ..schemas.users import (
    CreateUserRequestSchema,
    ChangePinRequestSchema,
    SetUserStatusRequestSchema,
    UpdateUserRequestSchema,
    UpdateMeRequestSchema,
    VerifyPinRequestSchema,
)


class UserService:
    def create_clinic_user(
            self,
            owner: User,
            payload: CreateUserRequestSchema,
    ):
        if not owner.clinic_id:
            return None, "owner has no clinic assigned"

        email = payload.email

        existing = user_repo.get_by_email_in_clinic(email, owner.clinic_id)
        if existing:
            return None, "email already in use for this clinic"

        requires_approval = True

        user = user_repo.create_user(
            clinic_id=owner.clinic_id,
            name=payload.name,
            email=email,
            role=payload.role,
            password=payload.password,
            pin=payload.pin,
            requires_approval_for_actions=requires_approval,
            is_active=True,
        )
        return user, None

    def list_users_for_clinic(self, clinic_id: int):
        return user_repo.list_for_clinic(clinic_id)

    def list_users_for_clinic_paginated(
            self,
            clinic_id: int,
            page: int | None = None,
            page_size: int | None = None,
    ):
        return user_repo.list_for_clinic_paginated(clinic_id, page, page_size)

    def change_own_pin(
            self,
            user: User,
            payload: ChangePinRequestSchema,
    ):
        if user.pin_hash:
            if not payload.current_pin:
                return None, "current_pin is required"
            if not user.check_pin(payload.current_pin):
                return None, "current PIN is incorrect"

        user.set_pin(payload.new_pin)
        return user, None

    def set_user_active(
            self,
            owner: User,
            target_user_id: int,
            payload: SetUserStatusRequestSchema,
    ):
        if not owner.clinic_id:
            return None, "owner has no clinic assigned"

        target = user_repo.get_by_id_in_clinic(target_user_id, owner.clinic_id)
        if not target:
            return None, "user not found"

        if target.user_id == owner.user_id:
            return None, "owner cannot change their own active status"

        user_repo.set_user_active(target, payload.is_active)
        return target, None

    def update_user_by_owner(
            self,
            owner: User,
            target_user_id: int,
            payload: UpdateUserRequestSchema,
    ):
        if not owner.clinic_id:
            return None, "owner has no clinic assigned"

        target = user_repo.get_by_id_in_clinic(target_user_id, owner.clinic_id)
        if not target:
            return None, "user not found"

        if target.user_id == owner.user_id and payload.role is not None:
            return None, "owner cannot change their own role"

        if payload.email is not None:
            existing = user_repo.get_by_email_in_clinic(str(payload.email), owner.clinic_id)
            if existing and existing.user_id != target.user_id:
                return None, "email already in use for this clinic"
            target.email = str(payload.email)

        if payload.name is not None:
            target.name = payload.name

        if payload.role is not None:
            target.role = payload.role

        if payload.requires_approval_for_actions is not None:
            target.requires_approval_for_actions = payload.requires_approval_for_actions

        if payload.clear_pin:
            target.pin_hash = None
        elif payload.pin is not None:
            target.set_pin(payload.pin)

        return target, None

    def update_me(
            self,
            user: User,
            payload: UpdateMeRequestSchema,
    ):
        if payload.email is not None:
            existing = user_repo.get_by_email_in_clinic(str(payload.email), user.clinic_id)
            if existing and existing.user_id != user.user_id:
                return None, "email already in use for this clinic"
            user.email = str(payload.email)

        if payload.name is not None:
            user.name = payload.name

        return user, None

    def verify_pin_for_user(
            self,
            clinic_id: int,
            target_user_id: int,
            payload: VerifyPinRequestSchema,
    ):
        target = user_repo.get_by_id_in_clinic(target_user_id, clinic_id)
        if not target:
            return False, "user not found"

        if not target.pin_hash:
            return False, "PIN not set for this user"

        if not target.check_pin(payload.pin):
            return False, "invalid PIN"

        return True, None


user_service = UserService()
