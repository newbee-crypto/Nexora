# backend/seed.py
# ----------------
# One-time script to populate the database with 400 realistic Indian customers.
#
# Run this ONCE after starting Postgres:
#   python seed.py
#
# What this script does:
#   1. Calls Base.metadata.create_all() → creates all 5 tables (safe to call multiple times)
#   2. Checks if data already exists → skips seeding if customers table is not empty
#   3. Generates customers in 4 SEGMENTS with specific last_order_date distributions
#   4. Generates realistic orders for each customer
#   5. Derives denormalized fields (total_orders, total_spent, etc.) from the orders
#   6. Bulk-inserts everything efficiently
#   7. Prints a summary report so you can verify the distribution
#
# Why Faker en_IN (Indian locale)?
# → Produces realistic Indian names (Priya Sharma, Rahul Mehta), phone numbers (+91 format)
# → Makes the demo feel authentic for the Nexora use case (Indian e-commerce brand)

import random
from datetime import datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import text

# Import our database and model modules
from database import Base, SessionLocal, engine
from models import Customer, Order

# ── Initialize Faker with Indian locale ──────────────────────────────────────
# en_IN locale ensures realistic Indian first names, last names, addresses, phones.
fake = Faker("en_IN")

# Fix the random seed so the generated data is REPRODUCIBLE.
# If you re-run seed.py after wiping the DB, you get the same 400 customers.
# This is crucial for debugging — same data every time.
Faker.seed(42)
random.seed(42)


# ── Product Catalog ───────────────────────────────────────────────────────────
# Realistic Indian fashion/lifestyle e-commerce product names.
# Used to populate the `items` JSON array in each Order record.
PRODUCT_CATALOG = [
    "Kurta", "Saree", "Dupatta", "Lehenga", "Salwar Kameez",
    "Dhoti", "Sherwani", "Anarkali", "Palazzo Pants", "Chikankari Kurti",
    "Bandhani Dupatta", "Phulkari Dupatta", "Kanjivaram Silk Saree",
    "Banarasi Silk Saree", "Ikat Kurta", "Linen Shirt", "Cotton Kurta",
    "Ethnic Jacket", "Waistcoat", "Formal Trousers",
]

# ── Segment Definitions ───────────────────────────────────────────────────────
# Each segment defines:
#   - count: how many customers to generate
#   - days_range: tuple of (min_days_ago, max_days_ago) for last_order_date
#   - orders_range: how many orders this type of customer has
#   - amount_range: min/max order amount in ₹
#   - tags: list of tags to assign
#   - force_min_spent: if set, ensures total_spent >= this value (for VIP)
#
# Why these specific distributions?
# → inactive_days > 45 returns ~180 customers — a large, impressive segment for demo
# → inactive_days > 60 returns ~80 customers — the "deep win-back" segment
# → VIP customers (total_spent > 5000) make the "reward loyals" use case work
# → New customers (total_orders = 1) make the "convert first-timers" use case work

SEGMENTS = [
    {
        "name": "active",
        "count": 220,
        "days_range": (1, 44),           # Last ordered 1–44 days ago
        "orders_range": (2, 6),          # Has between 2 and 6 orders
        "amount_range": (150, 2000),     # ₹150 to ₹2000 per order
        "tags": [],                      # No special tags for generic active customers
        "force_min_spent": None,
    },
    {
        "name": "at_risk",
        "count": 100,
        "days_range": (45, 60),          # Last ordered 45–60 days ago
        "orders_range": (2, 5),          # Has 2–5 orders (not new, not churned)
        "amount_range": (150, 1500),
        "tags": ["at-risk"],
        "force_min_spent": None,
    },
    {
        "name": "churned",
        "count": 80,
        "days_range": (61, 90),          # Last ordered 61–90 days ago
        "orders_range": (1, 4),
        "amount_range": (150, 1200),
        "tags": ["at-risk"],             # Also at-risk but older
        "force_min_spent": None,
    },
    {
        "name": "vip",
        "count": 50,
        "days_range": (5, 30),           # VIPs are mostly active (they buy often)
        "orders_range": (5, 10),         # More orders than average
        "amount_range": (800, 3000),     # Higher spend per order
        "tags": ["vip"],
        "force_min_spent": 5000.0,       # Guarantee total_spent > ₹5000 for VIP filter
    },
    {
        "name": "new",
        "count": 60,
        "days_range": (1, 20),           # New customers — recent first order
        "orders_range": (1, 1),          # Exactly 1 order — they're new!
        "amount_range": (200, 1500),
        "tags": ["new"],
        "force_min_spent": None,
    },
]
# Total customers: 220 + 100 + 80 + 50 + 60 = 510... we cap at 400.
# We'll take 400 total across segments, adjusting "active" down to 110.
# Wait — let's do this correctly. Total = 110 + 100 + 80 + 50 + 60 = 400.
# We'll adjust "active" count to 110 to make the total exactly 400.
SEGMENTS[0]["count"] = 110  # Adjust active to make total = 400


