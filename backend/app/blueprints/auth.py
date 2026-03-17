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
from ..models import User, Clinic, Cashbox
from ..enums import UserRole, ClinicType
from ..schemas.auth import RegisterOwnerSchema, LoginSchema, ChangePasswordSchema
from ..utils.validation import use_schema
from ..utils.wrappers import login_required

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _issue_tokens_response(msg: str, user: User, status: HTTPStatus):
    user_id_str = str(user.user_id)

    claims = {"v": user.token_version}

    access = create_access_token(identity=user_id_str, additional_claims=claims)
    refresh = create_refresh_token(identity=user_id_str, additional_claims=claims)

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
    """
    Register a new Clinic Owner
    ---
    tags:
      - Authentication
    summary: Creates a new Clinic, a default Cashbox, and an Owner user.
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - owner_name
            - email
            - password
            - confirm_password
            - clinic_name
          properties:
            owner_name:
              type: string
              example: "Dr. John Doe"
            email:
              type: string
              format: email
              example: "owner@clinic.com"
            password:
              type: string
              format: password
              example: "StrongPass1!"
            confirm_password:
              type: string
              format: password
              example: "StrongPass1!"
            owner_role:
              type: string
              enum: ["OWNER"]
              default: "OWNER"
            clinic_name:
              type: string
              example: "City Dental"
            clinic_type:
              type: string
              enum: ["DENTAL", "MEDICAL", "VET", "OTHER"]
              default: "DENTAL"
            currency:
              type: string
              default: "EUR"
            default_language:
              type: string
              default: "en"
    responses:
      201:
        description: Registration successful
      409:
        description: Email already in use
      400:
        description: Validation error
    """
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
        clinic_type=clinic_type,
        currency=(data.currency or "EUR").strip(),
        default_language=(data.default_language or "en").strip(),
        timezone=(data.timezone or "UTC").strip(),

        requires_payment_approval=False,
        requires_cash_approval=False,
        requires_close_approval=False,
    )
    db.session.add(clinic)
    db.session.flush()

    owner_user = User(
        clinic_id=clinic.clinic_id,
        name=data.owner_name.strip(),
        email=data.email,
        role=data.owner_role,
        is_active=True,

        can_approve_financials=True,
        requires_approval_for_actions=False
    )
    owner_user.set_password(data.password)
    db.session.add(owner_user)
    db.session.flush()

    clinic.owner_user_id = owner_user.user_id

    default_cashbox = Cashbox(
        clinic_id=clinic.clinic_id,
        name="Main Cashbox",
        current_amount=0.0
    )
    default_cashbox.is_default = True
    db.session.add(default_cashbox)

    db.session.commit()

    return _issue_tokens_response("owner registered", owner_user, HTTPStatus.CREATED)


@bp.post("/login")
@use_schema(LoginSchema)
def login(data: LoginSchema):
    """
    User Login
    ---
    tags:
      - Authentication
    summary: Authenticate user and retrieve JWT tokens.
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
              example: "owner@clinic.com"
            password:
              type: string
              format: password
              example: "StrongPass1!"
    responses:
      200:
        description: Login successful
        schema:
          type: object
          properties:
            access_token:
              type: string
            refresh_token:
              type: string
            user_id:
              type: integer
            role:
              type: string
      401:
        description: Invalid credentials or inactive user
    """
    user = db.session.scalar(select(User).where(User.email == data.email))
    if not user or not user.is_active or not user.check_password(data.password):
        return jsonify(msg="invalid credentials"), HTTPStatus.UNAUTHORIZED

    return _issue_tokens_response("logged in", user, HTTPStatus.OK)


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """
    Refresh Access Token
    ---
    tags:
      - Authentication
    security:
      - Bearer: []
    summary: Use a valid Refresh Token to get a new Access Token.
    description: Requires the Refresh Token in the Authorization header (Bearer scheme).
    responses:
      200:
        description: Tokens refreshed
      401:
        description: Invalid or revoked token
    """
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity))

    if not user or not user.is_active:
        return jsonify(msg="user invalid"), HTTPStatus.UNAUTHORIZED

    resp, _ = _issue_tokens_response("refreshed", user, HTTPStatus.OK)
    return resp, HTTPStatus.OK


@bp.post("/logout")
def logout():
    """
    Logout
    ---
    tags:
      - Authentication
    summary: Clear authentication cookies.
    responses:
      200:
        description: Logged out successfully
    """
    resp = jsonify(msg="logged out")
    unset_jwt_cookies(resp)
    return resp, HTTPStatus.OK


@bp.post("/change-password")
@login_required
@use_schema(ChangePasswordSchema)
def change_password(data: ChangePasswordSchema):
    """
    Change Password
    ---
    tags:
      - Authentication
    security:
      - Bearer: []
    summary: Update the current user's password.
    description: Changing the password invalidates all existing tokens (version bump).
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - current_password
            - new_password
            - confirm_new_password
          properties:
            current_password:
              type: string
              format: password
            new_password:
              type: string
              format: password
            confirm_new_password:
              type: string
              format: password
    responses:
      200:
        description: Password changed successfully
      401:
        description: Incorrect current password
      400:
        description: Validation error (mismatch or complexity)
    """
    user = g.current_user

    if not user.check_password(data.current_password):
        return jsonify(msg="current password is incorrect"), HTTPStatus.UNAUTHORIZED

    user.set_password(data.new_password)
    db.session.commit()

    return jsonify(msg="password changed"), HTTPStatus.OK
