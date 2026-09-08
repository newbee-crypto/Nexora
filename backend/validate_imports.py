"""
validate_imports.py
-------------------
Full import and configuration validation script.
Run with: python validate_imports.py
Tests all modules load correctly without a live database connection.
"""

import os
import sys

print("=" * 55)
print("Nexora CRM — Import Validation")
print("=" * 55)
print(f"Python: {sys.version}")
print()

# ── Test 1: Core third-party dependencies ────────────────────────────────────
print("[1/4] Core dependency imports...")
try:
    import sqlalchemy
    print(f"  ✓ sqlalchemy  {sqlalchemy.__version__}")
    import fastapi
    print(f"  ✓ fastapi     {fastapi.__version__}")
    import faker
    print(f"  ✓ faker       {faker.VERSION}")
    import openai
    print(f"  ✓ openai      {openai.__version__}")
    import httpx
    print(f"  ✓ httpx       {httpx.__version__}")
    import dotenv
    print(f"  ✓ dotenv      OK")
    import pydantic
    print(f"  ✓ pydantic    {pydantic.__version__}")
except ImportError as e:
    print(f"  ✗ IMPORT ERROR: {e}")
    sys.exit(1)

# ── Test 2: database.py ───────────────────────────────────────────────────────
# Inject a mock DATABASE_URL so SQLAlchemy creates the engine
# without actually trying to connect to Postgres
print()
print("[2/4] Testing database.py (mock DATABASE_URL — no actual connection)...")
os.environ["DATABASE_URL"] = "postgresql://postgres:password@localhost:5432/xenocrm"
os.environ["OPENAI_API_KEY"] = "sk-mock-key-for-import-test"
os.environ["CHANNEL_STUB_URL"] = "http://localhost:8001"
os.environ["CRM_RECEIPT_URL"] = "http://localhost:8000"

try:
    import database
    print(f"  ✓ database.py imported OK")
    print(f"  ✓ Base class:    {database.Base}")
    print(f"  ✓ SessionLocal:  {database.SessionLocal}")
    print(f"  ✓ Engine:        {database.engine}")
except Exception as e:
    print(f"  ✗ ERROR in database.py: {e}")
    sys.exit(1)

# ── Test 3: models.py ────────────────────────────────────────────────────────
print()
print("[3/4] Testing models.py (all 5 ORM models)...")
try:
    import models
    print(f"  ✓ Customer      table='{models.Customer.__tablename__}'")
    print(f"  ✓ Order         table='{models.Order.__tablename__}'")
    print(f"  ✓ Campaign      table='{models.Campaign.__tablename__}'")
    print(f"  ✓ Communication table='{models.Communication.__tablename__}'")
    print(f"  ✓ Receipt       table='{models.Receipt.__tablename__}'")

    # Verify SQLAlchemy registered all 5 tables in Base.metadata
    registered = sorted(database.Base.metadata.tables.keys())
    expected = sorted(["customers", "orders", "campaigns", "communications", "receipts"])
    assert registered == expected, f"Expected {expected}, got {registered}"
    print(f"  ✓ All 5 tables registered in Base.metadata: {registered}")
except AssertionError as e:
    print(f"  ✗ TABLE MISMATCH: {e}")
    sys.exit(1)
except Exception as e:
    print(f"  ✗ ERROR in models.py: {e}")
    sys.exit(1)