# ── Channel Preference Distribution ──────────────────────────────────────────
# 50% WhatsApp, 25% SMS, 25% Email — reflects Indian consumer behavior.
# When we demo "win-back on WhatsApp", the segment is large enough to look good.
CHANNEL_PREFERENCES = ["whatsapp"] * 50 + ["sms"] * 25 + ["email"] * 25


def generate_indian_phone() -> str:
    """
    Generate a realistic Indian mobile number in the format: 9XXXXXXXXX (10 digits).

    Indian mobile numbers:
    - Always 10 digits
    - Start with 6, 7, 8, or 9 (telecom operator prefixes)
    - We prefix with nothing — the DB stores the 10-digit local number
    - Stays within max 15 chars for the DB column

    Why not use Faker's phone_number()?
    → Faker's en_IN phone_number() sometimes generates landline formats with STD codes.
    → A hardcoded format ensures we always get a valid mobile number.
    """
    # First digit is always 6, 7, 8, or 9 for Indian mobile numbers
    first_digit = random.choice(["6", "7", "8", "9"])
    remaining_digits = "".join([str(random.randint(0, 9)) for _ in range(9)])
    return f"+91{first_digit}{remaining_digits}"


def generate_orders_for_segment(
    customer_id: str,
    segment: dict,
    last_order_date: datetime,
) -> list[Order]:
    """
    Generate a list of Order objects for a customer based on their segment config.

    Key logic:
    1. Determine number of orders from the segment's orders_range
    2. The LAST order's created_at = last_order_date (this is the customer's most recent purchase)
    3. Previous orders are spread backwards in time (30–180 days before the last order each)
    4. If force_min_spent is set (VIP), we keep adding order amount until threshold is met

    Why derive orders this way?
    → Ensures that Customer.last_order_date is ALWAYS consistent with their actual last Order.
    → Prevents data inconsistencies (e.g., last_order_date = 5 days ago but all orders are 60+ days old)

    Args:
        customer_id: The UUID of the Customer who owns these orders
        segment: The segment config dict
        last_order_date: The computed last_order_date for this customer

    Returns:
        List of Order objects (not yet added to session)
    """
    num_orders = random.randint(*segment["orders_range"])
    min_amount, max_amount = segment["amount_range"]

    orders = []
    total_spent = 0.0

    # ── Generate each order ────────────────────────────────────────────────────
    for i in range(num_orders):
        # The most recent order gets last_order_date as its created_at.
        # Earlier orders are placed randomly further back in time.
        if i == 0:
            # Index 0 = the MOST RECENT order (last purchase)
            order_date = last_order_date
        else:
            # Each previous order is 30–180 days before the one after it
            days_back = random.randint(30, 180)
            order_date = orders[-1].created_at - timedelta(days=days_back)

        # Pick a random set of 1–3 products from the catalog
        items = random.sample(PRODUCT_CATALOG, k=random.randint(1, 3))

        # Generate order amount
        amount = round(random.uniform(min_amount, max_amount), 2)
        total_spent += amount

        order = Order(
            customer_id=customer_id,
            amount=amount,
            items=items,
            status="completed",
            created_at=order_date,
        )
        orders.append(order)

    # ── VIP: ensure total_spent exceeds force_min_spent ────────────────────────
    # If we generated a VIP customer but the random amounts didn't reach ₹5000,
    # we add extra amount to the first (most recent) order to bridge the gap.
    # This guarantees the SQL filter `total_spent > 5000` always catches VIPs.
    if segment.get("force_min_spent") and total_spent < segment["force_min_spent"]:
        shortfall = segment["force_min_spent"] - total_spent
        orders[0].amount = round(orders[0].amount + shortfall + 100, 2)
        total_spent = sum(o.amount for o in orders)

    return orders


