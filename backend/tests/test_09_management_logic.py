import pytest
from sqlalchemy.exc import IntegrityError
from app.models import User, Clinic, Category
from app.enums import UserRole
from app.services.user_service import user_service
from app.services.clinic_service import clinic_service
from app.services.category_service import category_service


# --- MOCK SCHEMAS FOR TESTING ---
# These mimic the Pydantic schemas expected by your Services
class MockCreateUserSchema:
    def __init__(self, email, name, role, password, pin=None):
        self.email = email
        self.name = name
        self.role = role
        self.password = password
        self.pin = pin


class MockUpdateClinicSettingsSchema:
    def __init__(self, **kwargs):
        self.requires_payment_approval = kwargs.get('requires_payment_approval', False)
        self.requires_cash_approval = kwargs.get('requires_cash_approval', False)
        self.requires_close_approval = kwargs.get('requires_close_approval', False)
        self.use_shared_terminal_mode = kwargs.get('use_shared_terminal_mode', True)
        self.require_pin_for_actions = kwargs.get('require_pin_for_actions', True)
        self.require_pin_for_signoff = kwargs.get('require_pin_for_signoff', True)


class MockCreateCategorySchema:
    def __init__(self, name, is_pinned=False):
        self.name = name
        self.is_pinned = is_pinned


# ------------------------------------------------------------------------------
# TEST 1: User Logic & Constraints
# ------------------------------------------------------------------------------

def test_user_email_uniqueness_via_service(db_session, clinic_factory, user_factory):
    """
    Scenario: Manager tries to create two users with the same email 'nurse@test.com'.
    Expected: Service should return an error for the second attempt.
    """
    clinic = clinic_factory()
    owner = user_factory(clinic, role=UserRole.OWNER)

    # 1. Create First User -> Success
    payload1 = MockCreateUserSchema(
        email="nurse@test.com",
        name="Nurse 1",
        role=UserRole.NURSE,
        password="Pass1",
        pin="1111"
    )
    user1, error1 = user_service.create_clinic_user(owner, payload1)
    assert error1 is None
    assert user1 is not None

    # 2. Create Second User (Same Email) -> Error
    payload2 = MockCreateUserSchema(
        email="nurse@test.com",
        name="Nurse Imposter",
        role=UserRole.NURSE,
        password="Pass2",
        pin="2222"
    )
    user2, error2 = user_service.create_clinic_user(owner, payload2)

    assert user2 is None
    assert error2 == "email already in use for this clinic"


def test_user_permissions_db_constraint(db_session, clinic_factory):
    """
    Scenario: Verify the DB CheckConstraint logic.
    Rule: A user CANNOT be both 'can_approve_financials=True' AND 'requires_approval=True'.
    (You cannot be a boss who needs permission from a boss).
    """
    clinic = clinic_factory()

    # 1. Create a user with invalid contradictory permissions
    # We bypass the service and go straight to DB to test the SQL constraint
    confused_user = User(
        clinic_id=clinic.clinic_id,
        name="Confused Guy",
        email="confused@test.com",
        role=UserRole.MANAGER,
        is_active=True,
        # THE INVALID COMBO:
        can_approve_financials=True,
        requires_approval_for_actions=True
    )
    confused_user.set_password("pass")

    db_session.add(confused_user)

    # 2. Verify Database Rejects It
    # This expects an IntegrityError (CheckConstraint violation)
    try:
        db_session.commit()
        pytest.fail("Database allowed a user to have both permissions set to True!")
    except IntegrityError:
        db_session.rollback()  # Correct behavior


# ------------------------------------------------------------------------------
# TEST 2: Clinic Settings Logic
# ------------------------------------------------------------------------------

def test_update_clinic_settings(db_session, clinic_factory, user_factory):
    """
    Scenario: Owner changes clinic policy to Require Payment Approval.
    """
    clinic = clinic_factory(settings={"requires_payment_approval": False})
    owner = user_factory(clinic, role=UserRole.OWNER)

    assert clinic.requires_payment_approval is False

    # Update Settings
    payload = MockUpdateClinicSettingsSchema(requires_payment_approval=True)

    updated_clinic, error = clinic_service.update_settings(owner, payload)

    assert error is None
    assert updated_clinic.requires_payment_approval is True

    # Check DB persistence
    db_session.refresh(clinic)
    assert clinic.requires_payment_approval is True


# ------------------------------------------------------------------------------
# TEST 3: Category Logic
# ------------------------------------------------------------------------------

def test_category_lifecycle(db_session, clinic_factory, user_factory):
    """
    Scenario: Create categories, list them, and try duplicates.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)

    # 1. Create "Consultations"
    cat1, err1 = category_service.create_category(
        manager, MockCreateCategorySchema(name="Consultations", is_pinned=True)
    )
    assert err1 is None
    assert cat1.name == "Consultations"
    assert cat1.is_pinned is True

    # 2. Create "Supplements"
    cat2, err2 = category_service.create_category(
        manager, MockCreateCategorySchema(name="Supplements")
    )
    assert err2 is None

    # 3. List Categories
    items, err_list = category_service.list_categories(manager)
    assert len(items) == 2
    names = [c.name for c in items]
    assert "Consultations" in names
    assert "Supplements" in names


def test_category_uniqueness(db_session, clinic_factory, user_factory):
    """
    Scenario: Prevent duplicate category names in the same clinic.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)

    # 1. Create "Dentistry"
    category_service.create_category(
        manager, MockCreateCategorySchema(name="Dentistry")
    )

    # 2. Try creating "Dentistry" again -> Should Fail
    dup, error = category_service.create_category(
        manager, MockCreateCategorySchema(name="Dentistry")
    )

    assert dup is None
    assert error == "category with this name already exists in this clinic"

    # 3. Verify DB Constraint (Double Check)
    # If we bypass service, DB should still block it
    try:
        dup_db = Category(clinic_id=clinic.clinic_id, name="Dentistry")
        db_session.add(dup_db)
        db_session.commit()
        pytest.fail("DB Unique Constraint failed for Category Name")
    except IntegrityError:
        db_session.rollback()
