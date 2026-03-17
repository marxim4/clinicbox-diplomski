#!/usr/bin/env python
"""
ClinicBox dev/demo seed.

Usage:
    python seed.py

Seeds two demo clinics into the existing migrated database.
If the seed marker already exists (owner@dental.test), the script
exits cleanly without touching the database.

To reset and reseed from scratch:
    1. Recreate the DB schema manually, e.g.:
           flask db downgrade base
           flask db upgrade
       or for a full PostgreSQL drop:
           psql -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
           flask db upgrade
    2. Then run: python seed.py
"""

import sys
from datetime import date, timedelta

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.enums import UserRole, ClinicType, PaymentMethod, CashTransactionType
from app.models import User, Clinic, Cashbox, Category, Patient, Installment
from app.data_layer.user_repository import user_repo
from app.data_layer.patient_repository import patient_repo
from app.services.installment_service import installment_service
from app.services.payment_service import payment_service
from app.services.cash_service import cash_service
from app.schemas.installments import (
    CreateInstallmentPlanRequestSchema,
    InstallmentItemInputSchema,
)
from app.schemas.payments import CreatePaymentRequestSchema
from app.schemas.cash import CreateCashTransactionRequestSchema


# ---------------------------------------------------------------------------
# Demo credentials
# Centralised here so the printed summary always matches what was inserted.
# ---------------------------------------------------------------------------

DEMO_PASSWORD = "Admin1234!"

# Clinic A — Dental Studio Beograd
CLINIC_A_META = {
    "name":     "Dental Studio Beograd",
    "timezone": "Europe/Belgrade",
    "currency": "EUR",
    "type":     "DENTAL",
}

A_OWNER    = {"email": "owner@dental.test",      "name": "Dr. Marko Petrović",  "pin": "1111"}
A_MANAGER  = {"email": "manager@dental.test",    "name": "Ana Nikolić",          "pin": "2222"}
A_DOCTOR1  = {"email": "dr.petar@dental.test",   "name": "Dr. Petar Jović",      "pin": "3333"}
A_DOCTOR2  = {"email": "dr.jovana@dental.test",  "name": "Dr. Jovana Stanić",    "pin": "4444"}
A_RECEPT   = {"email": "reception@dental.test",  "name": "Milica Savić",         "pin": "5555"}
A_INACTIVE = {"email": "old.staff@dental.test",  "name": "Stari Radnik",         "pin": None}

# Clinic B — City Health
CLINIC_B_META = {
    "name":     "City Health",
    "timezone": "UTC",
    "currency": "USD",
    "type":     "GENERAL_MEDICINE",
}

B_OWNER  = {"email": "owner@cityhealth.test",   "name": "Dr. James Smith",  "pin": "1111"}
B_DOCTOR = {"email": "dr.jones@cityhealth.test", "name": "Dr. Sarah Jones", "pin": "2222"}
B_RECEPT = {"email": "front@cityhealth.test",   "name": "Tom Evans",        "pin": "3333"}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _create_clinic(name: str, timezone: str, currency: str, type: str) -> Clinic:
    """
    Create a Clinic that reflects the MVP operating model:
    - payments require approval
    - cash movements do not (simpler opening-float scenario)
    - shared terminal mode + PIN for actions enabled
    """
    clinic = Clinic(
        name=name,
        timezone=timezone,
        currency=currency,
        default_language="en",
        clinic_type=ClinicType[type],
        requires_payment_approval=True,
        requires_cash_approval=False,
        requires_close_approval=False,
        use_shared_terminal_mode=True,
        require_pin_for_actions=True,
        require_pin_for_signoff=False,
    )
    db.session.add(clinic)
    db.session.flush()
    return clinic