def create_customer_from_segment(segment: dict) -> tuple[Customer, list[Order]]:
    """
    Create a single Customer and their Orders for a given segment.

    This is the main factory function. It:
    1. Generates the customer's last_order_date from the segment's days_range
    2. Creates the Customer record with CORRECT denormalized fields
    3. Generates Order records and derives totals from them

    Why compute last_order_date BEFORE generating orders?
    → We need the date first to pass it into generate_orders_for_segment(),
      which uses it as the anchor date for the most recent order.

    Returns:
        (Customer, [Order, ...]) — ready to be bulk-inserted

    """
    min_days, max_days = segment["days_range"]

    # Calculate last_order_date: randomly within the segment's day range
    # timezone-aware datetime for consistency — avoids comparison errors with DB
    days_ago = random.randint(min_days, max_days)
    last_order_date = datetime.now(timezone.utc) - timedelta(days=days_ago)

    # Generate a unique UUID for this customer — used as PK and also passed to orders
    customer_id = str(__import__("uuid").uuid4())

    # Assign a channel preference using the 50/25/25 distribution
    channel_preference = random.choice(CHANNEL_PREFERENCES)

    # Generate this customer's orders FIRST so we can compute totals
    orders = generate_orders_for_segment(customer_id, segment, last_order_date)

    # ── Compute denormalized fields from the actual orders ─────────────────────
    # This is the KEY POINT: we derive these fields from real order data,
    # not random values. This ensures data integrity.
    total_orders = len(orders)
    total_spent = round(sum(o.amount for o in orders), 2)

    # first_order_date = the earliest order's created_at
    first_order_date = min(o.created_at for o in orders)

    # Assign tags from segment config
    tags = segment["tags"].copy()

    # Generate Indian name and email using Faker
    name = fake.name()
    # Build a realistic email from the name — no spaces, lowercase
    email_local = name.lower().replace(" ", ".").replace("..", ".")
    email = f"{email_local}{random.randint(1, 999)}@{random.choice(['gmail.com', 'yahoo.co.in', 'outlook.com', 'hotmail.com'])}"

    customer = Customer(
        id=customer_id,
        name=name,
        phone=generate_indian_phone(),
        email=email,
        channel_preference=channel_preference,
        total_orders=total_orders,
        total_spent=total_spent,
        last_order_date=last_order_date,
        first_order_date=first_order_date,
        tags=tags,
    )

    return customer, orders


