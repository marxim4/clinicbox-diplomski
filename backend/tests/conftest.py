"""
Test Configuration and Fixtures.

This module defines the Pytest configuration for the application's test suite.
It handles:
1. Application Lifecycle: Creating a Flask app instance configured for testing.
2. Database Management: ensuring test isolation by creating a fresh, in-memory
   SQLite database for every test function using a transaction rollback strategy.
3. Factory Fixtures: Helper functions (Factory Pattern) to rapidly generate
   complex object graphs (e.g., a Clinic with Users, Patients, and Financial Plans)
   for specific test scenarios.
"""

import pytest
from datetime import date, timedelta
from sqlalchemy import orm
from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db as _db
from app.enums import UserRole, ClinicType, PlanStatus, PaymentMethod


class TestConfig(Config):
    """
    Configuration overrides for the testing environment.

    Uses an in-memory SQLite database for speed and strict isolation.
    Disables CSRF protection to simplify API testing.
    """
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    DEBUG = False
    JWT_SECRET_KEY = "test-secret-key"


@pytest.fixture(scope="session")
def app():
    """
    Creates a single Flask application instance for the entire test session.
    """
    app = create_app(config_object=TestConfig)
    with app.app_context():
        yield app


@pytest.fixture(scope="function")
def db_session(app):
    """
    Provides a transactional database session for each test function.

    This fixture creates all tables before a test runs and drops them afterwards
    (or rolls back the transaction), ensuring that tests do not leak state
    into one another. This guarantees test atomicity and reliability.
    """
    _db.create_all()

    connection = _db.engine.connect()
    transaction = connection.begin()

    # Create a scoped session bound to the connection
    session_factory = orm.sessionmaker(bind=connection)
    session = orm.scoped_session(session_factory)
    _db.session = session

    yield session

    # Teardown: Rollback transaction and clean up resources
    session.remove()
    transaction.rollback()
    connection.close()
    _db.drop_all()


@pytest.fixture
def client(app):
    """
    Creates a Flask test client for simulating HTTP requests (GET, POST, etc.)
    without running a live server.
    """
    return app.test_client()


@pytest.fixture
def auth_headers_generator(app):
    """
    Factory fixture to generate JWT Authorization headers.

    Allows tests to simulate authenticated requests by generating valid
    Bearer tokens for specific test users.
    """

    def _make_headers(user):
        with app.app_context():
            # Identity must be a string for JWT compatibility
            access_token = create_access_token(identity=str(user.user_id))
            return {
                'Authorization': f'Bearer {access_token}'
            }

    return _make_headers


# -------------------------------------------------------------------
# Model Factories
# These fixtures implement the Factory Pattern to simplify test setup.
# -------------------------------------------------------------------

@pytest.fixture
def clinic_factory(db_session):
    """
    Creates a Clinic instance with configurable settings.
    Default: Dental Clinic requiring strict financial approvals.
    """

    def create_clinic(name="Test Clinic", settings=None):
        from app.models.clinic import Clinic
        clinic = Clinic(
            name=name,
            clinic_type=ClinicType.DENTAL,
            currency="EUR",
            requires_payment_approval=True,
            requires_cash_approval=True
        )
        if settings:
            for k, v in settings.items():
                setattr(clinic, k, v)
        db_session.add(clinic)
        db_session.commit()
        return clinic

    return create_clinic


@pytest.fixture
def user_factory(db_session):
    """
    Creates a User instance with appropriate permissions based on Role.
    Default: Manager (Approver permissions).
    """

    def create_user(clinic, role=UserRole.MANAGER, email="test@test.com", name="Test User"):
        from app.models.user import User

        # Default permission logic mimicking the application domain
        can_approve = False
        req_approval = True

        if role in [UserRole.MANAGER, UserRole.OWNER]:
            can_approve = True
            req_approval = False

        user = User(
            clinic_id=clinic.clinic_id,
            name=name,
            email=email,
            role=role,
            can_approve_financials=can_approve,
            requires_approval_for_actions=req_approval
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()
        return user

    return create_user


@pytest.fixture
def cashbox_factory(db_session):
    """Creates a Cashbox (Physical Register) initialized with 0.00 balance."""

    def create_cashbox(clinic, name="Main Register"):
        from app.models.cashbox import Cashbox
        box = Cashbox(
            clinic_id=clinic.clinic_id,
            name=name,
            current_amount=0.00
        )
        db_session.add(box)
        db_session.commit()
        return box

    return create_cashbox


@pytest.fixture
def patient_factory(db_session):
    """Creates a Patient record associated with a specific Doctor and Clinic."""

    def create_patient(clinic, doctor, first_name="John", last_name="Doe"):
        from app.models.patient import Patient
        patient = Patient(
            clinic_id=clinic.clinic_id,
            doctor_id=doctor.user_id,
            first_name=first_name,
            last_name=last_name,
            email=f"{first_name}.{last_name}@example.com"
        )
        db_session.add(patient)
        db_session.commit()
        return patient

    return create_patient


@pytest.fixture
def plan_factory(db_session):
    """
    Creates an Installment Plan with generated monthly installments.
    Useful for testing payment waterfalls and debt calculations.
    """

    def create_plan(clinic, patient, doctor, total_amount=1000.0, installment_count=2):
        from app.models import InstallmentPlan, Installment

        plan = InstallmentPlan(
            clinic_id=clinic.clinic_id,
            patient_id=patient.patient_id,
            doctor_id=doctor.user_id,
            description="Dental Braces",
            total_amount=total_amount,
            status=PlanStatus.PLANNED,
            default_payment_method=PaymentMethod.CASH
        )
        db_session.add(plan)
        db_session.flush()

        amount_per_inst = total_amount / installment_count
        for i in range(installment_count):
            inst = Installment(
                plan_id=plan.plan_id,
                sequence=i + 1,
                due_date=date.today() + timedelta(days=30 * i),
                expected_amount=amount_per_inst,
                amount_paid=0
            )
            db_session.add(inst)

        db_session.commit()
        return plan

    return create_plan