def _create_owner(clinic: Clinic, info: dict) -> User:
    """
    Replicates the exact 3-step pattern from auth.py:
      1. Clinic already exists with owner_user_id=None
      2. Create User with clinic_id
      3. Back-fill clinic.owner_user_id
    """
    owner = User(
        clinic_id=clinic.clinic_id,
        name=info["name"],
        email=info["email"],
        role=UserRole.OWNER,
        is_active=True,
        can_approve_financials=True,
        requires_approval_for_actions=False,
    )
    owner.set_password(DEMO_PASSWORD)
    if info["pin"]:
        owner.set_pin(info["pin"])
    db.session.add(owner)
    db.session.flush()
    clinic.owner_user_id = owner.user_id
    db.session.flush()
    return owner


def _create_default_cashbox(clinic: Clinic) -> Cashbox:
    cashbox = Cashbox(
        clinic_id=clinic.clinic_id,
        name="Main Register",
        is_default=True,
        current_amount=0.0,
    )
    db.session.add(cashbox)
    db.session.flush()
    return cashbox


def _create_staff(
    clinic: Clinic,
    info: dict,
    role: UserRole,
    *,
    can_approve: bool = False,
    requires_approval: bool = True,
    is_active: bool = True,
) -> User:
    """
    Create a staff user via user_repo so bcrypt hashing and PIN setup
    are handled correctly. can_approve_financials is not a repo parameter
    so it is set manually after creation.
    """
    user = user_repo.create_user(
        clinic_id=clinic.clinic_id,
        name=info["name"],
        email=info["email"],
        role=role,
        password=DEMO_PASSWORD,
        pin=info["pin"],
        requires_approval_for_actions=requires_approval,
        is_active=is_active,
    )
    if can_approve:
        user.can_approve_financials = True
        db.session.flush()
    return user


def _create_category(clinic: Clinic, name: str) -> Category:
    cat = Category(clinic_id=clinic.clinic_id, name=name)
    db.session.add(cat)
    db.session.flush()
    return cat


def _create_patient(clinic: Clinic, first: str, last: str, doctor_id: int):
    return patient_repo.create_patient(
        clinic_id=clinic.clinic_id,
        first_name=first,
        last_name=last,
        middle_name=None,
        birth_date=None,
        phone=None,
        email=None,
        note=None,
        doctor_id=doctor_id,
    )


def _create_plan(
    actor: User,
    patient_id: int,
    doctor_id: int,
    description: str,
    installments: list,
) -> object:
    """
    Create an installment plan via installment_service so schema validation
    runs (including installment sum == total_amount).

    installments: list of (due_date, amount) tuples, in schedule order.
    """
    total = round(sum(amt for _, amt in installments), 2)
    payload = CreateInstallmentPlanRequestSchema(
        patient_id=patient_id,
        doctor_id=doctor_id,
        description=description,
        total_amount=total,
        installments=[
            InstallmentItemInputSchema(due_date=d, expected_amount=a)
            for d, a in installments
        ],
    )
    plan, err = installment_service.create_plan(actor, payload)
    if err:
        raise RuntimeError(f"create_plan failed: {err}")

    # Query installment IDs directly from the DB ordered by sequence.
    #
    # Do NOT use plan.installments here. _replace_installments() in the repo
    # calls plan.installments.clear() then adds new rows via db.session.add()
    # (bypassing the relationship collection), so plan.installments remains
    # empty in memory even though the rows are flushed to the DB.
    inst_ids = list(db.session.scalars(
        select(Installment.installment_id)
        .where(Installment.plan_id == plan.plan_id)
        .order_by(Installment.sequence)
    ).all())
    if not inst_ids:
        raise RuntimeError(f"create_plan succeeded but no installments found for plan_id={plan.plan_id}")
    return plan, inst_ids


