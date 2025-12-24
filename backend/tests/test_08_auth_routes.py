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
    """Happy path registration."""
    payload = valid_register_payload()
    resp = client.post("/api/auth/register-owner", json=payload)

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json
    assert "access_token" in data
    assert data["role"] == "OWNER"

    # DB Verification
    user = db_session.query(User).filter_by(email=payload["email"]).first()
    assert user is not None
    clinic = db_session.query(Clinic).get(user.clinic_id)
    assert clinic.name == "Test Clinic"


def test_register_duplicate_email(client, db_session):
    """Scenario: Registering the same email twice should fail."""
    payload = valid_register_payload("dup@test.com")
    client.post("/api/auth/register-owner", json=payload)
    resp2 = client.post("/api/auth/register-owner", json=payload)
    assert resp2.status_code == HTTPStatus.CONFLICT


def test_login_flow(client, db_session):
    """Scenario: Login with valid and invalid credentials."""
    email = "login_flow@test.com"
    password = "StrongPassword1!"
    payload = valid_register_payload(email)
    payload["password"] = password
    payload["confirm_password"] = password
    client.post("/api/auth/register-owner", json=payload)

    # 1. Valid Login
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == HTTPStatus.OK
    assert "access_token" in resp.json

    # 2. Invalid Password
    resp = client.post("/api/auth/login", json={"email": email, "password": "Wrong!"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_login_inactive_user_rejected(client, db_session):
    """Scenario: Banned/Inactive users cannot log in."""
    email = "banned@test.com"
    payload = valid_register_payload(email)
    client.post("/api/auth/register-owner", json=payload)

    # Manually ban user in DB
    user = db_session.query(User).filter_by(email=email).first()
    user.is_active = False
    db_session.commit()

    resp = client.post("/api/auth/login", json={
        "email": email,
        "password": payload["password"]
    })
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_change_password_and_token_revocation(client, db_session):
    """
    Scenario:
    1. Change password (functionality check).
    2. Ensure OLD token is revoked immediately (security check).
    """
    email = "change_flow@test.com"
    old_pass = "OldPass1!"
    new_pass = "NewPass1!"

    # 1. Register
    payload = valid_register_payload(email)
    payload["password"] = old_pass
    payload["confirm_password"] = old_pass
    client.post("/api/auth/register-owner", json=payload)

    # 2. Login to get Token A (Version 1)
    login_resp = client.post("/api/auth/login", json={"email": email, "password": old_pass})
    token_a = login_resp.json["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 3. Try Change with WRONG current password (Should fail 401)
    resp = client.post("/api/auth/change-password", headers=headers_a, json={
        "current_password": "Wrong!",
        "new_password": new_pass,
        "confirm_new_password": new_pass
    })
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    assert "current password is incorrect" in resp.json["msg"]

    # 4. Change Password with VALID current password (Should succeed)
    # This Action bumps User DB Version 1 -> 2
    resp = client.post("/api/auth/change-password", headers=headers_a, json={
        "current_password": old_pass,
        "new_password": new_pass,
        "confirm_new_password": new_pass
    })
    assert resp.status_code == HTTPStatus.OK

    # 5. SECURITY CHECK: Try to use Token A again
    # It should now be REJECTED because:
    #   Token A has Version 1
    #   User DB has Version 2
    retry_resp = client.post("/api/auth/change-password", headers=headers_a, json={
        "current_password": new_pass,
        "new_password": "NewestPassword!",
        "confirm_new_password": "NewestPassword!"
    })

    # ACCEPT EITHER 401 or 422.
    # Both mean the request was blocked, satisfying the security requirement.
    # 401 = Unauthorized (Logic rejection from our wrapper)
    # 422 = Unprocessable Entity (JWT Library rejection)
    assert retry_resp.status_code in [HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_ENTITY]

    # 6. Verify we can login with the NEW password to get Token B (Version 2)
    login_new = client.post("/api/auth/login", json={"email": email, "password": new_pass})
    assert login_new.status_code == HTTPStatus.OK
    token_b = login_new.json["access_token"]

    # 7. Verify Token B works
    headers_b = {"Authorization": f"Bearer {token_b}"}
    valid_resp = client.post("/api/auth/change-password", headers=headers_b, json={
        "current_password": new_pass,
        "new_password": old_pass,  # Resetting
        "confirm_new_password": old_pass
    })
    assert valid_resp.status_code == HTTPStatus.OK