import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from app.models import Payment
from app.enums import UserRole, PaymentMethod
from app.services.payment_service import payment_service
from app.schemas.payments import CreatePaymentRequestSchema


def unique_email(prefix):
    """Helper to generate unique emails to avoid constraint collisions."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}@test.com"


def test_delete_patient_blocked_by_financials(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                              cashbox_factory):
    """
    Verifies Referential Integrity.

    Ensures that the database strictly blocks the deletion of a Patient record
    if active financial records (Installment Plans) exist. This prevents
    orphaned financial data and ensures audit trails remain linked to a subject.
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

    # 2. Make Payment (Anchoring the financial data)
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

    # 3. Attempt to DELETE the Patient
    db_session.delete(patient)

    # 4. Assert Database Rejection
    try:
        db_session.commit()
        pytest.fail("Database constraint failed: Allowed deletion of patient with active financials.")
    except IntegrityError:
        db_session.rollback()
        # Pass: The Foreign Key constraint correctly blocked the deletion.


def test_plan_restructuring_scenario(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                     cashbox_factory):
    """
    Verifies Financial Persistence (Anti-Cascade).

    Simulates a 'Plan Restructuring' scenario where an old plan is deleted to be
    replaced by a new one. Crucially, asserts that the PAYMENTS made towards the
    old plan are NOT deleted (Cascade Disable). They must remain in the database,
    unlinked (orphaned), to preserve the accuracy of the cashbook.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER, email=unique_email("man_refinance"))
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email=unique_email("doc_refinance"))
    patient = patient_factory(clinic, doctor)

    cashbox = cashbox_factory(clinic)
    cashbox.is_default = True
    db_session.commit()

    # Step 1: Create Plan A (€1000)
    plan_a = plan_factory(clinic, patient, doctor, total_amount=1000.0)

    # Step 2: Pay €500 towards Plan A
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

    # Capture ID for verification
    payment_id = plan_a.payments[0].payment_id

    # Step 3: Delete Plan A (Simulating a restructuring/cancellation)
    db_session.delete(plan_a)
    db_session.commit()

    # Step 4: Verify Payment Survival
    surviving_payment = db_session.get(Payment, payment_id)

    assert surviving_payment is not None, "Financial Record Loss: Deleting the plan destroyed the payment record."
    assert surviving_payment.plan_id is None, "Payment should be unlinked (NULL) from the deleted plan."
    assert float(surviving_payment.amount) == 500.0
