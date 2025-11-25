from __future__ import annotations

from functools import wraps
from http import HTTPStatus

from flask import jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity

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
    Decorator factory: restrict endpoint to given roles.

    Example:
        @role_required(UserRole.OWNER, UserRole.ACCOUNTANT)
        def some_route(): ...
    """
    allowed_values = {
        r.value if isinstance(r, UserRole) else r for r in allowed_roles
    }

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            identity = get_jwt_identity() or {}
            role = identity.get("role")

            if role not in allowed_values:
                return jsonify(msg="forbidden"), HTTPStatus.FORBIDDEN

            load_current_user()
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def owner_only(fn):
    @wraps(fn)
    @role_required(UserRole.OWNER)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper
