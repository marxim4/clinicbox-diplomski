import pytest
from pydantic import ValidationError
from app.schemas.auth import RegisterOwnerSchema, LoginSchema, ChangePasswordSchema
from app.enums import UserRole

# Define Password Complexity Rules for Testing
# Policy: Minimum 8 characters, requiring Uppercase, Digit, and Special Character.
VALID_PASSWORDS = [
    "StrongP@ss1",
    "Another#1",
    "VeryLongPassword1!",
    "Simple1@",
    "Test@1234"
]

INVALID_PASSWORDS = [
    ("short1!", "too short"),
    ("nodigits!", "missing digit"),
    ("NoSpecial1", "missing special character"),
    ("alllowercase1!", "missing uppercase"),
    ("12345678", "only digits"),
]


@pytest.mark.parametrize("password", VALID_PASSWORDS)
def test_password_regex_valid(password):
    """
    Verifies that passwords meeting the complexity policy pass validation.
    """
    schema = RegisterOwnerSchema(
        owner_name="Test",
        email="test@test.com",
        password=password,
        confirm_password=password,
        owner_role=UserRole.OWNER,
        clinic_name="Clinic"
    )
    assert schema.password == password


@pytest.mark.parametrize("password, reason", INVALID_PASSWORDS)
def test_password_regex_invalid(password, reason):
    """
    Verifies that weak passwords are rejected with specific error messages.
    """
    with pytest.raises(ValidationError) as exc:
        RegisterOwnerSchema(
            owner_name="Test",
            email="test@test.com",
            password=password,
            confirm_password=password,
            owner_role=UserRole.OWNER,
            clinic_name="Clinic"
        )

    # Assert validation error relates to password constraints
    assert "Password must be at least 8 characters" in str(exc.value)


def test_register_password_mismatch():
    """
    Verifies integrity check: Registration fails if 'password' and 'confirm_password' diverge.
    """
    with pytest.raises(ValidationError) as exc:
        RegisterOwnerSchema(
            owner_name="Test",
            email="test@test.com",
            password="Valid1@Password",
            confirm_password="Valid1@Password_TYPO",
            owner_role=UserRole.OWNER,
            clinic_name="Clinic"
        )
    assert "Passwords do not match" in str(exc.value)


def test_change_password_mismatch():
    """
    Verifies integrity check: Password change fails if confirmation field does not match.
    """
    with pytest.raises(ValidationError) as exc:
        ChangePasswordSchema(
            current_password="OldPassword1!",
            new_password="NewPassword1!",
            confirm_new_password="NewPassword1!_TYPO"
        )
    assert "New passwords do not match" in str(exc.value)


def test_email_normalization():
    """
    Verifies data sanitization: Emails should be trimmed and lowercased automatically.
    """
    schema = LoginSchema(
        email="  Test@Test.COM  ",
        password="Password1!"
    )
    assert schema.email == "test@test.com"


def test_empty_strings_rejected():
    """
    Verifies that required string fields cannot contain only whitespace.
    """
    # Case 1: Empty Name
    with pytest.raises(ValidationError):
        RegisterOwnerSchema(
            owner_name="   ",
            email="test@test.com",
            password="Valid1@Password",
            confirm_password="Valid1@Password",
            owner_role=UserRole.OWNER,
            clinic_name="Clinic"
        )

    # Case 2: Empty Clinic Name
    with pytest.raises(ValidationError):
        RegisterOwnerSchema(
            owner_name="Valid Name",
            email="test@test.com",
            password="Valid1@Password",
            confirm_password="Valid1@Password",
            owner_role=UserRole.OWNER,
            clinic_name="   "
        )
