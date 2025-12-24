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
    Scenario: A Manager (Trusted User) processes a cash payment.
    Expected: Payment is immediately PAID, cashbox balance increases, and debt decreases.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_inst@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_inst@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Act: Manager processes €500 payment
    payload = CreatePaymentRequestSchema(
        amount=500.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )

    payment, error = payment_service.create_payment(
        current_user=manager, session_user=manager, payload=payload
    )

    # Assert
    assert error is None
    assert payment.status == PaymentStatus.PAID.value

    # Verify Cashbox Balance Updated
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 500.0

    # Verify Installment Paid
    db_session.refresh(plan)
    assert plan.installments[0].amount_paid == 500.0
    assert plan.status == PlanStatus.PARTIALLY_PAID


def test_junior_payment_requires_approval(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                          plan_factory):
    """
    Scenario: A Junior Receptionist accepts a payment in a restricted clinic.
    Expected: Status is PENDING. No money moves, no debt is reduced.
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

    # Assert: Cashbox remains 0
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 0.0

    # Assert: Debt remains 0
    db_session.refresh(plan)
    assert plan.installments[0].amount_paid == 0.0


def test_approve_payment_flow(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory, plan_factory):
    """
    Scenario: A Manager approves a previously PENDING payment.
    Expected: Financial effects (Cashbox/Debt) are applied only after approval.
    """
    clinic = clinic_factory(settings={"requires_payment_approval": True})
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_appr@test.com")
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_appr@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_appr@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # 1. Junior creates Pending Payment
    payload = CreatePaymentRequestSchema(amount=500.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment, _ = payment_service.create_payment(current_user=junior, session_user=junior, payload=payload)
    assert payment.status == PaymentStatus.PENDING.value

    # 2. Manager Approves
    approved_payment, error = payment_service.approve_payment(approver=manager, payment_id=payment.payment_id)

    assert error is None
    assert approved_payment.status == PaymentStatus.PAID.value
    assert approved_payment.approved_by == manager.user_id

    # 3. Verify Effects Applied
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 500.0

    db_session.refresh(plan)
    assert plan.installments[0].amount_paid == 500.0


def test_debt_cascade_math(db_session, clinic_factory, user_factory, patient_factory, plan_factory, cashbox_factory):
    """
    Scenario: Payment covers one full installment and partially covers the next.
    Input: €700 payment on a €1000 plan (2x €500).
    Expected: Installment 1 full (€500), Installment 2 partial (€200).
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
    Scenario: Payment made via CREDIT CARD.
    Expected: Debt reduces, but physical Cashbox balance remains unchanged.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_card@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_card@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    # Act: Pay €100 via CARD
    payload = CreatePaymentRequestSchema(
        amount=100.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CARD
    )

    payment, error = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload)

    assert error is None
    assert payment.status == PaymentStatus.PAID.value

    # Verify Debt is paid
    db_session.refresh(plan)
    assert plan.status == PlanStatus.PAID

    # Verify Cashbox is EMPTY
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 0.0


