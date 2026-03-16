from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, g, request

from ..extensions import db
from ..utils.wrappers import login_required, owner_only
from ..utils.validation import use_schema
from ..schemas.users import (
    CreateUserRequestSchema,
    ChangePinRequestSchema,
    SetUserStatusRequestSchema,
    UpdateUserRequestSchema,
    UpdateMeRequestSchema,
    VerifyPinRequestSchema,
    UserResponseSchema,
)
from ..services.user_service import user_service

from ..schemas.pagination import PageMetaSchema

bp = Blueprint("users", __name__, url_prefix="/api/users")


def _serialize_user(user):
    return UserResponseSchema(
        user_id=user.user_id,
        clinic_id=user.clinic_id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        has_pin=bool(user.pin_hash),
        requires_approval_for_actions=user.requires_approval_for_actions,
    ).model_dump()


@bp.post("")
@login_required
@owner_only
@use_schema(CreateUserRequestSchema)
def create_user(data: CreateUserRequestSchema):
    """
    Create Staff User
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: Add a new staff member to the clinic.
    description: Only available to the Owner.
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - email
            - name
            - role
            - password
          properties:
            email:
              type: string
              format: email
            name:
              type: string
            role:
              type: string
              enum: ["MANAGER", "DOCTOR", "RECEPTIONIST"]
            password:
              type: string
            pin:
              type: string
              description: Optional 4-digit PIN
    responses:
      201:
        description: User created
      409:
        description: Email exists
    """
    owner = g.current_user

    user, error = user_service.create_clinic_user(owner, data)
    if error:
        status = (
            HTTPStatus.CONFLICT
            if "email already in use" in error
            else HTTPStatus.BAD_REQUEST
        )
        return jsonify(msg=error), status

    db.session.commit()

    return (
        jsonify(msg="user created", user=_serialize_user(user)),
        HTTPStatus.CREATED,
    )


@bp.get("")
@login_required
@owner_only
def list_users():
    """
    List Staff
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: List all users in the clinic.
    parameters:
      - name: page
        in: query
        type: integer
      - name: page_size
        in: query
        type: integer
    responses:
      200:
        description: List of users
    """
    owner = g.current_user

    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)

    if page is None and page_size is None:
        users = user_service.list_users_for_clinic(owner.clinic_id)
        return (
            jsonify(
                users=[_serialize_user(u) for u in users],
            ),
            HTTPStatus.OK,
        )

    items, meta = user_service.list_users_for_clinic_paginated(
        owner.clinic_id,
        page,
        page_size,
    )

    return (
        jsonify(
            users=[_serialize_user(u) for u in items],
            meta=PageMetaSchema(**meta).model_dump(by_alias=True)
        ),
        HTTPStatus.OK,
    )


@bp.get("/me")
@login_required
def get_me():
    """
    Get Current User Profile
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: Retrieve profile of the currently logged-in user.
    responses:
      200:
        description: User profile
    """
    user = g.current_user
    return jsonify(user=_serialize_user(user)), HTTPStatus.OK


@bp.patch("/me")
@login_required
@use_schema(UpdateMeRequestSchema)
def update_me(data: UpdateMeRequestSchema):
    """
    Update My Profile
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: Self-service update (Name, Email).
    parameters:
      - name: body
        in: body
        schema:
          type: object
          properties:
            name:
              type: string
            email:
              type: string
    responses:
      200:
        description: Profile updated
    """
    user = g.current_user

    updated_user, error = user_service.update_me(user, data)
    if error:
        if "email already in use" in error:
            return jsonify(msg=error), HTTPStatus.CONFLICT
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="profile updated", user=_serialize_user(updated_user)),
        HTTPStatus.OK,
    )


@bp.patch("/me/pin")
@login_required
@use_schema(ChangePinRequestSchema)
def change_my_pin(data: ChangePinRequestSchema):
    """
    Change My PIN
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: Update or set a 4-digit PIN.
    description: Requires current PIN if one is already set.
    parameters:
      - name: body
        in: body
        schema:
          type: object
          required:
            - new_pin
          properties:
            current_pin:
              type: string
            new_pin:
              type: string
    responses:
      200:
        description: PIN updated
      401:
        description: Incorrect current PIN
    """
    user = g.current_user

    updated_user, error = user_service.change_own_pin(user, data)
    if error:
        status = (
            HTTPStatus.UNAUTHORIZED
            if "incorrect" in error.lower() or "required" in error.lower()
            else HTTPStatus.BAD_REQUEST
        )
        return jsonify(msg=error), status

    db.session.commit()

    return jsonify(msg="PIN updated"), HTTPStatus.OK


@bp.patch("/<int:user_id>")
@login_required
@owner_only
@use_schema(UpdateUserRequestSchema)
def update_user(user_id: int, data: UpdateUserRequestSchema):
    """
    Update Staff User
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: Owner override to update staff details/permissions.
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        schema:
          type: object
          properties:
            role:
              type: string
            requires_approval_for_actions:
              type: boolean
            pin:
              type: string
              description: Reset user PIN
            clear_pin:
              type: boolean
              description: Remove PIN entirely
    responses:
      200:
        description: User updated
    """
    owner = g.current_user

    updated_user, error = user_service.update_user_by_owner(owner, user_id, data)
    if error:
        if error == "user not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        if "email already in use" in error:
            return jsonify(msg=error), HTTPStatus.CONFLICT
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="user updated", user=_serialize_user(updated_user)),
        HTTPStatus.OK,
    )


@bp.patch("/<int:user_id>/status")
@login_required
@owner_only
@use_schema(SetUserStatusRequestSchema)
def set_user_status(user_id: int, data: SetUserStatusRequestSchema):
    """
    Set User Status (Ban/Unban)
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: Activate or Deactivate a user account.
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        schema:
          type: object
          required:
            - is_active
          properties:
            is_active:
              type: boolean
    responses:
      200:
        description: Status updated
    """
    owner = g.current_user

    updated_user, error = user_service.set_user_active(owner, user_id, data)
    if error:
        if error == "user not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()

    return (
        jsonify(msg="user status updated", user=_serialize_user(updated_user)),
        HTTPStatus.OK,
    )


@bp.post("/<int:user_id>/verify-pin")
@login_required
@use_schema(VerifyPinRequestSchema)
def verify_pin(user_id: int, data: VerifyPinRequestSchema):
    """
    Verify PIN
    ---
    tags:
      - Users
    security:
      - Bearer: []
    summary: Verify a specific user's PIN.
    description: Used during 'Shared Terminal' mode to authorize an action for a user other than the logged-in session user.
    parameters:
      - name: user_id
        in: path
        type: integer
        description: The user attempting the action (Acting User)
      - name: body
        in: body
        schema:
          type: object
          required:
            - pin
          properties:
            pin:
              type: string
    responses:
      200:
        description: PIN Valid
      401:
        description: Invalid PIN
    """
    current_user = g.current_user

    ok, error = user_service.verify_pin_for_user(current_user.clinic_id, user_id, data)
    if not ok:
        if error == "user not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        if error == "PIN not set for this user":
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        return jsonify(msg=error), HTTPStatus.UNAUTHORIZED

    return jsonify(msg="PIN verified"), HTTPStatus.OK
