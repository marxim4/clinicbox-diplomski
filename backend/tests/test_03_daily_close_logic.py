from datetime import date, datetime, timedelta
import pytest
from app.enums import UserRole, DailyCloseStatus, CashTransactionType, TransactionStatus, PaymentMethod
from app.services.daily_close_service import daily_close_service
from app.services.cash_service import cash_service
from app.services.payment_service import payment_service
from app.schemas.daily_close import CreateDailyCloseRequestSchema
from app.schemas.cash import CreateCashTransactionRequestSchema
from app.schemas.payments import CreatePaymentRequestSchema
from app.models import CashTransaction


def test_daily_close_perfect_match(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Manager closes the day with a perfect count (0 variance).
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_close@test.com")
    cashbox = cashbox_factory(clinic)  # Starts at 0.00

    # 1. Add some money so expected amount is 100
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0, note="Opening"
        )
    )

    # 2. Perform Close
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=100.0,  # Matches expected
        date=date.today()
    )

    close, error = daily_close_service.create_daily_close(
        current_user=manager, session_user=manager, payload=payload
    )

    # 3. Verify
    assert error is None
    assert close.status == DailyCloseStatus.APPROVED.value
    assert float(close.variance) == 0.0
    assert float(close.expected_total) == 100.0


def test_junior_close_with_missing_cash(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Junior counts 90, but system expects 100 (Missing 10).
    """
    clinic = clinic_factory(settings={"requires_close_approval": True})
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_close@test.com")
    manager = user_factory(clinic, role=UserRole.MANAGER, email="boss_close@test.com")
    cashbox = cashbox_factory(clinic)

    # 1. Setup: Cashbox has 100
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0
        )
    )

    # 2. Junior counts only 90
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=90.0,
        date=date.today()
    )
    close, _ = daily_close_service.create_daily_close(
        current_user=junior, session_user=junior, payload=payload
    )

    # 3. Verify PENDING state
    assert close.status == DailyCloseStatus.PENDING.value
    assert float(close.variance) == -10.0

    # Cashbox should still say 100 until approved
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 100.0


def test_manager_approves_variance(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Manager approves the missing 10 EUR from the test above.
    """
    clinic = clinic_factory(settings={"requires_close_approval": True})
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_var@test.com")
    manager = user_factory(clinic, role=UserRole.MANAGER, email="boss_var@test.com")
    cashbox = cashbox_factory(clinic)

    # Add 100
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0
        )
    )

    # Junior counts 90
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id, counted_total=90.0, date=date.today()
    )
    close, _ = daily_close_service.create_daily_close(
        current_user=junior, session_user=junior, payload=payload
    )

    # 2. Manager Approves
    approved_close, error = daily_close_service.approve_daily_close(
        approver=manager, close_id=close.close_id
    )

    # 3. Verify Effects
    assert error is None
    assert approved_close.status == DailyCloseStatus.APPROVED.value

    # Check Cashbox: Should now be 90 to match reality
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 90.0

    last_tx = cashbox.transactions[-1]
    assert last_tx.type == CashTransactionType.ADJUSTMENT
    assert float(last_tx.amount) == -10.0
    assert "Approved Close" in last_tx.note


def test_daily_close_empty_day(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: It's Sunday. The clinic opened, nobody came, we close the register.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    # 1. Ensure Cashbox starts at 0
    assert float(cashbox.current_amount) == 0.0
    assert len(cashbox.transactions) == 0

    # 2. Attempt Close with 0.0
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=0.0,
        date=date.today()
    )

    close_record, error = daily_close_service.create_daily_close(
        current_user=manager,
        session_user=manager,
        payload=payload
    )

    assert error is None
    assert close_record is not None

    assert float(close_record.expected_total) == 0.0
    assert float(close_record.counted_total) == 0.0
    assert float(close_record.variance) == 0.0
    assert close_record.status == DailyCloseStatus.APPROVED.value


