import pytest
from app.enums import UserRole, PaymentMethod, CashTransactionType
from app.enums.tip_payout_status_enum import TipPayoutStatus
from app.services.payment_service import payment_service
from app.services.tip_service import tip_service
from app.schemas.payments import CreatePaymentRequestSchema
from app.schemas.tips import CreateTipPayoutRequestSchema
from app.models import Tip, TipPayout


def test_manual_tip_increases_cashbox_and_pool(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Verifies that a manual tip entry (without underlying debt payment) correctly
    updates both the physical cashbox balance and the doctor's virtual tip ledger.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_man_tip@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_man_tip@test.com")
    cashbox = cashbox_factory(clinic)

    # Act: Create a "Pure Tip" of €50
    payload = CreatePaymentRequestSchema(
        doctor_id=doctor.user_id,
        amount=0.0,
        tip_amount=50.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )

    payment, error = payment_service.create_payment(
        current_user=manager, session_user=manager, payload=payload
    )

    assert error is None

    # Assert 1: Physical Cashbox increased
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 50.0

    # Assert 2: Virtual Ledger updated
    tips = db_session.query(Tip).filter_by(doctor_id=doctor.user_id).all()
    assert len(tips) == 1
    assert float(tips[0].amount) == 50.0


def test_tip_payout_happy_path(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Verifies the complete lifecycle of a tip withdrawal: accumulation,
    payout request creation, approval, and physical cash deduction.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_payout@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_payout@test.com")

    # Arrange: Set default cashbox for payout deductions
    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    # Step 1: Accumulate funds (Give doctor €100 in tips)
    payload_in = CreatePaymentRequestSchema(
        doctor_id=doctor.user_id,
        amount=0.0,
        tip_amount=100.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload_in)

    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 100.0

    # Step 2: Create Payout Request
    payload_out = CreateTipPayoutRequestSchema(
        amount=100.0,
        note="Weekly withdrawal"
    )

    payout, error = tip_service.create_payout(
        current_user=manager,
        session_user=manager,
        doctor_id=doctor.user_id,
        amount=payload_out.amount,
        note=payload_out.note
    )
    assert error is None

    # Step 3: Approval (if pending)
    if payout.status == TipPayoutStatus.PENDING.value:
        payout, _ = tip_service.approve_payout(approver=manager, payout_id=payout.payout_id)

    assert payout.status == TipPayoutStatus.PAID.value

    # Step 4: Verify Physical Deduction
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 0.0

    # Step 5: Verify Audit Log
    last_tx = cashbox.transactions[-1]
    assert last_tx.type == CashTransactionType.OUT
    assert float(last_tx.amount) == 100.0


def test_payout_overdraft_protection(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Verifies the solvency check mechanism. Ensures that a payout request is rejected
    if it exceeds the doctor's current accumulated tip balance.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_overdraft@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_overdraft@test.com")

    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    # Arrange: Doctor has €50 balance
    payload_in = CreatePaymentRequestSchema(
        doctor_id=doctor.user_id,
        amount=0.0,
        tip_amount=50.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload_in)

    # Act: Attempt to withdraw €100 (Overdraft)
    payload_out = CreateTipPayoutRequestSchema(
        amount=100.0
    )

    payout, error = tip_service.create_payout(
        current_user=manager,
        session_user=manager,
        doctor_id=doctor.user_id,
        amount=payload_out.amount,
        note=payload_out.note
    )

    # Assert: Should fail either at creation or approval stage
    if payout and not error:
        approved_payout, error = tip_service.approve_payout(approver=manager, payout_id=payout.payout_id)
        assert error is not None
        assert "exceeds" in error or "balance" in error
    else:
        assert error is not None
        assert "exceeds" in error or "balance" in error


def test_reject_tip_payout_restores_nothing(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Manager rejects a tip withdrawal request.
    Expected:
    1. Status is REJECTED.
    2. No money leaves the cashbox.
    3. The Doctor's tip balance is UNAFFECTED (it was never deducted because it was pending).
    """
    clinic = clinic_factory(settings={"requires_cash_approval": True})
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_tip_rej@test.com")
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_tip_req@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_tip_rej@test.com")

    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    # 1. Earn €100 in tips
    payload_in = CreatePaymentRequestSchema(
        doctor_id=doctor.user_id, amount=0.0, tip_amount=100.0,
        cashbox_id=cashbox.cashbox_id, method=PaymentMethod.CASH
    )
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload_in)

    # 2. Junior requests payout (PENDING)
    payout, _ = tip_service.create_payout(
        current_user=junior, session_user=junior,
        doctor_id=doctor.user_id, amount=100.0, note="Can I have cash?"
    )
    assert payout.status == TipPayoutStatus.PENDING.value

    # 3. Manager Rejects
    rejected_payout, error = tip_service.reject_payout(rejector=manager, payout_id=payout.payout_id)

    assert error is None
    assert rejected_payout.status == TipPayoutStatus.REJECTED.value
    assert rejected_payout.approved_by == manager.user_id

    # 4. Verify Financial Safety
    # Cashbox should still have the €100 (No money OUT)
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 100.0

    # Doctor should still have €100 balance available (Solvency check)
    balance = tip_service.get_doctor_tip_balance(clinic.clinic_id, doctor.user_id)
    assert balance['balance'] == 100.0
