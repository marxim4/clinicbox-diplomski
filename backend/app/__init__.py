from flask import Flask, jsonify

from .config import DevConfig
from .extensions import db, migrate, cors, jwt


def create_app(config_object=DevConfig) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
    )
    jwt.init_app(app)

    from .blueprints.cash import bp as cash_bp
    from .blueprints.installment import bp as installment_bp
    from .blueprints.auth import bp as auth_bp

    app.register_blueprint(cash_bp, url_prefix="/api/cash")
    app.register_blueprint(installment_bp, url_prefix="/api/installment")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    # a simple root route (optional)
    @app.get("/")
    def index():
        return jsonify({"app": "clinicBox", "status": "running"})

    return app
