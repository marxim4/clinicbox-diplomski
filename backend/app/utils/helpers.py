from __future__ import annotations

from flask import g
from flask_jwt_extended import get_jwt_identity

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
    g.current_user = user
    g.jwt_identity = {"user_id": user_id}
    return user
