from flask import Flask, jsonify

from .config import DevConfig
from .extensions import db, migrate, cors, jwt, bcrypt


def create_app(config_object=DevConfig) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    from . import models

    cors.init_app(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
    )
    jwt.init_app(app)

    from .blueprints.auth import bp as auth_bp
    from .blueprints.users import bp as users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    # a simple root route (optional)
    @app.get("/")
    def index():
        return jsonify({"app": "clinicBox", "status": "running"})

    return app