def _pay_installment(actor: User, installment_id: int, amount: float) -> None:
    """
    Pay a specific installment via payment_service (CASH method).

    Status (PAID vs PENDING) is determined at runtime by the service based on:
      - clinic.requires_payment_approval
      - actor.requires_approval_for_actions
    Pass manager/owner as actor for PAID; receptionist for PENDING.

    NOTE: payment_service.create_payment() calls db.session.commit() internally
    on the PAID path (known upstream bug). Each PAID payment is its own commit.
    This means the seed is not fully atomic; a mid-seed crash leaves partial data.
    The idempotency guard will detect this on the next run.
    """
    payload = CreatePaymentRequestSchema(
        installment_id=installment_id,
        amount=amount,
        method=PaymentMethod.CASH,
    )
    _, err = payment_service.create_payment(
        current_user=actor,
        session_user=actor,
        payload=payload,
    )
    if err:
        raise RuntimeError(f"create_payment(inst={installment_id}) failed: {err}")


def _deposit(actor: User, cashbox_id: int, amount: float, note: str) -> None:
    """
    Record a manual cash deposit via cash_service so cashbox.current_amount
    is updated correctly through the standard business path.
    clinic.requires_cash_approval=False + actor.requires_approval_for_actions=False
    ensures the transaction is CONFIRMED immediately.
    """
    payload = CreateCashTransactionRequestSchema(
        cashbox_id=cashbox_id,
        type=CashTransactionType.IN,
        amount=amount,
        note=note,
    )
    _, err = cash_service.create_transaction(actor, actor, payload)
    if err:
        raise RuntimeError(f"deposit failed: {err}")


# ---------------------------------------------------------------------------
# Clinic A
# ---------------------------------------------------------------------------

def _seed_clinic_a() -> None:
    today = date.today()

    # --- Foundation ---
    clinic  = _create_clinic(**CLINIC_A_META)
    owner   = _create_owner(clinic, A_OWNER)
    cashbox = _create_default_cashbox(clinic)

    # --- Staff ---
    manager = _create_staff(clinic, A_MANAGER, UserRole.ACCOUNTANT,
                            can_approve=True, requires_approval=False)
    doctor1 = _create_staff(clinic, A_DOCTOR1, UserRole.DOCTOR)
    doctor2 = _create_staff(clinic, A_DOCTOR2, UserRole.DOCTOR)
    recept  = _create_staff(clinic, A_RECEPT,  UserRole.NURSE)
    _create_staff(clinic, A_INACTIVE, UserRole.NURSE, is_active=False)

    # --- Categories ---
    for name in ("Orthodontics", "Implants", "Consultation", "Prosthetics"):
        _create_category(clinic, name)

    # --- Patients ---
    jovan   = _create_patient(clinic, "Jovan",   "Đorđević",  doctor1.user_id)
    sofija  = _create_patient(clinic, "Sofija",  "Marković",  doctor1.user_id)
    nikola  = _create_patient(clinic, "Nikola",  "Lazović",   doctor2.user_id)
    teodora = _create_patient(clinic, "Teodora", "Ilić",      doctor2.user_id)
    _create_patient(clinic, "Stefan", "Čović", doctor1.user_id)  # no plan

    # --- Opening float (CONFIRMED immediately — owner has no approval requirement) ---
    _deposit(owner, cashbox.cashbox_id, 200.0, "Opening float")

    # -------------------------------------------------------------------
    # Plan 1: Jovan — 3 × €300 — all paid by manager → plan PAID
    # Expected cashbox delta: +€900
    # -------------------------------------------------------------------
    _, plan1_ids = _create_plan(
        actor=owner,
        patient_id=jovan.patient_id,
        doctor_id=doctor1.user_id,
        description="Full orthodontic treatment",
        installments=[
            (today - timedelta(days=90), 300.0),
            (today - timedelta(days=60), 300.0),
            (today - timedelta(days=30), 300.0),
        ],
    )
    for inst_id in plan1_ids:
        _pay_installment(manager, inst_id, 300.0)

    # -------------------------------------------------------------------
    # Plan 2: Sofija — €500 + €700 — first installment paid → PARTIALLY_PAID
    # Expected cashbox delta: +€500
    # -------------------------------------------------------------------
    _, plan2_ids = _create_plan(
        actor=owner,
        patient_id=sofija.patient_id,
        doctor_id=doctor1.user_id,
        description="Implant procedure",
        installments=[
            (today - timedelta(days=15), 500.0),
            (today + timedelta(days=30), 700.0),
        ],
    )
    _pay_installment(manager, plan2_ids[0], 500.0)

    # -------------------------------------------------------------------
    # Plan 3: Nikola — 2 × €400
    #   inst 1: paid by manager (PAID)     → cashbox +€400
    #   inst 2: submitted by receptionist  → PENDING (awaits approval)
    # Expected cashbox delta: +€400
    # Demonstrates the approval workflow without blocking the cashbox.
    # -------------------------------------------------------------------
    _, plan3_ids = _create_plan(
        actor=owner,
        patient_id=nikola.patient_id,
        doctor_id=doctor2.user_id,
        description="Prosthetics course",
        installments=[
            (today - timedelta(days=10), 400.0),
            (today + timedelta(days=20), 400.0),
        ],
    )
    _pay_installment(manager, plan3_ids[0], 400.0)

    # Receptionist creates second payment — PENDING due to clinic + user flags.
    pending_payload = CreatePaymentRequestSchema(
        installment_id=plan3_ids[1],
        amount=400.0,
        method=PaymentMethod.CASH,
    )
    _, err = payment_service.create_payment(
        current_user=recept,
        session_user=recept,
        payload=pending_payload,
    )
    if err:
        raise RuntimeError(f"pending payment (plan3 inst2) failed: {err}")

    # -------------------------------------------------------------------
    # Plan 4: Teodora — 3 × €250, future due dates, no payments → PLANNED
    # -------------------------------------------------------------------
    _create_plan(
        actor=owner,
        patient_id=teodora.patient_id,
        doctor_id=doctor2.user_id,
        description="Consultation and implant plan",
        installments=[
            (today + timedelta(days=30), 250.0),
            (today + timedelta(days=60), 250.0),
            (today + timedelta(days=90), 250.0),
        ],
    )

    # Final cashbox balance:
    #   opening deposit: €200
    #   plan 1 (3 payments): €900
    #   plan 2 (1 payment):  €500
    #   plan 3 (1 payment):  €400
    #   total:              €2000


