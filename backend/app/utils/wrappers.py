from __future__ import annotations

from functools import wraps
from http import HTTPStatus

from flask import jsonify, g
from flask_jwt_extended import jwt_required

from ..enums import UserRole
from .helpers import load_current_user


def login_required(fn):
    # This remains the "Gatekeeper" that loads the user initially
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
    Assumes g.current_user is already set (by @login_required or @require_pin).
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)

        if not user or not user.is_active or not user.clinic:
            return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

        if user.clinic.owner_user_id != user.user_id:
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
        # 1. Identity 1: The Session User (Logged into JWT)
        session_user = load_current_user()
        if not session_user:
            return jsonify(msg="unauthorized"), HTTPStatus.UNAUTHORIZED

        # 2. Extract Data
        # We need to peek at the JSON body, which @use_schema has validated
        # but passing it via kwargs['data'] is safer if we ensure order.
        data_obj = kwargs.get("data")
        if not data_obj:
            # Fallback if @use_schema didn't run or failed
            return jsonify(msg="Payload missing"), HTTPStatus.BAD_REQUEST

        # 3. Identity 2: The Acting User (From Dropdown + PIN)
        acting_user = session_user  # Default: same person

        # Check if a different user is selected
        provided_user_id = getattr(data_obj, "acting_user_id", None)

        if provided_user_id and provided_user_id != session_user.user_id:
            acting_user = db.session.get(User, provided_user_id)
            if not acting_user or acting_user.clinic_id != session_user.clinic_id:
                return jsonify(msg="Invalid acting user"), HTTPStatus.FORBIDDEN

        # 4. Check PIN Rules (on the ACTING user's clinic)
        clinic = acting_user.clinic
        if not clinic:
            return jsonify(msg="User has no clinic"), HTTPStatus.FORBIDDEN

        # Logic: If general actions OR strict signoff requires PIN, we check it.
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
