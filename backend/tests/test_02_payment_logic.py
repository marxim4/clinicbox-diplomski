import pytest
from pydantic import ValidationError
from app.models.tip import Tip
from app.enums import UserRole, PaymentStatus, PlanStatus, PaymentMethod
from app.services.payment_service import payment_service
from app.services.installment_service import installment_service
from app.schemas.payments import CreatePaymentRequestSchema


def test_manager_payment_instant_effect(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                        plan_factory):
    """
    Scenario: A Manager (trusted) accepts a cash payment.
    Expected: Payment is IMMEDIATELY PAID, Cashbox increases, Debt decreases.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_inst@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_inst@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Action: Manager creates payment of €500
    payload = CreatePaymentRequestSchema(
        amount=500.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )

    payment, error = payment_service.create_payment(
        current_user=manager, session_user=manager, payload=payload
    )

    assert error is None
    assert payment.status == PaymentStatus.PAID.value

    # Verify Cashbox
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 500.0

    # Verify Debt
    db_session.refresh(plan)
    assert plan.installments[0].amount_paid == 500.0
    assert plan.status == PlanStatus.PARTIALLY_PAID


def test_junior_payment_requires_approval(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                          plan_factory):
    """
    Scenario: A Junior accepts a payment.
    Expected: Status PENDING. Cashbox UNCHANGED. Debt UNCHANGED.
    """
    clinic = clinic_factory(settings={"requires_payment_approval": True})
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_pend@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_pend@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    payload = CreatePaymentRequestSchema(
        amount=500.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id
    )

    payment, error = payment_service.create_payment(
        current_user=junior, session_user=junior, payload=payload
    )

    assert error is None
    assert payment.status == PaymentStatus.PENDING.value

    # Cashbox must be 0
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 0.0

    # Debt must be 0
    db_session.refresh(plan)
    assert plan.installments[0].amount_paid == 0.0


def test_approve_payment_flow(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory, plan_factory):
    """
    Scenario: Manager approves a pending payment.
    Expected: Logic triggers only AFTER approval.
    """
    clinic = clinic_factory(settings={"requires_payment_approval": True})
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_appr@test.com")
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_appr@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_appr@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # 1. Junior Pay
    payload = CreatePaymentRequestSchema(amount=500.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment, _ = payment_service.create_payment(current_user=junior, session_user=junior, payload=payload)

    assert payment.status == PaymentStatus.PENDING.value

    # 2. Manager Approve
    approved_payment, error = payment_service.approve_payment(approver=manager, payment_id=payment.payment_id)

    assert error is None
    assert approved_payment.status == PaymentStatus.PAID.value
    assert approved_payment.approved_by == manager.user_id

    # 3. Verify Effects
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 500.0

    db_session.refresh(plan)
    assert plan.installments[0].amount_paid == 500.0


def test_debt_cascade_math(db_session, clinic_factory, user_factory, patient_factory, plan_factory, cashbox_factory):
    """
    Scenario: Partial payment Logic.
    Payment: €700 on a €1000 plan (2x €500 installments).
    Expected: Inst 1 Full, Inst 2 Partial.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_math@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_math@test.com")
    patient = patient_factory(clinic, doctor)

    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0, installment_count=2)

    payload = CreatePaymentRequestSchema(amount=700.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment, error = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload)
    assert error is None

    db_session.refresh(plan)
    insts = sorted(plan.installments, key=lambda x: x.sequence)

    assert insts[0].amount_paid == 500.0  # Fully paid
    assert insts[1].amount_paid == 200.0  # Partially paid
    assert plan.status == PlanStatus.PARTIALLY_PAID


def test_card_payment_ignores_cashbox(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                      cashbox_factory):
    """
    Scenario: Payment made via CARD.
    Expected: Debt reduces, but Cashbox balance remains 0.00.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_card@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_card@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    # Action: Pay €100 via CARD
    payload = CreatePaymentRequestSchema(
        amount=100.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CARD
    )

    # --- UPDATED: Unpack result to catch errors ---
    payment, error = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload)

    # If this fails, the error message will tell us WHY (e.g. "Cashbox not needed for Card"?)
    assert error is None
    assert payment.status == PaymentStatus.PAID.value

    # Verify Debt is paid
    db_session.refresh(plan)
    assert plan.status == PlanStatus.PAID

    # Verify Cashbox is EMPTY (Card money doesn't go in the box)
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 0.0


def test_overpayment_treated_as_tip(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                    cashbox_factory):
    """
    Scenario: User pays €1200 on a €1000 debt.
    Expected: Debt Paid, €200 recorded as Tip.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_tip@test.com")
    cashbox = cashbox_factory(clinic)
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_tip@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Action: Pay €1200
    payload = CreatePaymentRequestSchema(amount=1200.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment, error = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload)
    assert error is None

    # Verify
    assert float(payment.amount) == 1000.0  # Applied to debt
    assert float(payment.tip_amount) == 200.0  # Excess becomes tip

    db_session.refresh(plan)
    assert plan.status == PlanStatus.PAID

    # Cashbox should have the full 1200
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 1200.0


