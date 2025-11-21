from flask import Blueprint, jsonify

bp = Blueprint("cash", __name__)


@bp.get("/cash")
def cash():
    return jsonify({"status": "ok"})
