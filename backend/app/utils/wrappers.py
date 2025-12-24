from __future__ import annotations

from functools import wraps
from http import HTTPStatus

from flask import jsonify, g
from flask_jwt_extended import jwt_required

from ..enums import UserRole
from .helpers import load_current_user


def login_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if not user or not user.is_active:
            return jsonify(msg="user inactive or not found"), HTTPStatus.UNAUTHORIZED
        return fn(*args, **kwargs)

    return wrapper


def owner_only(fn):
    """
    Pure Permission Check.
    Ensures the current user is the registered owner of the clinic.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)

        if not user or not user.is_active or not user.clinic:
            return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

        owner_id = str(user.clinic.owner_user_id) if user.clinic.owner_user_id else ""
        current_id = str(user.user_id)

        if owner_id != current_id:
            return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

        return fn(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles: UserRole):
    allowed_values = {
        r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles
    }

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, "current_user", None)

            if (
                    not user
                    or not user.is_active
                    or user.role.value not in allowed_values
            ):
                return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_pin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        session_user = load_current_user()
        if not session_user:
            return jsonify(msg="unauthorized"), HTTPStatus.UNAUTHORIZED

        data_obj = kwargs.get("data")
        if not data_obj:
            return jsonify(msg="Payload missing"), HTTPStatus.BAD_REQUEST

        acting_user = session_user

        provided_user_id = getattr(data_obj, "acting_user_id", None)

        if provided_user_id and provided_user_id != session_user.user_id:
            acting_user = db.session.get(User, provided_user_id)
            if not acting_user or acting_user.clinic_id != session_user.clinic_id:
                return jsonify(msg="Invalid acting user"), HTTPStatus.FORBIDDEN

        clinic = acting_user.clinic
        if not clinic:
            return jsonify(msg="User has no clinic"), HTTPStatus.FORBIDDEN

        is_required = clinic.require_pin_for_actions or clinic.require_pin_for_signoff

        if is_required:
            provided_pin = getattr(data_obj, "pin", None)
            if not provided_pin:
                return jsonify(msg="PIN required"), HTTPStatus.FORBIDDEN

            if not acting_user.pin_hash:
                return jsonify(msg="Acting user has no PIN setup"), HTTPStatus.FORBIDDEN

            if not acting_user.check_pin(provided_pin):
                return jsonify(msg="Invalid PIN"), HTTPStatus.FORBIDDEN

        g.current_user = acting_user
        g.session_user = session_user

        return fn(*args, **kwargs)

    return wrapper