def test_sequential_payments_with_tip(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                      cashbox_factory):
    """
    Scenario: The "700 then 350" workflow.
    1. Pay €700 on €1000 debt -> Partial.
    2. Pay €350 on remaining €300 -> Paid + €50 Tip.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_seq@test.com")
    cashbox = cashbox_factory(clinic)
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_seq@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # 1. Pay 700
    payload1 = CreatePaymentRequestSchema(amount=700.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload1)

    db_session.refresh(plan)
    assert plan.status == PlanStatus.PARTIALLY_PAID

    # 2. Pay 350 (Remaining debt is 300)
    payload2 = CreatePaymentRequestSchema(amount=350.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment2, error = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload2)
    assert error is None

    # Assertions
    assert float(payment2.amount) == 300.0  # Only 300 needed for debt
    assert float(payment2.tip_amount) == 50.0  # 50 extra

    db_session.refresh(plan)
    assert plan.status == PlanStatus.PAID

    # Total Cashbox = 700 + 350 = 1050
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 1050.0


def test_plan_cancellation(db_session, clinic_factory, user_factory, patient_factory, plan_factory):
    """
    Scenario: Manager cancels a plan.
    Expected: Plan status becomes CANCELLED.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_cancel@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_cancel@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Verify initial state
    assert plan.status == PlanStatus.PLANNED

    # Action: Cancel
    canceled_plan, error = installment_service.cancel_plan(current_user=manager, plan_id=plan.plan_id)

    assert error is None
    assert canceled_plan.status == PlanStatus.CANCELLED

    db_session.refresh(plan)
    assert plan.status == PlanStatus.CANCELLED


def test_complex_payment_waterfall_and_tips(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                            cashbox_factory):
    """
    Scenario:
      - Plan: €1000 total (2 installments of €500).
      - Payment 1: €700 -> Should pay Inst #1 (500) and part of Inst #2 (200).
      - Payment 2: €200 -> Should add to Inst #2 (Total 400).
      - Payment 3: €150 -> Should finish Inst #2 (Total 500) + €50 Tip.
    """
    # --- 1. Setup ---
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_waterfall@test.com")
    # Separate doctor to verify tips are assigned to the correct person
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doctor_rich@test.com")
    cashbox = cashbox_factory(clinic)
    patient = patient_factory(clinic, doctor)

    # Create Plan: €1000 total, 2 installments of €500
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0, installment_count=2)

    # Verify Doctor starts with 0 tips
    initial_tips = db_session.query(Tip).filter_by(doctor_id=doctor.user_id).count()
    assert initial_tips == 0

    # --- 2. Action: Pay €700 ---
    payload1 = CreatePaymentRequestSchema(amount=700.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload1)

    db_session.refresh(plan)
    # Sort installments by sequence to be sure which is which
    insts = sorted(plan.installments, key=lambda x: x.sequence)

    # Assertions for Pay #1
    assert insts[0].amount_paid == 500.0  # First bucket full
    assert insts[1].amount_paid == 200.0  # Overflow went here
    assert plan.status == PlanStatus.PARTIALLY_PAID

    # --- 3. Action: Pay €200 ---
    # This applies purely to the second installment
    payload2 = CreatePaymentRequestSchema(amount=200.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload2)

    db_session.refresh(plan)
    db_session.refresh(insts[1])  # Refresh the specific installment object

    # Assertions for Pay #2
    assert insts[0].amount_paid == 500.0
    assert insts[1].amount_paid == 400.0  # 200 (prev) + 200 (new)
    assert plan.status == PlanStatus.PARTIALLY_PAID

    # --- 4. Action: Pay €150 (The Tip Scenario) ---
    # We only owe €100 more on Installment 2. The extra €50 should become a Tip.
    payload3 = CreatePaymentRequestSchema(amount=150.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment3, _ = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload3)

    db_session.refresh(plan)
    db_session.refresh(insts[1])

    # Assertions for Pay #3
    assert insts[1].amount_paid == 500.0  # Bucket full
    assert plan.status == PlanStatus.PAID  # Plan done

    # Verify the specific payment object recorded the tip
    assert float(payment3.amount) == 100.0  # Debt reduced
    assert float(payment3.tip_amount) == 50.0  # Tip recorded

    # --- 5. Final Verification: Doctor's Tip Pool ---
    # Check the database for Tip records linked to this doctor
    doctor_tips = db_session.query(Tip).filter_by(doctor_id=doctor.user_id).all()

    assert len(doctor_tips) == 1
    assert float(doctor_tips[0].amount) == 50.0
    assert doctor_tips[0].plan_id == plan.plan_id  # Verify link to the plan


def test_service_create_valid_payment(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                      plan_factory):
    """Test creating a standard cash payment via Service."""
    clinic = clinic_factory()
    # Manager gets default email (e.g., test@test.com)
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
    # Doctor needs a UNIQUE email
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doctor_valid_pay@test.com")

    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    payload = CreatePaymentRequestSchema(
        amount=100.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )

    payment, error = payment_service.create_payment(
        current_user=manager, session_user=manager, payload=payload
    )

    assert error is None
    assert payment.status == PaymentStatus.PAID.value
    assert float(payment.amount) == 100.0


def test_service_reject_negative_payment(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                         plan_factory):
    """Test that Pydantic rejects negative payment amounts immediately."""
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doctor_neg_pay@test.com")

    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    # The schema itself should raise the error, not the service
    with pytest.raises(ValidationError) as excinfo:
        CreatePaymentRequestSchema(
            amount=-50.0,  # Negative!
            plan_id=plan.plan_id,
            cashbox_id=cashbox.cashbox_id,
            method=PaymentMethod.CASH
        )

    # Verify the error message mentions the amount issue
    assert "amount" in str(excinfo.value).lower() or "negative" in str(excinfo.value).lower()
