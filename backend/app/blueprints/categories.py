from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, g

from ..extensions import db
from ..utils.wrappers import login_required
from ..utils.validation import use_schema
from ..schemas.categories import (
    CreateCategoryRequestSchema,
    UpdateCategoryRequestSchema,
    CategoryResponseSchema,
)
from ..services.category_service import category_service

bp = Blueprint("categories", __name__, url_prefix="/api/categories")


def _serialize_category(cat):
    return CategoryResponseSchema.model_validate(cat).model_dump()


@bp.post("")
@login_required
@use_schema(CreateCategoryRequestSchema)
def create_category(data: CreateCategoryRequestSchema):
    """
    Create Category
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    summary: Create a new financial category.
    description: Used for tagging cash transactions (e.g., "Supplies", "Utilities").
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
          properties:
            name:
              type: string
              example: "Office Supplies"
            is_pinned:
              type: boolean
              default: false
              description: Pinned categories appear at the top of the UI list.
    responses:
      201:
        description: Category created
      400:
        description: Validation error or Duplicate name
    """
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
    """
    List Categories
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    summary: Retrieve all financial categories for the clinic.
    responses:
      200:
        description: List of categories
    """
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
    """
    Update Category
    ---
    tags:
      - Categories
    security:
      - Bearer: []
    summary: Rename or pin/unpin a category.
    parameters:
      - name: category_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        schema:
          type: object
          properties:
            name:
              type: string
            is_pinned:
              type: boolean
            is_active:
              type: boolean
    responses:
      200:
        description: Update successful
      404:
        description: Category not found
    """
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
