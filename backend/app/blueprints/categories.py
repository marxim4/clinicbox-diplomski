from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, g
from flask import request

from ..extensions import db
from ..utils.wrappers import login_required
from ..utils.validation import use_schema
from ..schemas.categories import (
    CreateCategoryRequestSchema,
    UpdateCategoryRequestSchema,
    CategoryResponseSchema,
)
from ..services.category_service import category_service

bp = Blueprint("categories", __name__, url_prefix="/categories")


def _serialize_category(cat):
    return CategoryResponseSchema.model_validate(cat).model_dump()


@bp.post("")
@login_required
@use_schema(CreateCategoryRequestSchema)
def create_category(data: CreateCategoryRequestSchema):
    current_user = g.current_user

    category, error = category_service.create_category(current_user, data)
    if error == "user has no clinic assigned":
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error and "already exists" in error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="category created", category=_serialize_category(category)),
        HTTPStatus.CREATED,
    )


@bp.get("")
@login_required
def list_categories():
    current_user = g.current_user

    items, error = category_service.list_categories(current_user)
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    return (
        jsonify(categories=[_serialize_category(c) for c in items]),
        HTTPStatus.OK,
    )


@bp.patch("/<int:category_id>")
@login_required
@use_schema(UpdateCategoryRequestSchema)
def update_category(category_id: int, data: UpdateCategoryRequestSchema):
    current_user = g.current_user

    category, error = category_service.update_category(current_user, category_id, data)
    if error == "category not found in this clinic":
        return jsonify(msg=error), HTTPStatus.NOT_FOUND
    if error == "user has no clinic assigned":
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error and "already exists" in error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST
    if error:
        return jsonify(msg=error), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return (
        jsonify(msg="category updated", category=_serialize_category(category)),
        HTTPStatus.OK,
    )
