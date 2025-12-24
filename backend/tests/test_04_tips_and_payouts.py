import pytest
from app.enums import UserRole, PaymentMethod, CashTransactionType
# Assuming TipPayoutStatus is in app.enums.tip_payout_status_enum based on your service code
from app.enums.tip_payout_status_enum import TipPayoutStatus
from app.services.payment_service import payment_service
from app.services.tip_service import tip_service
from app.schemas.payments import CreatePaymentRequestSchema
from app.schemas.tips import CreateTipPayoutRequestSchema
from app.models import Tip, TipPayout


def test_manual_tip_increases_cashbox_and_pool(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Receptionist adds a manual tip (e.g. patient gave €50 cash just for the doctor).
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_man_tip@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_man_tip@test.com")
    cashbox = cashbox_factory(clinic)

    # 1. Create a "Pure Tip"
    payload = CreatePaymentRequestSchema(
        doctor_id=doctor.user_id,
        amount=0.0,  # Pure tip
        tip_amount=50.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )

    payment, error = payment_service.create_payment(
        current_user=manager, session_user=manager, payload=payload
    )

    assert error is None

    # 2. Verify Cashbox (Money came IN: 0.0 + 50.0 = 50.0)
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 50.0

    # 3. Verify Doctor's Tip Record created
    tips = db_session.query(Tip).filter_by(doctor_id=doctor.user_id).all()
    assert len(tips) == 1
    assert float(tips[0].amount) == 50.0


def test_tip_payout_happy_path(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Doctor withdraws accumulated tips.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_payout@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_payout@test.com")

    # --- FIX: Create Cashbox AND mark it as default ---
    # This allows the tip_service to find the correct register to deduct money from.
    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()
    # --------------------------------------------------

    # 1. Seed the system: Give the doctor €100 in tips
    payload_in = CreatePaymentRequestSchema(
        doctor_id=doctor.user_id,
        amount=0.0,
        tip_amount=100.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload_in)

    # Verify setup
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 100.0

    # 2. Create Payout Request
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

    # Logic: If it went to PENDING (e.g. junior user or strict settings), approve it.
    if payout.status == TipPayoutStatus.PENDING.value:
        payout, _ = tip_service.approve_payout(approver=manager, payout_id=payout.payout_id)

    # --- ASSERTION FIX: Compare against TipPayoutStatus.PAID ---
    assert payout.status == TipPayoutStatus.PAID.value

    # 3. Verify Cashbox Dropped (100.0 - 100.0 = 0.0)
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 0.0

    # 4. Verify Transaction Log
    last_tx = cashbox.transactions[-1]
    assert last_tx.type == CashTransactionType.OUT
    assert float(last_tx.amount) == 100.0


def test_payout_overdraft_protection(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Doctor tries to withdraw more than they have earned.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_overdraft@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_overdraft@test.com")

    # --- FIX: Ensure we have a default cashbox ---
    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()
    # ---------------------------------------------

    # 1. Give doctor €50
    payload_in = CreatePaymentRequestSchema(
        doctor_id=doctor.user_id,
        amount=0.0,
        tip_amount=50.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload_in)

    # 2. Try to withdraw €100 (which exceeds the €50 available balance)
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

    # Depending on implementation, it might fail at creation OR require approval then fail.
    # The service code provided checks balance at creation, so we expect an error immediately.
    if payout and not error:
        # If it somehow succeeded to create as PENDING, approval must fail
        approved_payout, error = tip_service.approve_payout(approver=manager, payout_id=payout.payout_id)
        assert error is not None
        assert "exceeds" in error or "balance" in error or "insufficient" in error
    else:
        # Expected path: creation fails
        assert error is not None
        assert "exceeds" in error or "balance" in error