def test_forgotten_close_multi_day_accumulation(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: The 'Midnight' / Forgotten Close logic.
    1. Monday: €100 IN. Manager forgets to close.
    2. Tuesday: €50 IN. Manager closes Tuesday night.
    3. Expected: The system should capture BOTH (€150) safely.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    # --- Day 1 (Monday) ---
    monday_tx = CashTransaction(
        clinic_id=clinic.clinic_id,
        cashbox_id=cashbox.cashbox_id,
        type=CashTransactionType.IN,
        amount=100.0,
        status=TransactionStatus.CONFIRMED.value,
        created_by=manager.user_id,
        session_user_id=manager.user_id
    )
    # Set date manually AFTER initialization
    monday_tx.created_at = datetime.utcnow() - timedelta(days=1)

    db_session.add(monday_tx)
    cashbox.current_amount = 100.0
    db_session.commit()

    # --- Day 2 (Tuesday) ---
    tuesday_tx = CashTransaction(
        clinic_id=clinic.clinic_id,
        cashbox_id=cashbox.cashbox_id,
        type=CashTransactionType.IN,
        amount=50.0,
        status=TransactionStatus.CONFIRMED.value,
        created_by=manager.user_id,
        session_user_id=manager.user_id
    )
    db_session.add(tuesday_tx)
    cashbox.current_amount = 150.0
    db_session.commit()

    # --- The Close ---
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=150.0,
        date=date.today()
    )

    close_record, error = daily_close_service.create_daily_close(
        current_user=manager,
        session_user=manager,
        payload=payload
    )

    assert error is None
    # This proves the system includes Monday's 100 + Tuesday's 50
    assert float(close_record.expected_total) == 150.0


def test_service_daily_close_discrepancy(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Test daily close when money is missing via Service.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    # 1. Add 100 to system
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0
        )
    )

    # 2. Count only 90 (Missing 10)
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=90.0,
        date=date.today()
    )

    close, error = daily_close_service.create_daily_close(
        current_user=manager, session_user=manager, payload=payload
    )

    assert error is None
    assert float(close.variance) == -10.0


def test_service_reject_payment_after_close(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                            plan_factory):
    """
    Ensure no new payments can be added if the day is closed.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    # --- UNIQUE EMAIL FIX ---
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_closed_reject@test.com")

    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=500.0)

    # 1. Close the day
    close_payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id, counted_total=0.0, date=date.today()
    )
    daily_close_service.create_daily_close(current_user=manager, session_user=manager, payload=close_payload)

    # 2. Try to add a payment
    pay_payload = CreatePaymentRequestSchema(
        amount=100.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id
    )

    payment, error = payment_service.create_payment(
        current_user=manager, session_user=manager, payload=pay_payload
    )

    # 3. Expect Error
    assert payment is None
    assert error is not None
    assert "closed" in error.lower()


def test_service_reject_duplicate_close(db_session, clinic_factory, user_factory, cashbox_factory):
    """Ensure we can't close the same day twice."""
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id, counted_total=0.0, date=date.today()
    )

    # Close once
    daily_close_service.create_daily_close(current_user=manager, session_user=manager, payload=payload)

    # Close again
    close2, error2 = daily_close_service.create_daily_close(
        current_user=manager, session_user=manager, payload=payload
    )

    assert close2 is None
    assert error2 is not None
    assert "already closed" in error2.lower()


def test_daily_close_blocked_by_pending_payments(db_session, clinic_factory, user_factory, cashbox_factory,
                                                 patient_factory, plan_factory):
    """
    Scenario: Manager tries to close, but a Junior left a payment as PENDING.
    Expected: System rejects the close to force cleanup.
    """
    clinic = clinic_factory(settings={"requires_payment_approval": True})

    # Give everyone unique emails to avoid IntegrityError
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_clean_desk@test.com")
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_clean_desk@test.com")

    cashbox = cashbox_factory(clinic)

    # 1. Create a Pending Payment
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_clean_desk@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    pay_payload = CreatePaymentRequestSchema(
        amount=50.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    # Junior creates it -> PENDING
    payment_service.create_payment(current_user=junior, session_user=junior, payload=pay_payload)

    # 2. Manager tries to Close
    close_payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id, counted_total=0.0, date=date.today()
    )

    close, error = daily_close_service.create_daily_close(
        current_user=manager, session_user=manager, payload=close_payload
    )

    # 3. Assert Blocking
    assert close is None
    assert error is not None
    assert "pending payments" in error.lower()
