from flask import Flask, jsonify
from flasgger import Swagger

from .config import DevConfig
from .extensions import db, migrate, cors, jwt, bcrypt


def create_app(config_object=DevConfig) -> Flask:
    """
    Application Factory.

    Initializes the Flask application, registers extensions, blueprints, and
    API documentation (Swagger). This pattern allows for creating multiple
    instances of the app with different configurations.
    """
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Initialize Extensions
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    # Swagger API Documentation Setup
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec_1',
                "route": '/apispec_1.json',
                "rule_filter": lambda rule: True,  # Include all endpoints
                "model_filter": lambda tag: True,  # Include all models
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/"
    }

    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "ClinicBox API",
            "description": "Thesis Backend API Documentation",
            "version": "1.0.0"
        },
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "JWT Authorization header using the Bearer scheme. Example: \"Bearer {token}\""
            }
        },
        "security": [
            {"Bearer": []}
        ]
    }

    # Initialize Swagger
    Swagger(app, config=swagger_config, template=swagger_template)

    # CORS Setup: Allow credentials to support secure cookies
    cors.init_app(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
    )
    jwt.init_app(app)

    # Register Blueprints
    from . import models  # noqa: F401 (Ensure models are loaded for Migrations)

    from .blueprints.auth import bp as auth_bp
    from .blueprints.users import bp as users_bp
    from .blueprints.clinics import bp as clinic_bp

    from .blueprints.patients import bp as patients_bp
    from .blueprints.installments import bp as installment_bp
    from .blueprints.payments import bp as payments_bp
    from .blueprints.tips import bp as tips_bp

    from .blueprints.cashboxes import bp as cashboxes_bp
    from .blueprints.cash_transactions import bp as cash_transactions_bp
    from .blueprints.categories import bp as categories_bp
    from .blueprints.daily_closes import bp as daily_closes_bp

    from .blueprints.reports import bp as reports_bp
    from .blueprints.audit_logs import bp as audit_logs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(clinic_bp)

    app.register_blueprint(patients_bp)
    app.register_blueprint(installment_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(tips_bp)

    app.register_blueprint(cashboxes_bp)
    app.register_blueprint(cash_transactions_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(daily_closes_bp)

    app.register_blueprint(reports_bp)
    app.register_blueprint(audit_logs_bp)

    @app.get("/")
    def index():
        """Health check endpoint."""
        return jsonify({"app": "clinicBox", "status": "running"})

    return app