def seed_database() -> None:
    """
    Main seeding function. Creates all tables and inserts all customers + orders.

    Flow:
        1. Create tables (idempotent — safe to call even if tables already exist)
        2. Check if the database is already seeded (count customers)
        3. Generate customers + orders for each segment
        4. Bulk insert into PostgreSQL using session.add_all()
        5. Print a verification summary

    Why use add_all() instead of individual add() calls?
    → add_all() batches the inserts into a single transaction, which is much
      faster than individual commits. For 400 customers + ~1200+ orders, this
      makes seeding take < 1 second instead of several seconds.
    """
    print("=" * 60)
    print("Nexora CRM — Database Seeder")
    print("=" * 60)

    # ── Step 1: Create all tables ──────────────────────────────────────────────
    # create_all() is IDEMPOTENT: if tables already exist, it does nothing.
    # It uses SQLAlchemy's internal registry (Base.metadata) to find all models.
    print("\n[1/4] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("      ✓ All 5 tables created (or already exist)")

    # ── Step 2: Check if already seeded ───────────────────────────────────────
    db = SessionLocal()
    try:
        existing_count = db.query(Customer).count()
        if existing_count > 0:
            print(f"\n[SKIP] Database already contains {existing_count} customers.")
            print("       Delete all records or wipe the DB to re-seed.")
            print("       SQL: TRUNCATE customers, orders CASCADE;")
            return

        print(f"\n[2/4] Database is empty — beginning seed generation...")

        # ── Step 3: Generate all customers and orders ──────────────────────────
        all_customers = []
        all_orders = []
        segment_counts = {}

        for segment in SEGMENTS:
            seg_name = segment["name"]
            count = segment["count"]
            print(f"      Generating {count:3d} '{seg_name}' customers...")

            for _ in range(count):
                customer, orders = create_customer_from_segment(segment)
                all_customers.append(customer)
                all_orders.extend(orders)

            segment_counts[seg_name] = count

        print(f"\n      Total customers generated: {len(all_customers)}")
        print(f"      Total orders generated:    {len(all_orders)}")

        # ── Step 4: Bulk insert into PostgreSQL ────────────────────────────────
        print("\n[3/4] Inserting into database (single transaction)...")

        # Insert customers FIRST (orders have FK to customers)
        db.add_all(all_customers)
        db.flush()  # flush to DB without committing so FKs are satisfied

        # Insert orders next — customer records now exist in DB
        db.add_all(all_orders)
        db.flush()

        # Recalculate predictive RFM tags for all customers before committing
        from rfm import recalculate_rfm_tags
        print("\n      Calculating predictive RFM segments...")
        rfm_counts = recalculate_rfm_tags(db)
        print(f"      ✓ RFM segments calculated: {rfm_counts}")

        # Commit the entire batch — either all 400 customers + all orders
        # succeed, or everything is rolled back. Atomic operation.
        db.commit()

        print("      ✓ All records committed to PostgreSQL")

        # ── Step 5: Print verification summary ────────────────────────────────
        print("\n[4/4] Verification Summary:")
        print("-" * 50)

        # Run actual SQL queries to verify the data, not just trusting our counts
        total = db.query(Customer).count()
        print(f"  Total customers in DB:    {total}")

        # Verify inactive segments using the SAME SQL logic the AI copilot will use
        now = datetime.now(timezone.utc)
        cutoff_45 = now - timedelta(days=45)
        cutoff_60 = now - timedelta(days=60)

        inactive_45 = (
            db.query(Customer)
            .filter(Customer.last_order_date < cutoff_45)
            .count()
        )
        inactive_60 = (
            db.query(Customer)
            .filter(Customer.last_order_date < cutoff_60)
            .count()
        )

        print(f"  Inactive 45+ days:        {inactive_45}  (target: ~180)")
        print(f"  Inactive 60+ days:        {inactive_60}  (target: ~80)")

        vip_count = (
            db.query(Customer)
            .filter(Customer.total_spent > 5000)
            .count()
        )
        new_count = (
            db.query(Customer)
            .filter(Customer.total_orders == 1)
            .count()
        )

        print(f"  VIP customers (spent>₹5k): {vip_count}  (target: 50)")
        print(f"  New customers (1 order):   {new_count}  (target: 60)")

        # Channel distribution
        from sqlalchemy import func
        channel_dist = (
            db.query(Customer.channel_preference, func.count(Customer.id))
            .group_by(Customer.channel_preference)
            .all()
        )
        print("\n  Channel Preference Distribution:")
        for channel, count in channel_dist:
            pct = round(count / total * 100)
            print(f"    {channel:<12} {count:3d} customers  ({pct}%)")

        print("-" * 50)
        print("\n✅ Seeding complete! Your database is ready.")
        print("   Next step: uvicorn main:app --reload --port 8000")
        print("=" * 60)

    except Exception as e:
        # Roll back the entire transaction if anything fails
        db.rollback()
        print(f"\n❌ Seeding failed: {e}")
        print("   The database has been rolled back — no partial data inserted.")
        raise
    finally:
        db.close()


# ── Entry point ───────────────────────────────────────────────────────────────
# This block only runs when you execute `python seed.py` directly.
# It does NOT run when seed.py is imported as a module.
if __name__ == "__main__":
    seed_database()
