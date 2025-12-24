import pytest
from http import HTTPStatus
from app.models import User, Clinic
from app.enums import UserRole


def valid_register_payload(email="owner@test.com"):
    """Helper to generate a compliant registration payload."""
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
    Verifies the standard Owner Registration workflow.
    Ensures that a User, a Clinic, and an initial JWT are created successfully.
    """
    payload = valid_register_payload()
    resp = client.post("/api/auth/register-owner", json=payload)

    assert resp.status_code == HTTPStatus.CREATED
    data = resp.json
    assert "access_token" in data
    assert data["role"] == "OWNER"

    # Verify Database Persistence
    user = db_session.query(User).filter_by(email=payload["email"]).first()
    assert user is not None
    clinic = db_session.query(Clinic).get(user.clinic_id)
    assert clinic.name == "Test Clinic"


def test_register_duplicate_email(client, db_session):
    """
    Verifies uniqueness constraints: Registration should fail if the email exists.
    """
    payload = valid_register_payload("dup@test.com")

    # 1. First Registration (Success)
    client.post("/api/auth/register-owner", json=payload)

    # 2. Second Registration (Failure)
    resp2 = client.post("/api/auth/register-owner", json=payload)
    assert resp2.status_code == HTTPStatus.CONFLICT


def test_login_flow(client, db_session):
    """
    Verifies authentication logic for valid and invalid credentials.
    """
    email = "login_flow@test.com"
    password = "StrongPassword1!"
    payload = valid_register_payload(email)
    payload["password"] = password
    payload["confirm_password"] = password
    client.post("/api/auth/register-owner", json=payload)

    # 1. Valid Credentials
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == HTTPStatus.OK
    assert "access_token" in resp.json

    # 2. Invalid Credentials
    resp = client.post("/api/auth/login", json={"email": email, "password": "Wrong!"})
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


def test_login_inactive_user_rejected(client, db_session):
    """
    Verifies Account Suspension logic.
    A user marked `is_active=False` must be denied access even with valid credentials.
    """
    email = "banned@test.com"
    payload = valid_register_payload(email)
    client.post("/api/auth/register-owner", json=payload)

    # Simulate Administrative Ban
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
    Verifies the JWT Versioning Security Mechanism.

    Scenario:
    1. User changes password.
    2. The system increments the user's `token_version`.
    3. Old tokens (signed with the previous version) must be immediately invalidated.
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

    # 3. Attempt Change with WRONG current password (Should Fail)
    resp = client.post("/api/auth/change-password", headers=headers_a, json={
        "current_password": "Wrong!",
        "new_password": new_pass,
        "confirm_new_password": new_pass
    })
    assert resp.status_code == HTTPStatus.UNAUTHORIZED

    # 4. Change Password with VALID current password (Success)
    # Side Effect: User DB `token_version` increments from 1 -> 2
    resp = client.post("/api/auth/change-password", headers=headers_a, json={
        "current_password": old_pass,
        "new_password": new_pass,
        "confirm_new_password": new_pass
    })
    assert resp.status_code == HTTPStatus.OK

    # 5. SECURITY CHECK: Reuse Token A (Version 1)
    # Expected: Rejection (401 or 422) because Token Version (1) < User Version (2)
    retry_resp = client.post("/api/auth/change-password", headers=headers_a, json={
        "current_password": new_pass,
        "new_password": "NewestPassword!",
        "confirm_new_password": "NewestPassword!"
    })

    assert retry_resp.status_code in [HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_ENTITY]

    # 6. Verify Login with NEW password yields valid Token B (Version 2)
    login_new = client.post("/api/auth/login", json={"email": email, "password": new_pass})
    assert login_new.status_code == HTTPStatus.OK
    token_b = login_new.json["access_token"]

    # 7. Verify Token B is functional
    headers_b = {"Authorization": f"Bearer {token_b}"}
    valid_resp = client.post("/api/auth/change-password", headers=headers_b, json={
        "current_password": new_pass,
        "new_password": old_pass,
        "confirm_new_password": old_pass
    })
    assert valid_resp.status_code == HTTPStatus.OK
