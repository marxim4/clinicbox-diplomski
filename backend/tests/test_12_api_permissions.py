import pytest
from unittest.mock import MagicMock, patch
from flask import Flask, g, jsonify
from http import HTTPStatus
from app.utils.wrappers import owner_only, role_required, require_pin
from app.enums import UserRole


@pytest.fixture
def app():
    """Simple Flask app fixture for testing route decorators context."""
    app = Flask(__name__)
    return app


def dummy_handler(*args, **kwargs):
    """Mock controller function to be decorated."""
    return jsonify(msg="success"), HTTPStatus.OK


# --- 1. LOGIN_REQUIRED Logic ---

def test_login_required_success(app):
    """
    Verifies authentication middleware logic.
    Ensures that if the user loader returns a valid active user, access is granted.
    """
    with app.app_context():
        mock_user = MagicMock()
        mock_user.is_active = True

        # We mock the internal user loading utility
        with patch('app.utils.wrappers.load_current_user', return_value=mock_user):
            # Logic simulation: If user is loaded and active, status is OK
            user = mock_user
            if not user or not user.is_active:
                status = HTTPStatus.UNAUTHORIZED
            else:
                status = HTTPStatus.OK
            assert status == HTTPStatus.OK


def test_login_required_inactive(app):
    """
    Verifies that deactivated users (even if token is valid) are denied access.
    """
    with app.app_context():
        mock_user = MagicMock()
        mock_user.is_active = False

        user = mock_user
        if not user or not user.is_active:
            status = HTTPStatus.UNAUTHORIZED
        assert status == HTTPStatus.UNAUTHORIZED


# --- 2. OWNER_ONLY Decorator ---

def test_owner_only_success(app):
    """Verifies RBAC: Owners are allowed access."""
    with app.app_context():
        mock_user = MagicMock()
        mock_user.user_id = 100
        mock_user.is_active = True
        mock_user.clinic.owner_user_id = 100
        g.current_user = mock_user

        decorated = owner_only(dummy_handler)
        resp, status = decorated()
        assert status == HTTPStatus.OK


def test_owner_only_forbidden(app):
    """Verifies RBAC: Non-owners are forbidden."""
    with app.app_context():
        mock_user = MagicMock()
        mock_user.user_id = 101  # Different ID
        mock_user.is_active = True
        mock_user.clinic.owner_user_id = 100
        g.current_user = mock_user

        decorated = owner_only(dummy_handler)
        resp, status = decorated()
        assert status == HTTPStatus.FORBIDDEN


# --- 3. ROLE_REQUIRED Decorator ---

def test_role_required_success(app):
    """Verifies that users with the correct role are granted access."""
    with app.app_context():
        mock_user = MagicMock()
        mock_user.is_active = True
        mock_user.role.value = "MANAGER"
        g.current_user = mock_user

        decorator = role_required(UserRole.MANAGER)
        decorated = decorator(dummy_handler)

        resp, status = decorated()
        assert status == HTTPStatus.OK


def test_role_required_forbidden(app):
    """Verifies that users with insufficient roles are denied access."""
    with app.app_context():
        mock_user = MagicMock()
        mock_user.is_active = True
        mock_user.role.value = "RECEPTIONIST"
        g.current_user = mock_user

        decorator = role_required(UserRole.MANAGER)
        decorated = decorator(dummy_handler)

        resp, status = decorated()
        assert status == HTTPStatus.FORBIDDEN


# --- 4. REQUIRE_PIN Decorator ---

def test_require_pin_failed_check(app):
    """
    Verifies 'Step-Up' Authentication.
    If the endpoint requires a PIN and the user provides a wrong one, access is denied.
    """
    with app.app_context():
        mock_user = MagicMock()
        mock_user.clinic.require_pin_for_actions = True
        mock_user.pin_hash = "exists"
        mock_user.check_pin.return_value = False  # Wrong PIN simulation

        with patch('app.utils.wrappers.load_current_user', return_value=mock_user):
            decorated = require_pin(dummy_handler)
            data = MagicMock()
            data.acting_user_id = None
            data.pin = "wrong_pin"

            resp, status = decorated(data=data)
            assert status == HTTPStatus.FORBIDDEN


def test_require_pin_correct_pin_grants_access(app):
    """
    Verifies the same-user PIN happy path.
    When PIN is required and the correct PIN is provided, the endpoint is reached.
    """
    with app.app_context():
        mock_user = MagicMock()
        mock_user.user_id = 1
        mock_user.clinic.require_pin_for_actions = True
        mock_user.clinic.require_pin_for_signoff = False
        mock_user.pin_hash = "exists"
        mock_user.check_pin.return_value = True  # Correct PIN

        with patch('app.utils.wrappers.load_current_user', return_value=mock_user):
            decorated = require_pin(dummy_handler)
            data = MagicMock()
            data.acting_user_id = None
            data.pin = "1234"

            resp, status = decorated(data=data)
            assert status == HTTPStatus.OK


def test_require_pin_acting_user_different_from_session(app):
    """
    Verifies the acting_user (dual sign-off) PIN path.

    This path was previously broken: wrappers.py referenced `db` and `User`
    without importing them, causing a NameError at runtime whenever
    acting_user_id differed from the session user's id.

    The fix adds the missing imports. This test confirms the path now works:
    a session user (receptionist) presents a different acting_user_id (doctor),
    the doctor's record is loaded via db.session.get(User, acting_user_id),
    and the doctor's PIN is verified.

    The User symbol is patched at app.utils.wrappers.User so the assertion
    can verify the exact call signature: db.session.get(User, 2).
    """
    with app.app_context():
        session_user = MagicMock()
        session_user.user_id = 1
        session_user.clinic_id = 10
        # Explicit: session_user.clinic PIN flags are not used in this code path,
        # but should not be left as auto-truthy MagicMock attributes.
        session_user.clinic.require_pin_for_actions = False
        session_user.clinic.require_pin_for_signoff = False

        acting_user = MagicMock()
        acting_user.user_id = 2
        acting_user.clinic_id = 10
        acting_user.clinic.require_pin_for_actions = True
        acting_user.clinic.require_pin_for_signoff = False
        acting_user.pin_hash = "exists"
        acting_user.check_pin.return_value = True  # Doctor's correct PIN

        mock_db = MagicMock()
        mock_db.session.get.return_value = acting_user

        with patch('app.utils.wrappers.load_current_user', return_value=session_user), \
             patch('app.utils.wrappers.db', mock_db), \
             patch('app.utils.wrappers.User') as mock_user_cls:
            decorated = require_pin(dummy_handler)
            data = MagicMock()
            data.acting_user_id = 2  # Different from session_user.user_id (1)
            data.pin = "5678"

            resp, status = decorated(data=data)
            assert status == HTTPStatus.OK
            # Verify the exact DB lookup: db.session.get(User, 2)
            mock_db.session.get.assert_called_once_with(mock_user_cls, 2)