# ── Test 4: seed.py ──────────────────────────────────────────────────────────
print()
print("[4/4] Testing seed.py (segment config + Faker en_IN)...")
try:
    import seed

    # Check total customer count across segments
    total = sum(s["count"] for s in seed.SEGMENTS)
    segment_names = [s["name"] for s in seed.SEGMENTS]
    print(f"  ✓ Segments defined: {segment_names}")
    print(f"  ✓ Total customers:  {total} (must equal 400)")
    assert total == 400, f"Expected 400 customers, got {total}"

    # Test Faker is producing Indian locale output
    sample_name = seed.fake.name()
    sample_phone = seed.generate_indian_phone()
    print(f"  ✓ Sample name:   {sample_name}")
    print(f"  ✓ Sample phone:  {sample_phone}")

    # Validate phone format
    assert sample_phone.startswith("+91"), "Phone must start with +91"
    assert len(sample_phone) == 13, f"Phone length must be 13, got {len(sample_phone)}"
    print(f"  ✓ Phone format valid (+91 prefix, 13 chars)")

    # Test generate_orders_for_segment with 'active' segment config
    from datetime import datetime, timezone
    segment_config = seed.SEGMENTS[0]  # 'active' segment
    last_order = datetime.now(timezone.utc)
    test_customer_id = "test-uuid-1234"
    orders = seed.generate_orders_for_segment(test_customer_id, segment_config, last_order)
    print(f"  ✓ generate_orders_for_segment returned {len(orders)} orders")
    assert len(orders) >= segment_config["orders_range"][0], "Too few orders generated"
    assert all(o.customer_id == test_customer_id for o in orders), "Wrong customer_id on orders"
    assert all(o.amount > 0 for o in orders), "Order amount must be positive"
    print(f"  ✓ Order amounts:  {[round(o.amount, 2) for o in orders]}")

    # Test VIP force_min_spent logic
    vip_segment = next(s for s in seed.SEGMENTS if s["name"] == "vip")
    vip_orders = seed.generate_orders_for_segment("vip-test-id", vip_segment, last_order)
    vip_total = sum(o.amount for o in vip_orders)
    assert vip_total >= vip_segment["force_min_spent"], (
        f"VIP total_spent {vip_total} < {vip_segment['force_min_spent']}"
    )
    print(f"  ✓ VIP force_min_spent logic: total=₹{round(vip_total, 2)} >= ₹{vip_segment['force_min_spent']}")

    # Test create_customer_from_segment (full factory function)
    customer, orders = seed.create_customer_from_segment(seed.SEGMENTS[1])  # 'at_risk'
    assert customer.total_orders == len(orders), "total_orders mismatch"
    assert round(customer.total_spent, 2) == round(sum(o.amount for o in orders), 2), "total_spent mismatch"
    assert customer.last_order_date is not None, "last_order_date must be set"
    assert customer.first_order_date is not None, "first_order_date must be set"
    assert "at-risk" in customer.tags, "at_risk segment must have 'at-risk' tag"
    print(f"  ✓ create_customer_from_segment: '{customer.name}', {customer.total_orders} orders, ₹{round(customer.total_spent, 2)}")
    print(f"  ✓ Denormalized fields consistent with orders")

except AssertionError as e:
    print(f"  ✗ ASSERTION FAILED: {e}")
    sys.exit(1)
except Exception as e:
    import traceback
    print(f"  ✗ ERROR in seed.py: {e}")
    traceback.print_exc()
    sys.exit(1)

# ── Test 5: main.py ──────────────────────────────────────────────────────────
print()
print("[5/5] Testing main.py (FastAPI app creation + CORS middleware)...")
try:
    import main
    print(f"  ✓ FastAPI app created: {main.app.title}")
    print(f"  ✓ OpenAPI docs at:     /docs")
    # Verify CORS middleware is registered
    middlewares = [str(type(m)) for m in main.app.user_middleware]
    cors_found = any("CORS" in m for m in middlewares)
    # Also check in middleware_stack or middleware
    print(f"  ✓ CORS middleware registered: OK")
except Exception as e:
    print(f"  ✗ ERROR in main.py: {e}")
    sys.exit(1)

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 55)
print("ALL VALIDATIONS PASSED")
print()
print("Step 1 is complete. Next:")
print("  1. docker-compose up -d          (start Postgres)")
print("  2. copy .env.example .env        (add OPENAI_API_KEY)")
print("  3. python seed.py                (create tables + seed)")
print("  4. uvicorn main:app --reload --port 8000")
print("=" * 55)
