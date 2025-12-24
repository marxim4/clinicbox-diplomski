import pytest
from datetime import date, timedelta
from app.enums import UserRole, PaymentMethod
from app.services.daily_close_service import daily_close_service
from app.schemas.payments import CreatePaymentRequestSchema
from app.schemas.daily_close import CreateDailyCloseRequestSchema


def test_prevent_negative_payment_amount(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                         cashbox_factory):
    """
    Verifies Input Sanitization.

    Ensures that the application layer (Pydantic) rejects negative financial values
    before they reach business logic, preventing arithmetic exploits.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    patient = patient_factory(clinic, manager)
    plan = plan_factory(clinic, patient, manager, total_amount=100.0)
    cashbox = cashbox_factory(clinic)

    # Act & Assert: Schema Validation should fail
    try:
        CreatePaymentRequestSchema(
            plan_id=plan.plan_id,
            amount=-50.0,  # Invalid Input
            cashbox_id=cashbox.cashbox_id,
            method=PaymentMethod.CASH
        )
        pytest.fail("Schema validation failed to block negative amount!")
    except ValueError:
        pass


def test_prevent_future_daily_close(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Verifies Temporal Consistency.

    Prevents 'Time-Travel' errors where a user attempts to close the register
    for a future date, which would corrupt financial reporting timelines.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    tomorrow = date.today() + timedelta(days=1)

    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=100.0,
        date=tomorrow
    )

    close, error = daily_close_service.create_daily_close(
        current_user=manager,
        session_user=manager,
        payload=payload
    )

    assert close is None
    assert error is not None
    assert "future" in error.lower()


def test_prevent_duplicate_daily_close(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Verifies Idempotency/State Consistency.

    Ensures that a cash register cannot be closed twice for the same date,
    preventing duplicate financial entries in the aggregate reports.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    today = date.today()

    # 1. First Close -> Success
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=0.0,
        date=today
    )
    daily_close_service.create_daily_close(manager, manager, payload)

    # 2. Second Close -> Failure
    dup_close, error = daily_close_service.create_daily_close(manager, manager, payload)

    assert dup_close is None
    assert error is not None
    assert "already closed" in error.lower()
