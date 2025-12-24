from app.models.user import User
from app.enums import UserRole


def test_clinic_creation(db_session, clinic_factory):
    """
    Verifies that a clinic is created with the correct default configuration settings.
    """
    clinic = clinic_factory(name="Dental Pro")

    assert clinic.clinic_id is not None
    assert clinic.name == "Dental Pro"
    # Verify default policy (Payment Approval defaults to True)
    assert clinic.requires_payment_approval is True


def test_user_permissions_logic(db_session, clinic_factory, user_factory):
    """
    Verifies the RBAC constraint logic:
    A user cannot simultaneously 'approve financials' AND 'require approval for actions'.
    These flags are mutually exclusive based on seniority.
    """
    clinic = clinic_factory()

    # Case 1: Manager (Senior)
    # Should be able to approve others, and does not require approval for self.
    manager = user_factory(clinic, role=UserRole.MANAGER, email="boss@clinic.com")
    assert manager.can_approve_financials is True
    assert manager.requires_approval_for_actions is False

    # Case 2: Receptionist (Junior)
    # Should NOT be able to approve others, and requires approval for self.
    junior = user_factory(clinic, role=UserRole.RECEPTIONIST, email="junior@clinic.com")
    assert junior.can_approve_financials is False
    assert junior.requires_approval_for_actions is True