def test_overpayment_treated_as_tip(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                    cashbox_factory):
    """
    Scenario: Patient overpays their total debt.
    Input: €1200 payment on a €1000 debt.
    Expected: Debt fully paid, €200 recorded as a Tip.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_tip@test.com")
    cashbox = cashbox_factory(clinic)
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_tip@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    payload = CreatePaymentRequestSchema(amount=1200.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment, error = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload)
    assert error is None

    # Verify Split
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
    Scenario: Multi-step payment workflow with final overpayment.
    1. Pay €700 on €1000 debt -> Partial Status.
    2. Pay €350 on remaining €300 -> Paid Status + €50 Tip.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_seq@test.com")
    cashbox = cashbox_factory(clinic)
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_seq@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Step 1: Pay 700
    payload1 = CreatePaymentRequestSchema(amount=700.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload1)

    db_session.refresh(plan)
    assert plan.status == PlanStatus.PARTIALLY_PAID

    # Step 2: Pay 350 (Remaining debt is 300)
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
    Scenario: Manager cancels a financial plan.
    Expected: Plan status transitions to CANCELLED.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_cancel@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_cancel@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Action: Cancel
    canceled_plan, error = installment_service.cancel_plan(current_user=manager, plan_id=plan.plan_id)

    assert error is None
    assert canceled_plan.status == PlanStatus.CANCELLED

    db_session.refresh(plan)
    assert plan.status == PlanStatus.CANCELLED


def test_complex_payment_waterfall_and_tips(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                            cashbox_factory):
    """
    Scenario: Complex Waterfall Distribution.
    Plan: €1000 total (2 installments of €500).
    Steps:
      1. Pay €700 -> Fills Inst #1 (500), spills €200 to Inst #2.
      2. Pay €200 -> Adds to Inst #2 (Total 400).
      3. Pay €150 -> Fills Inst #2 (Total 500), remaining €50 becomes Tip.
    """
    # 1. Setup
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_waterfall@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doctor_rich@test.com")
    cashbox = cashbox_factory(clinic)
    patient = patient_factory(clinic, doctor)

    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0, installment_count=2)

    # Verify Doctor starts with 0 tips
    initial_tips = db_session.query(Tip).filter_by(doctor_id=doctor.user_id).count()
    assert initial_tips == 0

    # 2. Action: Pay €700
    payload1 = CreatePaymentRequestSchema(amount=700.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload1)

    db_session.refresh(plan)
    insts = sorted(plan.installments, key=lambda x: x.sequence)

    assert insts[0].amount_paid == 500.0  # First bucket full
    assert insts[1].amount_paid == 200.0  # Overflow
    assert plan.status == PlanStatus.PARTIALLY_PAID

    # 3. Action: Pay €200
    payload2 = CreatePaymentRequestSchema(amount=200.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment_service.create_payment(current_user=manager, session_user=manager, payload=payload2)

    db_session.refresh(plan)
    db_session.refresh(insts[1])

    assert insts[1].amount_paid == 400.0  # 200 previous + 200 new
    assert plan.status == PlanStatus.PARTIALLY_PAID

    # 4. Action: Pay €150 (triggers Tip)
    payload3 = CreatePaymentRequestSchema(amount=150.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment3, _ = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload3)

    db_session.refresh(plan)
    db_session.refresh(insts[1])

    assert insts[1].amount_paid == 500.0  # Full
    assert plan.status == PlanStatus.PAID  # Plan done

    assert float(payment3.amount) == 100.0  # Debt reduced
    assert float(payment3.tip_amount) == 50.0  # Tip recorded

    # 5. Verify Tip Ledger
    doctor_tips = db_session.query(Tip).filter_by(doctor_id=doctor.user_id).all()
    assert len(doctor_tips) == 1
    assert float(doctor_tips[0].amount) == 50.0
    assert doctor_tips[0].plan_id == plan.plan_id


def test_service_create_valid_payment(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                      plan_factory):
    """Test standard payment creation success path."""
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
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
    """Verifies that the schema validation layer rejects negative payment amounts."""
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doctor_neg_pay@test.com")

    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    # Act & Assert: Schema validation should raise error
    with pytest.raises(ValidationError) as excinfo:
        CreatePaymentRequestSchema(
            amount=-50.0,
            plan_id=plan.plan_id,
            cashbox_id=cashbox.cashbox_id,
            method=PaymentMethod.CASH
        )

    assert "amount" in str(excinfo.value).lower() or "negative" in str(excinfo.value).lower()


def test_reject_payment_audit_trail(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                    plan_factory):
    """
    Scenario: A Manager rejects a suspicious payment created by a Junior.
    Expected:
    1. Status becomes REJECTED.
    2. 'approved_by' records the Manager's ID (Audit Trail).
    3. NO money moves (Cashbox 0).
    4. NO debt is reduced (Plan 0).
    """
    clinic = clinic_factory(settings={"requires_payment_approval": True})
    manager = user_factory(clinic, role=UserRole.MANAGER, email="manager_reject@test.com")
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior_reject@test.com")
    cashbox = cashbox_factory(clinic)

    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_reject@test.com")
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # 1. Junior creates Pending Payment
    payload = CreatePaymentRequestSchema(amount=500.0, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id)
    payment, _ = payment_service.create_payment(current_user=junior, session_user=junior, payload=payload)
    assert payment.status == PaymentStatus.PENDING.value

    # 2. Manager Rejects
    rejected_payment, error = payment_service.reject_payment(rejector=manager, payment_id=payment.payment_id)

    # 3. Assertions
    assert error is None
    assert rejected_payment.status == PaymentStatus.REJECTED.value
    assert rejected_payment.approved_by == manager.user_id  # The "Who" in the audit trail

    # Verify NO Financial Impact
    db_session.refresh(cashbox)
    assert float(cashbox.current_amount) == 0.0

    db_session.refresh(plan)
    assert plan.installments[0].amount_paid == 0.0
