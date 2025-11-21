from flask import Blueprint, jsonify

bp = Blueprint("auth", __name__)


@bp.post("/login")
def login():
    # We'll implement real JWT login later
    return jsonify({"message": "login not implemented yet"}), 501
