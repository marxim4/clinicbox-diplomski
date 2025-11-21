from flask import Blueprint, jsonify

bp = Blueprint("installment", __name__)


@bp.get("/installment")
def installment():
    return jsonify({"status": "ok"})
