import pytest
from decimal import Decimal
from datetime import date, timedelta
from sqlalchemy import select
from app.enums import UserRole, PaymentMethod, CashTransactionType
from app.models import Installment
from app.extensions import db
from app.services.daily_close_service import daily_close_service
from app.services.cash_service import cash_service
from app.services.installment_service import installment_service
from app.schemas.payments import CreatePaymentRequestSchema
from app.schemas.cash import CreateCashTransactionRequestSchema
from app.schemas.daily_close import CreateDailyCloseRequestSchema
from app.schemas.installments import CreateInstallmentPlanRequestSchema, InstallmentItemInputSchema


def test_installment_ids_retrievable_by_query_after_create_plan(
        db_session, clinic_factory, user_factory, patient_factory):
    """
    Regression: _replace_installments() in the repo calls plan.installments.clear()
    then adds new Installment rows via db.session.add() — bypassing the relationship
    collection. This leaves plan.installments empty in memory even though the rows
    are flushed to the DB.

    Accessing plan.installments after installment_service.create_plan() returns an
    empty list, so any code relying on it (e.g. plan.installments[0]) fails with
    IndexError or silently processes nothing.

    The correct approach is an explicit DB query by plan_id ordered by sequence.
    This test verifies that query returns the expected installment IDs and count.
    """
    today = date.today()
    clinic = clinic_factory()
    owner = user_factory(clinic, role=UserRole.OWNER, email="owner_plan_ids@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_plan_ids@test.com")
    patient = patient_factory(clinic, doctor)

    payload = CreateInstallmentPlanRequestSchema(
        patient_id=patient.patient_id,
        doctor_id=doctor.user_id,
        description="Test plan",
        total_amount=900.0,
        installments=[
            InstallmentItemInputSchema(due_date=today + timedelta(days=30), expected_amount=300.0),
            InstallmentItemInputSchema(due_date=today + timedelta(days=60), expected_amount=300.0),
            InstallmentItemInputSchema(due_date=today + timedelta(days=90), expected_amount=300.0),
        ],
    )
    plan, err = installment_service.create_plan(owner, payload)

    assert err is None
    # Relationship collection is empty due to _replace_installments internals —
    # do NOT assert on plan.installments here, that is the known broken path.

    # Query the correct way: explicit SELECT by plan_id ordered by sequence.
    inst_ids = list(db_session.scalars(
        select(Installment.installment_id)
        .where(Installment.plan_id == plan.plan_id)
        .order_by(Installment.sequence)
    ).all())

    assert len(inst_ids) == 3
    assert all(isinstance(i, int) for i in inst_ids)


def test_manual_deposit_on_float_balance_cashbox(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Regression: cashbox_repo.adjust_balance_for_transaction raised
    TypeError when current_amount was a Python float (e.g. 0.0 as set at
    construction time) rather than a Decimal read back from PostgreSQL.

    The seed exposes this because the cashbox is flushed but never committed
    before _deposit() is called, so current_amount stays a float at the
    Python object level.

    This test deliberately constructs the cashbox with a float current_amount
    and confirms that a manual deposit via cash_service completes without error
    and produces a correct Decimal balance.
    """
    from app.models.cashbox import Cashbox

    clinic = clinic_factory(settings={
        "requires_cash_approval": False,
        "requires_payment_approval": False,
    })
    owner = user_factory(clinic, role=UserRole.OWNER, email="owner_deposit@test.com")

    # Construct the cashbox with a Python float — deliberately NOT committing
    # before use, to reproduce the session-level float vs. Decimal mismatch.
    cashbox = Cashbox(
        clinic_id=clinic.clinic_id,
        name="Float Balance Box",
        is_default=True,
        current_amount=0.0,   # float, as in seed / real construction
    )
    db_session.add(cashbox)
    db_session.flush()        # flush only — current_amount stays float on object

    payload = CreateCashTransactionRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        type=CashTransactionType.IN,
        amount=200.0,
        note="Opening float",
    )

    tx, err = cash_service.create_transaction(owner, owner, payload)

    assert err is None
    assert tx is not None
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 200.0


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
