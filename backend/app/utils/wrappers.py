from __future__ import annotations

from functools import wraps
from http import HTTPStatus

from flask import jsonify
from flask_jwt_extended import jwt_required

from ..enums import UserRole
from .helpers import load_current_user


def login_required(fn):
    @wraps(fn)
    @jwt_required()  # ensures token is valid
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if not user or not user.is_active:
            return jsonify(msg="user inactive or not found"), HTTPStatus.UNAUTHORIZED
        return fn(*args, **kwargs)

    return wrapper


def role_required(*allowed_roles: UserRole):
    """
    Restrict endpoint to given roles.

    Example:
        @role_required(UserRole.DOCTOR, UserRole.ACCOUNTANT)
        def some_route(): ...
    """
    allowed_values = {
        r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles
    }

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user = load_current_user()
            if (
                    not user
                    or not user.is_active
                    or user.role.value not in allowed_values
            ):
                return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def owner_only(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if not user or not user.is_active or not user.clinic:
            return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

        if user.clinic.owner_user_id != user.user_id:
            return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

        return fn(*args, **kwargs)

    return wrapper
