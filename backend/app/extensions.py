"""
Extensions module.

This module initializes the third-party Flask extensions used throughout the application,
such as SQLAlchemy for ORM, Migrate for database migrations, and JWTManager for authentication.
Centralizing them here avoids circular import issues.
"""

from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import MetaData

# Standard naming convention for database constraints to ensure migration compatibility
naming_convention = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=naming_convention)

db = SQLAlchemy(metadata=metadata)
migrate = Migrate()
cors = CORS()
jwt = JWTManager()
bcrypt = Bcrypt()
