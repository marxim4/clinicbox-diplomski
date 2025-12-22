import pytest
from pydantic import ValidationError
from app.schemas.auth import RegisterOwnerSchema, LoginSchema, ChangePasswordSchema
from app.enums import UserRole

# --- 1. Password Regex Testing ---

# Rule: At least 8 chars, 1 Upper, 1 Digit, 1 Special
VALID_PASSWORDS = [
    "StrongP@ss1",
    "Another#1",
    "VeryLongPassword1!",
    "Simple1@",
    "Test@1234"
]

INVALID_PASSWORDS = [
    ("short1!", "too short"),  # < 8 chars
    ("nodigits!", "missing digit"),  # No digit
    ("NoSpecial1", "missing special"),  # No special char
    ("alllowercase1!", "missing upper"),  # No uppercase
    ("ALLUPPER1!", "missing lower"),
    # No lowercase (Actually your regex requires Upper, Digit, Special. It usually implies lower but strict regex might allow ALL CAPS if it has special+digit. Your regex `(?=.*[A-Z])` checks upper. It doesn't strictly check for lower, but let's test what fails.)
    ("12345678", "only digits"),
]


@pytest.mark.parametrize("password", VALID_PASSWORDS)
def test_password_regex_valid(password):
    """Ensure valid passwords pass validation."""
    # We construct a partial schema to test just the password field logic
    # or instantiate the full schema with dummy data.
    schema = RegisterOwnerSchema(
        owner_name="Test",
        email="test@test.com",
        password=password,
        confirm_password=password,  # Must match to pass that check too
        owner_role=UserRole.OWNER,
        clinic_name="Clinic"
    )
    assert schema.password == password


@pytest.mark.parametrize("password, reason", INVALID_PASSWORDS)
def test_password_regex_invalid(password, reason):
    """Ensure weak passwords fail validation."""
    with pytest.raises(ValidationError) as exc:
        RegisterOwnerSchema(
            owner_name="Test",
            email="test@test.com",
            password=password,
            confirm_password=password,
            owner_role=UserRole.OWNER,
            clinic_name="Clinic"
        )
    # Check that the error message relates to password complexity
    assert "Password must be at least 8 characters" in str(exc.value)


# --- 2. Matching Passwords Logic ---

def test_register_password_mismatch():
    """Fail if password and confirm_password do not match."""
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
    """Fail if new_password and confirm_new_password do not match."""
    with pytest.raises(ValidationError) as exc:
        ChangePasswordSchema(
            current_password="OldPassword1!",
            new_password="NewPassword1!",
            confirm_new_password="NewPassword1!_TYPO"
        )
    assert "New passwords do not match" in str(exc.value)


# --- 3. Field Trimming & Normalization ---

def test_email_normalization():
    """Email should be lowercased and trimmed."""
    schema = LoginSchema(
        email="  Test@Test.COM  ",
        password="Password1!"
    )
    assert schema.email == "test@test.com"


def test_empty_strings_rejected():
    """Name and Clinic Name cannot be empty strings or just whitespace."""
    with pytest.raises(ValidationError):
        RegisterOwnerSchema(
            owner_name="   ",  # Empty after strip
            email="test@test.com",
            password="Valid1@Password",
            confirm_password="Valid1@Password",
            owner_role=UserRole.OWNER,
            clinic_name="Clinic"
        )

    with pytest.raises(ValidationError):
        RegisterOwnerSchema(
            owner_name="Valid Name",
            email="test@test.com",
            password="Valid1@Password",
            confirm_password="Valid1@Password",
            owner_role=UserRole.OWNER,
            clinic_name="   "  # Empty clinic name
        )
