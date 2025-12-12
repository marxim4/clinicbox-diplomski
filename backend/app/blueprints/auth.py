from __future__ import annotations

from http import HTTPStatus
from flask import Blueprint, jsonify, g
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
    jwt_required,
    get_jwt_identity,
)

from sqlalchemy import select

from ..extensions import db
from ..models import User, Clinic
from ..enums import UserRole, ClinicType
from ..schemas.auth import RegisterOwnerSchema, LoginSchema, ChangePasswordSchema
from ..utils.validation import use_schema
from ..utils.wrappers import login_required

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _issue_tokens_response(msg: str, user: User, status: HTTPStatus):
    user_id_str = str(user.user_id)

    access = create_access_token(identity=user_id_str)
    refresh = create_refresh_token(identity=user_id_str)

    resp = jsonify(
        msg=msg,
        user_id=user.user_id,
        clinic_id=user.clinic_id,
        role=user.role.value if hasattr(user.role, "value") else user.role,
        access_token=access,
        refresh_token=refresh,
    )
    set_access_cookies(resp, access)
    set_refresh_cookies(resp, refresh)
    return resp, status


@bp.post("/register-owner")
@use_schema(RegisterOwnerSchema)
def register_owner(data: RegisterOwnerSchema):
    existing_user = db.session.scalar(
        select(User).where(User.email == data.email)
    )
    if existing_user:
        return jsonify(msg="email already in use"), HTTPStatus.CONFLICT

    if data.clinic_type:
        try:
            clinic_type = ClinicType[data.clinic_type.upper()]
        except KeyError:
            return jsonify(msg=f"invalid clinic_type '{data.clinic_type}'"), HTTPStatus.BAD_REQUEST
    else:
        clinic_type = ClinicType.OTHER

    clinic = Clinic(
        name=data.clinic_name.strip(),
        address=(data.clinic_address or "").strip() or None,
        currency=(data.currency or "EUR").strip() or "EUR",
        default_language=(data.default_language or "en").strip() or "en",
        clinic_type=clinic_type,
    )
    db.session.add(clinic)
    db.session.flush()

    # Create Owner User
    owner_user = User(
        clinic_id=clinic.clinic_id,
        name=data.owner_name.strip(),
        email=data.email,
        role=data.owner_role,
        is_active=True,
        requires_approval_for_actions=False,
    )
    owner_user.set_password(data.password)
    db.session.add(owner_user)
    db.session.flush()

    clinic.owner_user_id = owner_user.user_id

    db.session.commit()

    return _issue_tokens_response("owner registered", owner_user, HTTPStatus.CREATED)


@bp.post("/login")
@use_schema(LoginSchema)
def login(data: LoginSchema):
    user = db.session.scalar(select(User).where(User.email == data.email))
    if not user or not user.is_active or not user.check_password(data.password):
        return jsonify(msg="invalid credentials"), HTTPStatus.UNAUTHORIZED

    return _issue_tokens_response("logged in", user, HTTPStatus.OK)


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access = create_access_token(identity=identity)

    resp = jsonify(msg="refreshed", access_token=access)
    set_access_cookies(resp, access)
    return resp, HTTPStatus.OK


@bp.post("/logout")
def logout():
    resp = jsonify(msg="logged out")
    unset_jwt_cookies(resp)
    return resp, HTTPStatus.OK


@bp.post("/change-password")
@login_required
@use_schema(ChangePasswordSchema)
def change_password(data: ChangePasswordSchema):
    user = g.current_user

    if not user.check_password(data.current_password):
        return jsonify(msg="current password is incorrect"), HTTPStatus.UNAUTHORIZED

    user.set_password(data.new_password)
    db.session.commit()

    # TODO (later): revoke existing refresh tokens / sessions

    return jsonify(msg="password changed"), HTTPStatus.OK
