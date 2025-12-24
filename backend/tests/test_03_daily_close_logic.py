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
    Scenario: Manager closes the register with a perfect count (0 variance).
    Expected: Close status is APPROVED, variance is 0.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_close@test.com")
    cashbox = cashbox_factory(clinic)

    # Arrange: Add €100 to the system
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0, note="Opening"
        )
    )

    # Act: Close with €100 count
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=100.0,
        date=date.today()
    )

    close, error = daily_close_service.create_daily_close(
        current_user=manager, session_user=manager, payload=payload
    )

    # Assert
    assert error is None
    assert close.status == DailyCloseStatus.APPROVED.value
    assert float(close.variance) == 0.0
    assert float(close.expected_total) == 100.0


def test_junior_close_with_missing_cash(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Junior staff counts €90, but system expects €100 (Variance: -€10).
    Expected: Close status is PENDING. Cashbox balance remains €100 until approved.
    """
    clinic = clinic_factory(settings={"requires_close_approval": True})
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_close@test.com")
    manager = user_factory(clinic, role=UserRole.MANAGER, email="boss_close@test.com")
    cashbox = cashbox_factory(clinic)

    # Arrange: Add €100
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0
        )
    )

    # Act: Close with €90
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id,
        counted_total=90.0,
        date=date.today()
    )
    close, _ = daily_close_service.create_daily_close(
        current_user=junior, session_user=junior, payload=payload
    )

    # Assert
    assert close.status == DailyCloseStatus.PENDING.value
    assert float(close.variance) == -10.0

    # Verify Cashbox: Should still show €100 (Pending closes do not adjust balance yet)
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 100.0


def test_manager_approves_variance(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Manager approves the PENDING close from the previous scenario.
    Expected: Status becomes APPROVED. Cashbox is adjusted via an 'Adjustment' transaction.
    """
    clinic = clinic_factory(settings={"requires_close_approval": True})
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_var@test.com")
    manager = user_factory(clinic, role=UserRole.MANAGER, email="boss_var@test.com")
    cashbox = cashbox_factory(clinic)

    # 1. Setup (System: 100, Count: 90)
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0
        )
    )

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
    Scenario: Closing a register on a day with zero transactions.
    Expected: Successful close with 0 variance.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    # Act
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
    assert float(close_record.variance) == 0.0


def test_forgotten_close_multi_day_accumulation(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: 'Forgotten Close' / Multi-day Accumulation.
    Day 1: €100 IN. No close performed.
    Day 2: €50 IN. Close performed.
    Expected: The system should capture both days' revenue (Total Expected: €150).
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    # --- Day 1 (Yesterday) ---
    monday_tx = CashTransaction(
        clinic_id=clinic.clinic_id,
        cashbox_id=cashbox.cashbox_id,
        type=CashTransactionType.IN,
        amount=100.0,
        status=TransactionStatus.CONFIRMED.value,
        created_by=manager.user_id,
        session_user_id=manager.user_id
    )
    # Manually backdate the transaction
    monday_tx.created_at = datetime.utcnow() - timedelta(days=1)

    db_session.add(monday_tx)
    cashbox.current_amount = 100.0
    db_session.commit()

    # --- Day 2 (Today) ---
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
    # Proves the close calculated revenue from the last close timestamp (or inception)
    assert float(close_record.expected_total) == 150.0


def test_service_reject_payment_after_close(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                            plan_factory):
    """
    Scenario: Attempting to process a payment after the Daily Close has been completed.
    Expected: Error (Day is closed).
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
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

    # 3. Expect Rejection
    assert payment is None
    assert error is not None
    assert "closed" in error.lower()


def test_service_reject_duplicate_close(db_session, clinic_factory, user_factory, cashbox_factory):
    """Verify that a cashbox cannot be closed twice on the same date."""
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id, counted_total=0.0, date=date.today()
    )

    # Close once
    daily_close_service.create_daily_close(current_user=manager, session_user=manager, payload=payload)

    # Attempt second close
    close2, error2 = daily_close_service.create_daily_close(
        current_user=manager, session_user=manager, payload=payload
    )

    assert close2 is None
    assert error2 is not None
    assert "already closed" in error2.lower()


def test_daily_close_blocked_by_pending_payments(db_session, clinic_factory, user_factory, cashbox_factory,
                                                 patient_factory, plan_factory):
    """
    Scenario: Clean Desk Policy Enforcement.
    Manager tries to close, but a Junior left a payment as PENDING.
    Expected: System blocks the close request until the pending payment is resolved.
    """
    clinic = clinic_factory(settings={"requires_payment_approval": True})

    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_clean_desk@test.com")
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_clean_desk@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_clean_desk@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    # 1. Create a Pending Payment
    pay_payload = CreatePaymentRequestSchema(
        amount=50.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    payment_service.create_payment(current_user=junior, session_user=junior, payload=pay_payload)

    # 2. Manager attempts Close
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


def test_reject_daily_close_no_impact(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Manager rejects a Daily Close with an incorrect count.
    Expected:
    1. Status becomes REJECTED.
    2. The Cashbox balance is NOT adjusted (no variance transaction created).
    """
    clinic = clinic_factory(settings={"requires_close_approval": True})
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_bad_count@test.com")
    manager = user_factory(clinic, role=UserRole.MANAGER, email="boss_reject@test.com")
    cashbox = cashbox_factory(clinic)

    # System has €100
    cash_service.create_transaction(
        current_user=manager, session_user=manager,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox.cashbox_id, type=CashTransactionType.IN, amount=100.0
        )
    )

    # Junior counts €50 (Huge error!)
    payload = CreateDailyCloseRequestSchema(
        cashbox_id=cashbox.cashbox_id, counted_total=50.0, date=date.today()
    )
    close, _ = daily_close_service.create_daily_close(
        current_user=junior, session_user=junior, payload=payload
    )

    # Manager Rejects
    rejected_close, error = daily_close_service.reject_daily_close(
        rejector=manager, close_id=close.close_id
    )

    assert error is None
    assert rejected_close.status == DailyCloseStatus.REJECTED.value
    assert rejected_close.approved_by == manager.user_id

    # CRITICAL: Verify Cashbox was NOT touched
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 100.0  # Still 100, not 50

    # Ensure no Adjustment transaction was created
    # We expect only 1 transaction (the initial IN 100.0)
    assert len(cashbox.transactions) == 1
