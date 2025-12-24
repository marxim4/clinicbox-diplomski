from __future__ import annotations
from flask import g
from flask_jwt_extended import get_jwt_identity, get_jwt
from ..extensions import db
from ..models import User


def load_current_user():
    if getattr(g, "current_user", None) is not None:
        return g.current_user

    identity = get_jwt_identity()
    if not identity:
        return None

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None

    user = db.session.get(User, user_id)

    if user:
        claims = get_jwt()
        token_version = int(claims.get("v", 0))

        if token_version != user.token_version:
            return None

    g.current_user = user
    return user
