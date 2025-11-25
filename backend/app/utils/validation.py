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
                json_data = {}

            try:
                obj = schema_cls.model_validate(json_data)
            except ValidationError as exc:
                return (
                    jsonify({"errors": exc.errors()}),
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                )

            return fn(*args, data=obj, **kwargs)

        return wrapper

    return decorator
