import pytest
from http import HTTPStatus
from app.models import User, Clinic, Cashbox
from app.enums import UserRole, ClinicType


# --- Helper to generate valid payload ---
def valid_register_payload(email="owner@test.com"):
    return {
        "owner_name": "Dr. Owner",
        "email": email,
        "password": "StrongPassword1!",
        "confirm_password": "StrongPassword1!",
        "owner_role": "OWNER",
        "clinic_name": "Test Clinic",
        "clinic_type": "DENTAL",
        "currency": "EUR",
        "default_language": "en"
    }


def test_register_owner_success(client, db_session):
    """
    Scenario: Happy path registration.
    Checks:
      1. User created?
      2. Clinic created?
      3. User linked to Clinic?
      4. Default Cashbox created?
      5. Tokens returned?
    """
    payload = valid_register_payload()
    resp = client.post("/api/auth/register-owner", json=payload)

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["role"] == "OWNER"

    # DB Verification
    user = db_session.query(User).filter_by(email=payload["email"]).first()
    assert user is not None
    assert user.clinic_id is not None

    clinic = db_session.query(Clinic).get(user.clinic_id)
    assert clinic.name == "Test Clinic"
    assert clinic.owner_user_id == user.user_id
    assert clinic.clinic_type == ClinicType.DENTAL

    # Check Cashbox Creation (Business Logic)
    cashbox = db_session.query(Cashbox).filter_by(clinic_id=clinic.clinic_id).first()
    assert cashbox is not None
    assert cashbox.is_default is True
    assert cashbox.name == "Main Cashbox"


def test_register_duplicate_email(client, db_session):
    """Scenario: Registering the same email twice should fail."""
    payload = valid_register_payload("dup@test.com")

    # 1. First Register -> OK
    resp1 = client.post("/api/auth/register-owner", json=payload)
    assert resp1.status_code == HTTPStatus.CREATED

    # 2. Second Register -> Conflict
    resp2 = client.post("/api/auth/register-owner", json=payload)
    assert resp2.status_code == HTTPStatus.CONFLICT
    assert "already in use" in resp2.json["msg"]


def test_login_flow(client, db_session, user_factory, clinic_factory):
    """
    Scenario: Login with valid and invalid credentials.
    """
    # Setup existing user
    clinic = clinic_factory()
    password = "MyLoginPass1!"

    # FIX: Create user first, then set password manually
    user = user_factory(clinic, email="login@test.com")
    user.set_password(password)
    db_session.commit()

    # 1. Valid Login
    resp = client.post("/api/auth/login", json={
        "email": "login@test.com",
        "password": password
    })
    assert resp.status_code == HTTPStatus.OK
    assert "access_token" in resp.json

    # 2. Invalid Password
    resp = client.post("/api/auth/login", json={
        "email": "login@test.com",
        "password": "WrongPassword1!"
    })
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    # 3. Non-existent Email
    resp = client.post("/api/auth/login", json={
        "email": "ghost@test.com",
        "password": password
    })
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_login_inactive_user_rejected(client, db_session, user_factory, clinic_factory):
    """Scenario: Banned/Inactive users cannot log in."""
    clinic = clinic_factory()
    user = user_factory(clinic, email="banned@test.com")

    # Set known password
    user.set_password("Password123!")
    user.is_active = False  # BAN HAMMER
    db_session.commit()

    resp = client.post("/api/auth/login", json={
        "email": "banned@test.com",
        "password": "Password123!"
    })
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_change_password_flow(client, db_session, user_factory, clinic_factory):
    """
    Scenario: Change password requires valid current password.
    """
    clinic = clinic_factory()
    old_pass = "OldPass1!"
    new_pass = "NewPass1!"

    # FIX: Create user first, then set password manually
    user = user_factory(clinic, email="changer@test.com")
    user.set_password(old_pass)
    db_session.commit()

    # Login to get token
    login_resp = client.post("/api/auth/login", json={
        "email": "changer@test.com",
        "password": old_pass
    })
    access_token = login_resp.json["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Try with WRONG current password
    resp = client.post("/api/auth/change-password", headers=headers, json={
        "current_password": "WrongCurrent1!",
        "new_password": new_pass,
        "confirm_new_password": new_pass
    })
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    # 2. Try with VALID current password
    resp = client.post("/api/auth/change-password", headers=headers, json={
        "current_password": old_pass,
        "new_password": new_pass,
        "confirm_new_password": new_pass
    })
    assert resp.status_code == HTTPStatus.OK

    # 3. Verify old password no longer works
    login_retry = client.post("/api/auth/login", json={
        "email": "changer@test.com",
        "password": old_pass
    })
    assert login_retry.status_code == HTTPStatus.UNAUTHORIZED

    # 4. Verify new password works
    login_new = client.post("/api/auth/login", json={
        "email": "changer@test.com",
        "password": new_pass
    })
    assert login_new.status_code == HTTPStatus.OK