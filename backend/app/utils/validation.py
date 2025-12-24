from __future__ import annotations

from functools import wraps
from http import HTTPStatus

from flask import request, jsonify
from pydantic import BaseModel, ValidationError


def use_schema(schema_cls: type[BaseModel]):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            json_data = request.get_json(silent=True) or {}
            if not isinstance(json_data, dict):
                return (
                    jsonify(msg="JSON body must be an object"),
                    HTTPStatus.BAD_REQUEST,
                )

            try:
                obj = schema_cls.model_validate(json_data)
            except ValidationError as exc:
                simplified_errors = [
                    {
                        "loc": err.get("loc"),
                        "msg": err.get("msg"),
                        "type": err.get("type"),
                    }
                    for err in exc.errors()
                ]

                return (
                    jsonify(
                        msg="validation error",
                        errors=simplified_errors,
                    ),
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )

            return fn(*args, data=obj, **kwargs)

        return wrapper

    return decorator
