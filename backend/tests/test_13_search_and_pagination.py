import pytest
from datetime import date, datetime, timedelta
from app.enums import UserRole, PaymentMethod, CashTransactionType
from app.services.payment_service import payment_service
from app.services.cash_service import cash_service
from app.schemas.payments import CreatePaymentRequestSchema
from app.schemas.cash import CreateCashTransactionRequestSchema


def test_payment_search_filters(db_session, clinic_factory, user_factory, patient_factory, plan_factory,
                                cashbox_factory):
    """
    Scenario: Verify filtering payments by Date, Doctor, and Amount.
    Setup:
      - Payment A: Yesterday, Doctor A, €100
      - Payment B: Today, Doctor B, €200
      - Payment C: Today, Doctor A, €50
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    doc_a = user_factory(clinic, role=UserRole.DOCTOR, email="doc_a@test.com")
    doc_b = user_factory(clinic, role=UserRole.DOCTOR, email="doc_b@test.com")

    patient = patient_factory(clinic, doc_a)
    plan = plan_factory(clinic, patient, doc_a, total_amount=1000.0)

    # Helper to create payment
    def make_pay(doctor, amount, days_offset=0):
        # We manually override created_at after creation for the date test
        payload = CreatePaymentRequestSchema(
            amount=amount, plan_id=plan.plan_id, cashbox_id=cashbox.cashbox_id, method=PaymentMethod.CASH
        )
        pay, _ = payment_service.create_payment(current_user=manager, session_user=manager, payload=payload)

        # Override attributes for testing
        pay.doctor_id = doctor.user_id
        # Fix: Use datetime, not date, to match Model field type
        pay.created_at = datetime.now() - timedelta(days=days_offset)

        db_session.add(pay)
        db_session.commit()
        return pay

    # Create Data
    pay_a = make_pay(doc_a, 100.0, days_offset=1)  # Yesterday
    pay_b = make_pay(doc_b, 200.0, days_offset=0)  # Today
    pay_c = make_pay(doc_a, 50.0, days_offset=0)  # Today

    # --- Test 1: Filter by Doctor A ---
    items, meta, _ = payment_service.search_payments(
        current_user=manager, doctor_id=doc_a.user_id,
        patient_id=None, method=None, date_from=None, date_to=None,
        min_amount=None, max_amount=None, has_tip=None,
        page=1, page_size=100  # Explicit pagination
    )
    assert len(items) == 2
    ids = [p.payment_id for p in items]
    assert pay_a.payment_id in ids
    assert pay_c.payment_id in ids
    assert pay_b.payment_id not in ids

    # --- Test 2: Filter by Date (Today Only) ---
    # Convert date to datetime for the service search args if needed,
    # but service expects datetime for start/end.
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())

    items, _, _ = payment_service.search_payments(
        current_user=manager, doctor_id=None,
        patient_id=None, method=None,
        date_from=today_start, date_to=today_end,
        min_amount=None, max_amount=None, has_tip=None,
        page=1, page_size=100
    )
    assert len(items) == 2
    ids = [p.payment_id for p in items]
    assert pay_b.payment_id in ids
    assert pay_c.payment_id in ids
    assert pay_a.payment_id not in ids

    # --- Test 3: Filter by Min Amount (> €150) ---
    items, _, _ = payment_service.search_payments(
        current_user=manager, doctor_id=None,
        patient_id=None, method=None, date_from=None, date_to=None,
        min_amount=150.0, max_amount=None, has_tip=None,
        page=1, page_size=100
    )
    assert len(items) == 1
    assert items[0].payment_id == pay_b.payment_id


def test_pagination_meta_logic(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Verify pagination math (Total Pages, Current Page, Has Next).
    Setup: Create 15 Cash Transactions.
    Request: Page 1 with Page Size 10.
    Expected: 10 items returned, Total Items=15, Total Pages=2.
    """
    clinic = clinic_factory()
    manager = user_factory(clinic, role=UserRole.MANAGER)
    cashbox = cashbox_factory(clinic)

    # Bulk create 15 transactions
    for i in range(15):
        cash_service.create_transaction(
            current_user=manager, session_user=manager,
            payload=CreateCashTransactionRequestSchema(
                cashbox_id=cashbox.cashbox_id,
                type=CashTransactionType.IN,
                amount=10.0,
                note=f"Tx {i}"
            )
        )

    # Act: Request Page 1 (Limit 10)
    items, meta, error = cash_service.search_transactions(
        current_user=manager, cashbox_id=None, type=None, status=None,
        category_id=None, payment_id=None, date_from=None, date_to=None,
        min_amount=None, max_amount=None,
        page=1, page_size=10
    )

    # Assert
    assert error is None
    assert len(items) == 10

    # Verify Meta Object
    # Fix: Check for 'page' OR 'current_page' to be safe, but typically it's 'page' in raw repo dicts
    page_key = 'page' if 'page' in meta else 'current_page'

    assert meta['total_items'] == 15
    assert meta['total_pages'] == 2
    assert meta[page_key] == 1
    assert meta['page_size'] == 10
    assert meta['has_next'] is True
    assert meta['has_prev'] is False

    # Act: Request Page 2
    items_p2, meta_p2, _ = cash_service.search_transactions(
        current_user=manager, cashbox_id=None, type=None, status=None,
        category_id=None, payment_id=None, date_from=None, date_to=None,
        min_amount=None, max_amount=None,
        page=2, page_size=10
    )

    assert len(items_p2) == 5
    assert meta_p2['has_next'] is False
    assert meta_p2['has_prev'] is True


def test_cross_clinic_search_isolation(db_session, clinic_factory, user_factory, cashbox_factory):
    """
    Scenario: Ensure searches strictly obey tenant isolation.
    User A (Clinic A) should NEVER find transactions from Clinic B,
    even if they match the search filters.
    """
    # Clinic A Setup
    clinic_a = clinic_factory(name="Clinic A")
    manager_a = user_factory(clinic_a, email="man_a@test.com")
    cashbox_a = cashbox_factory(clinic_a)

    # Clinic B Setup
    clinic_b = clinic_factory(name="Clinic B")
    manager_b = user_factory(clinic_b, email="man_b@test.com")
    cashbox_b = cashbox_factory(clinic_b)

    # Action: Create transaction in Clinic B
    cash_service.create_transaction(
        current_user=manager_b, session_user=manager_b,
        payload=CreateCashTransactionRequestSchema(
            cashbox_id=cashbox_b.cashbox_id, type=CashTransactionType.IN, amount=999.0
        )
    )

    # Action: Manager A searches for EVERYTHING
    items, meta, error = cash_service.search_transactions(
        current_user=manager_a, cashbox_id=None, type=None, status=None,
        category_id=None, payment_id=None, date_from=None, date_to=None,
        min_amount=None, max_amount=None,
        page=1, page_size=100
    )

    # Assert: Should find nothing (Clinic A is empty)
    assert len(items) == 0
    assert meta['total_items'] == 0
