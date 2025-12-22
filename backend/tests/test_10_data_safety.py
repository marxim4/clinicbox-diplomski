import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from app.models import Patient, Payment
from app.enums import UserRole, PaymentMethod, PlanStatus
from app.services.payment_service import payment_service
from app.schemas.payments import CreatePaymentRequestSchema


def unique_email(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}@test.com"


def test_delete_patient_blocked_by_financials(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                              cashbox_factory):
    """
    Safety Rule #1: You CANNOT delete a patient who has active plans.
    This works because InstallmentPlan.patient_id is NOT NULL.
    """
    clinic = clinic_factory()
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email=unique_email("doc"))
    manager = user_factory(clinic, role=UserRole.MANAGER, email=unique_email("manager"))

    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    # 1. Create Patient & Plan
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    # 2. Make Payment
    payment_payload = CreatePaymentRequestSchema(
        plan_id=plan.plan_id,
        amount=50.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    payment_service.create_payment(
        current_user=manager,
        session_user=manager,
        payload=payment_payload
    )

    # 3. Try to DELETE
    db_session.delete(patient)

    # 4. Assert Database BLOCKS it
    try:
        db_session.commit()
        pytest.fail("DANGER: System allowed deleting a patient with financial records!")
    except IntegrityError:
        db_session.rollback()
        # Pass: The database blocked the delete (InstallmentPlan requires patient_id).


def test_plan_restructuring_scenario(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                     cashbox_factory):
    """
    Scenario: 'Refinancing' a Plan.
    Verifies that deleting a plan DOES NOT delete its payments (Data Safety).
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email=unique_email("man_refinance"))
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email=unique_email("doc_refinance"))
    patient = patient_factory(clinic, doctor)

    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    # --- STEP 1: Old Plan A (€1000) ---
    plan_a = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Pay €500 towards Plan A
    pay_payload = CreatePaymentRequestSchema(
        plan_id=plan_a.plan_id,
        amount=500.0,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )
    payment_service.create_payment(
        current_user=manager,
        session_user=manager,
        payload=pay_payload
    )

    # Capture the payment ID to check later
    assert len(plan_a.payments) == 1
    payment_id = plan_a.payments[0].payment_id

    # --- STEP 2: Delete Plan A ---
    # Since we removed the cascade, this should NOT delete the payment.
    # It might succeed (setting payment.plan_id = NULL) or fail (if plan_id is not null).
    # Either way, the PAYMENT must survive.

    db_session.delete(plan_a)
    db_session.commit()  # If this passes, it means plan_id is nullable.

    # --- STEP 3: Safety Check ---
    # The payment must still exist in the database (Orphaned but safe)
    #

    surviving_payment = db_session.get(Payment, payment_id)

    assert surviving_payment is not None, "FATAL: Deleting the plan deleted the money! Cascade is still active."
    assert surviving_payment.plan_id is None, "Payment should be unlinked from the deleted plan."
    assert float(surviving_payment.amount) == 500.0