# ---------------------------------------------------------------------------
# Clinic B
# ---------------------------------------------------------------------------

def _seed_clinic_b() -> None:
    today = date.today()

    clinic  = _create_clinic(**CLINIC_B_META)
    owner   = _create_owner(clinic, B_OWNER)
    cashbox = _create_default_cashbox(clinic)

    doctor = _create_staff(clinic, B_DOCTOR, UserRole.DOCTOR)
    _create_staff(clinic, B_RECEPT, UserRole.NURSE)

    alice = _create_patient(clinic, "Alice", "Williams", doctor.user_id)
    _create_patient(clinic, "Bob", "Davis", doctor.user_id)  # no plan

    # Alice: 2-installment plan, first paid by owner → PARTIALLY_PAID
    _, plan_ids = _create_plan(
        actor=owner,
        patient_id=alice.patient_id,
        doctor_id=doctor.user_id,
        description="General check-up and treatment",
        installments=[
            (today - timedelta(days=15), 300.0),
            (today + timedelta(days=15), 300.0),
        ],
    )
    _pay_installment(owner, plan_ids[0], 300.0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _check_seed_state() -> str:
    """
    Returns one of three states:

      "clean"    — none of the expected seed records exist; safe to proceed
      "complete" — all four markers are present; seed already ran successfully
      "partial"  — some but not all markers exist; likely a mid-run crash

    Markers checked:
      - Clinic A owner email     (first record written in _seed_clinic_a)
      - Clinic B owner email     (first record written in _seed_clinic_b)
      - A known Clinic A patient (written after all Clinic A staff are committed)
      - A known Clinic B patient (written after Clinic B staff are committed)

    Any single marker appearing without all four indicates a partial seed.
    """
    has_owner_a = db.session.scalar(
        select(User).where(User.email == A_OWNER["email"])
    ) is not None

    has_owner_b = db.session.scalar(
        select(User).where(User.email == B_OWNER["email"])
    ) is not None

    has_patient_a = db.session.scalar(
        select(Patient).where(
            Patient.first_name == "Jovan",
            Patient.last_name  == "Đorđević",
        )
    ) is not None

    has_patient_b = db.session.scalar(
        select(Patient).where(
            Patient.first_name == "Alice",
            Patient.last_name  == "Williams",
        )
    ) is not None

    markers = [has_owner_a, has_owner_b, has_patient_a, has_patient_b]

    if all(markers):
        return "complete"
    if any(markers):
        return "partial"
    return "clean"


def _print_summary() -> None:
    sep = "=" * 64
    print()
    print(sep)
    print(" SEED COMPLETE".center(64))
    print(sep)
    print(f"\n  Password (all users): {DEMO_PASSWORD}\n")

    print("  CLINIC A — Dental Studio Beograd  (EUR · Europe/Belgrade)")
    print(f"  {'Role':<16} {'Email':<37} PIN")
    print(f"  {'-'*14:<16} {'-'*35:<37} ----")
    rows_a = [
        ("Owner",         A_OWNER),
        ("Manager",       A_MANAGER),
        ("Doctor 1",      A_DOCTOR1),
        ("Doctor 2",      A_DOCTOR2),
        ("Receptionist",  A_RECEPT),
        ("Inactive staff",A_INACTIVE),
    ]
    for role, info in rows_a:
        pin = info["pin"] if info["pin"] else "(none — inactive)"
        print(f"  {role:<16} {info['email']:<37} {pin}")

    print()
    print("  CLINIC B — City Health  (USD · UTC)")
    print(f"  {'Role':<16} {'Email':<37} PIN")
    print(f"  {'-'*14:<16} {'-'*35:<37} ----")
    rows_b = [
        ("Owner",        B_OWNER),
        ("Doctor",       B_DOCTOR),
        ("Receptionist", B_RECEPT),
    ]
    for role, info in rows_b:
        print(f"  {role:<16} {info['email']:<37} {info['pin']}")

    print()
    print("  Seeded scenarios (Clinic A):")
    print("    Plan 1  Jovan     3 × €300   all paid      → PAID         +€900 cashbox")
    print("    Plan 2  Sofija    €500+€700  1st paid       → PART. PAID  +€500 cashbox")
    print("    Plan 3  Nikola    2 × €400   1 paid / 1 PENDING (receptionist)")
    print("    Plan 4  Teodora   3 × €250   no payments    → PLANNED")
    print("    Stefan  (no plan)")
    print("    Opening float: €200 deposit")
    print("    Expected cashbox balance: €2000")
    print()
    print("  To reset: recreate schema → `flask db upgrade` → `python seed.py`")
    print(sep)
    print()


def seed() -> None:
    app = create_app()
    with app.app_context():
        state = _check_seed_state()

        if state == "complete":
            print("DB is already fully seeded.")
            print("To reset: recreate schema, run `flask db upgrade`, then re-run seed.")
            sys.exit(0)

        if state == "partial":
            print("ERROR: DB appears partially seeded (some expected records exist, others do not).")
            print("This usually means a previous seed run crashed mid-way.")
            print("Manual cleanup is required before rerunning:")
            print("  1. Recreate the DB schema (e.g. flask db downgrade base && flask db upgrade)")
            print("  2. Then run: python seed.py")
            sys.exit(1)

        print("Seeding Clinic A — Dental Studio Beograd...")
        _seed_clinic_a()

        print("Seeding Clinic B — City Health...")
        _seed_clinic_b()

        # Commit any remaining unflushed data (PENDING payment, Clinic B remainder).
        # PAID payments are already committed by payment_service internally.
        db.session.commit()

        _print_summary()


if __name__ == "__main__":
    seed()
