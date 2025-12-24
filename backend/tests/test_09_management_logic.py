import pytest
from sqlalchemy.exc import IntegrityError
from app.models import User, Clinic, Category
from app.enums import UserRole
from app.services.user_service import user_service
from app.services.clinic_service import clinic_service
from app.services.category_service import category_service


# --- Test Doubles (Mocks) ---
# These classes mock the Pydantic schemas required by the Service Layer,
# allowing us to test logic without engaging the HTTP layer.

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


def test_user_email_uniqueness_via_service(db_session, clinic_factory, user_factory):
    """
    Verifies Multi-Tenancy Logic:
    Ensures that the Service Layer enforces email uniqueness within the clinic scope.
    """
    clinic = clinic_factory()
    owner = user_factory(clinic, role=UserRole.OWNER)

    # 1. Create First User (Success)
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

    # 2. Create Second User with same email (Failure)
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
    Verifies Defense-in-Depth (Database Constraints).

    The database must reject a user configuration where:
    (can_approve_financials=True) AND (requires_approval_for_actions=True).
    This logic error (a boss who needs permission) is blocked at the SQL level.
    """
    clinic = clinic_factory()

    # Attempt to bypass service layer and insert invalid data directly
    confused_user = User(
        clinic_id=clinic.clinic_id,
        name="Confused Guy",
        email="confused@test.com",
        role=UserRole.MANAGER,
        is_active=True,
        # Invalid Combination:
        can_approve_financials=True,
        requires_approval_for_actions=True
    )
    confused_user.set_password("pass")

    db_session.add(confused_user)

    # Expecting IntegrityError from SQLAlchemy
    try:
        db_session.commit()
        pytest.fail("Database constraint failed: Invalid permission combination accepted.")
    except IntegrityError:
        db_session.rollback()  # Constraint functioned correctly


def test_update_clinic_settings(db_session, clinic_factory, user_factory):
    """
    Verifies that clinic-wide policy settings can be updated and persisted.
    """
    clinic = clinic_factory(settings={"requires_payment_approval": False})
    owner = user_factory(clinic, role=UserRole.OWNER)

    assert clinic.requires_payment_approval is False

    # Act: Update Settings
    payload = MockUpdateClinicSettingsSchema(requires_payment_approval=True)
    updated_clinic, error = clinic_service.update_settings(owner, payload)

    # Assert
    assert error is None
    assert updated_clinic.requires_payment_approval is True

    # Verify Persistence
    db_session.refresh(clinic)
    assert clinic.requires_payment_approval is True


def test_category_lifecycle(db_session, clinic_factory, user_factory):
    """
    Verifies the CRUD lifecycle of financial categories.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)

    # 1. Create Pinned Category
    cat1, err1 = category_service.create_category(
        manager, MockCreateCategorySchema(name="Consultations", is_pinned=True)
    )
    assert err1 is None
    assert cat1.name == "Consultations"
    assert cat1.is_pinned is True

    # 2. Create Standard Category
    cat2, err2 = category_service.create_category(
        manager, MockCreateCategorySchema(name="Supplements")
    )
    assert err2 is None

    # 3. Verify Listing
    items, err_list = category_service.list_categories(manager)
    assert len(items) == 2
    names = [c.name for c in items]
    assert "Consultations" in names
    assert "Supplements" in names


def test_category_uniqueness(db_session, clinic_factory, user_factory):
    """
    Verifies that the database enforces unique category names per clinic.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)

    # 1. Create Initial Category
    category_service.create_category(
        manager, MockCreateCategorySchema(name="Dentistry")
    )

    # 2. Attempt Duplicate via Service (Should fail gracefully)
    dup, error = category_service.create_category(
        manager, MockCreateCategorySchema(name="Dentistry")
    )

    assert dup is None
    assert error == "category with this name already exists in this clinic"

    # 3. Attempt Duplicate via DB Direct (Should fail with IntegrityError)
    try:
        dup_db = Category(clinic_id=clinic.clinic_id, name="Dentistry")
        db_session.add(dup_db)
        db_session.commit()
        pytest.fail("Database unique constraint failed for Category Name")
    except IntegrityError:
        db_session.rollback()
