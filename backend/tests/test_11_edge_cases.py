import pytest
from datetime import date, timedelta
from app.enums import UserRole, PaymentMethod
from app.services.payment_service import payment_service
from app.services.daily_close_service import daily_close_service
from app.schemas.payments import CreatePaymentRequestSchema
from app.schemas.daily_close import CreateDailyCloseRequestSchema  # <--- FIXED NAME


def test_prevent_negative_payment_amount(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                         cashbox_factory):
    """
    Edge Case: User enters a negative amount (e.g. -50) to exploit the math logic.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    patient = patient_factory(clinic, manager)
    plan = plan_factory(clinic, patient, manager, total_amount=100.0)
    cashbox = cashbox_factory(clinic)

    # We expect Pydantic validation to fail before it even reaches the service logic
    try:
        CreatePaymentRequestSchema(
            plan_id=plan.plan_id,
            amount=-50.0,  # <--- ATTACK
            cashbox_id=cashbox.cashbox_id,
            method=PaymentMethod.CASH
        )
        pytest.fail("Schema validation failed to block negative amount!")
    except ValueError:
        # Pass: Pydantic correctly raised a validation error
        pass


def test_prevent_future_daily_close(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Edge Case: Closing the register for a future date (e.g. tomorrow).
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    tomorrow = date.today() + timedelta(days=1)

    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=100.0,  # <--- FIXED FIELD NAME
        date=tomorrow  # <--- ATTACK
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
    Edge Case: Trying to close the same register twice for the same day.
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
    # Ensure no existing close blocks us
    # (In a real test env, we start fresh, so this is fine)

    daily_close_service.create_daily_close(manager, manager, payload)

    # 2. Second Close -> Should Fail
    dup_close, error = daily_close_service.create_daily_close(manager, manager, payload)

    assert dup_close is None
    assert error is not None
    assert "already closed" in error.lower()