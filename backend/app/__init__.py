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
    from .blueprints.clinic import bp as clinic_bp

    from .blueprints.patients import bp as patients_bp
    from .blueprints.installment import bp as installment_bp
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

    # a simple root route (optional)
    @app.get("/")
    def index():
        return jsonify({"app": "clinicBox", "status": "running"})

    return app
