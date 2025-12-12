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
@owner_only
@use_schema(CreateUserRequestSchema)
def create_user(data: CreateUserRequestSchema):
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
@owner_only
def list_users():
    owner = g.current_user

    # read from query string: ?page=1&page_size=20
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
    user = g.current_user
    return jsonify(user=_serialize_user(user)), HTTPStatus.OK


@bp.patch("/me")
@login_required
@use_schema(UpdateMeRequestSchema)
def update_me(data: UpdateMeRequestSchema):
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
@owner_only
@use_schema(UpdateUserRequestSchema)
def update_user(user_id: int, data: UpdateUserRequestSchema):
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
@owner_only
@use_schema(SetUserStatusRequestSchema)
def set_user_status(user_id: int, data: SetUserStatusRequestSchema):
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
    current_user = g.current_user

    ok, error = user_service.verify_pin_for_user(current_user.clinic_id, user_id, data)
    if not ok:
        if error == "user not found":
            return jsonify(msg=error), HTTPStatus.NOT_FOUND
        if error == "PIN not set for this user":
            return jsonify(msg=error), HTTPStatus.BAD_REQUEST
        return jsonify(msg=error), HTTPStatus.UNAUTHORIZED

    return jsonify(msg="PIN verified"), HTTPStatus.OK
