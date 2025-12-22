from app.models.user import User
from app.enums import UserRole


def test_clinic_creation(db_session, clinic_factory):
    """Test that we can create a clinic and it has default settings."""
    clinic = clinic_factory(name="Dental Pro")

    assert clinic.clinic_id is not None
    assert clinic.name == "Dental Pro"
    assert clinic.requires_payment_approval is True  # Verification of default


def test_user_permissions_logic(db_session, clinic_factory, user_factory):
    """
    Test the critical 'CheckConstraint' you added in User model:
    NOT (can_approve_financials IS TRUE AND requires_approval_for_actions IS TRUE)
    """
    clinic = clinic_factory()

    # Create a Manager (Should have can_approve=True, req_approval=False)
    manager = user_factory(clinic, role=UserRole.MANAGER, email="boss@clinic.com")
    assert manager.can_approve_financials is True
    assert manager.requires_approval_for_actions is False

    # Create a Junior (Should have can_approve=False, req_approval=True)
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior@clinic.com")
    assert junior.can_approve_financials is False
    assert junior.requires_approval_for_actions is True

    # Note: If we try to violate the SQL CheckConstraint, SQLAlchemy should raise an IntegrityError.
    # We will test that later.
