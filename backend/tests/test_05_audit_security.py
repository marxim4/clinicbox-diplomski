import pytest
from app.services.audit_log_service import audit_log_service
from app.enums import AuditAction


def test_audit_log_creation_and_hashing(db_session, clinic_factory, user_factory):
    """
    Verifies the cryptographic chaining integrity. Ensures that each new log entry
    correctly incorporates the hash of the preceding entry, forming an immutable chain.
    """
    clinic = clinic_factory()
    user = user_factory(clinic)

    # 1. Create First Log Entry
    log1, error = audit_log_service.log(
        current_user=user,
        action=AuditAction.CREATE,
        entity_name="test_entity",
        entity_id=1,
        after_data={"foo": "bar"}
    )
    assert error is None
    db_session.commit()

    assert log1.curr_hash is not None
    assert log1.prev_hash is None

    # 2. Create Second Log Entry
    log2, error = audit_log_service.log(
        current_user=user,
        action=AuditAction.UPDATE,
        entity_name="test_entity",
        entity_id=1,
        before_data={"foo": "bar"},
        after_data={"foo": "baz"}
    )
    assert error is None
    db_session.commit()

    # 3. Security Verification: Chain Continuity
    assert log2.prev_hash == log1.curr_hash

    # 4. Verify Hash Computation Algorithm
    recomputed = audit_log_service._compute_hash(
        prev_hash=log2.prev_hash,
        clinic_id=log2.clinic_id,
        user_id=log2.user_id,
        action=log2.action,
        entity_name=log2.entity_name,
        entity_id=log2.entity_id,
        before_data=log2.before_data,
        after_data=log2.after_data,
        ip_address=log2.ip_address,
        device_info=log2.device_info,
        created_at_iso=log2.created_at.isoformat()
    )

    assert recomputed == log2.curr_hash


def test_tamper_evidence(db_session, clinic_factory, user_factory):
    """
    Verifies the tamper-detection capability. Simulates a direct database manipulation
    attack and asserts that the verification algorithm identifies the compromise.
    """
    clinic = clinic_factory()
    user = user_factory(clinic)

    # 1. Create a legitimate log
    log, error = audit_log_service.log(
        current_user=user,
        action=AuditAction.CREATE,
        entity_name="sensitive_data",
        entity_id=99,
        after_data={"amount": 1000}
    )
    assert error is None
    db_session.commit()

    original_hash = log.curr_hash

    # 2. Simulate Attack: Malicious actor changes data in DB directly
    log.after_data = {"amount": 500000}
    db_session.commit()

    # 3. Verify: System detects the discrepancy
    recomputed = audit_log_service._compute_hash(
        prev_hash=log.prev_hash,
        clinic_id=log.clinic_id,
        user_id=log.user_id,
        action=log.action,
        entity_name=log.entity_name,
        entity_id=log.entity_id,
        before_data=log.before_data,
        after_data=log.after_data,
        ip_address=log.ip_address,
        device_info=log.device_info,
        created_at_iso=log.created_at.isoformat()
    )

    assert recomputed != original_hash
