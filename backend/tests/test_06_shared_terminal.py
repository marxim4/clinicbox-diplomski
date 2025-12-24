import pytest
from app.enums import UserRole, PaymentMethod
from app.services.payment_service import payment_service
from app.schemas.payments import CreatePaymentRequestSchema
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import CashTransaction


def test_pin_verification_logic(db_session, clinic_factory, user_factory):
    """
    Verifies the security of the PIN hashing mechanism using standard cryptographic libraries.
    """
    clinic = clinic_factory()
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doc_pin@test.com")

    # 1. Manually set a PIN hash
    pin_code = "1234"
    doctor.pin_hash = generate_password_hash(pin_code)
    db_session.commit()

    # 2. Verify Correct PIN
    assert check_password_hash(doctor.pin_hash, "1234") is True

    # 3. Verify Wrong PIN
    assert check_password_hash(doctor.pin_hash, "0000") is False


def test_shared_terminal_attribution(db_session, clinic_factory, user_factory, cashbox_factory, patient_factory,
                                     plan_factory):
    """
    Verifies the audit trail fidelity in a Shared Terminal environment.
    Ensures that transactions correctly distinguish between:
    - Session User: The receptionist logged into the device.
    - Acting User: The doctor authorizing the specific action via PIN.
    """
    clinic = clinic_factory()

    # Arrange: Allow instant payments to generate immediate transaction records
    clinic.requires_payment_approval = False
    db_session.commit()

    receptionist = user_factory(clinic, role=UserRole.RECEPTIONIST, email="reception@test.com")
    doctor = user_factory(clinic, role=UserRole.DOCTOR, email="doctor_pin@test.com")

    cashbox = cashbox_factory(clinic)
    patient = patient_factory(clinic, doctor)
    plan = plan_factory(clinic, patient, doctor, total_amount=100.0)

    # Act: Receptionist is logged in, but Doctor authorizes the payment
    payload = CreatePaymentRequestSchema(
        amount=100.0,
        plan_id=plan.plan_id,
        cashbox_id=cashbox.cashbox_id,
        method=PaymentMethod.CASH
    )

    payment, error = payment_service.create_payment(
        current_user=doctor,  # Acting User (PIN verified)
        session_user=receptionist,  # Session User (Logged in)
        payload=payload
    )

    assert error is None

    # Assert 1: Payment Record Attribution
    assert payment.created_by == doctor.user_id
    assert payment.session_user_id == receptionist.user_id

    # Assert 2: Financial Transaction Attribution
    tx = db_session.query(CashTransaction).filter_by(payment_id=payment.payment_id).first()
    assert tx is not None
    assert tx.created_by == doctor.user_id
    assert tx.session_user_id == receptionist.user_id
