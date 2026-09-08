# backend/test_advanced_features.py
# ---------------------------------
# Automated test suite to verify the three advanced features:
#   1. RFM segmentation calculation
#   2. Greedy budget channel allocation
#   3. Automated retargeting journey fallbacks
#
# Run this test script:
#   python backend/test_advanced_features.py

import sys
import os
import unittest
import asyncio
from datetime import datetime, timedelta, timezone

# Add backend folder to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── Mock Database for SQLite Testing ──────────────────────────────────────────
# Overrides PostgreSQL settings with SQLite before importing models/dispatcher
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

test_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_crm.db")
# Clean old test db if exists
if os.path.exists(test_db_path):
    try:
        os.remove(test_db_path)
    except Exception:
        pass

test_engine = create_engine(f"sqlite:///{test_db_path}")
TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

import database
database.engine = test_engine
database.SessionLocal = TestSessionLocal
database.DATABASE_URL = f"sqlite:///{test_db_path}"

# Now import dependent modules
from database import Base, SessionLocal, engine
from models import Customer, Order, Campaign, Communication, Receipt
from rfm import recalculate_rfm_tags
from dispatcher import allocate_channels_for_budget, run_journey_followup, resolve_message_tokens


class TestAdvancedCRMFeatures(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Create all tables in SQLite or PostgreSQL (uses database.py engine)
        Base.metadata.create_all(engine)

    def setUp(self):
        # Start a clean transaction
        self.db = SessionLocal()
        # Clean up existing test customers/campaigns to ensure isolated tests
        self.db.query(Receipt).delete()
        self.db.query(Communication).delete()
        self.db.query(Campaign).delete()
        self.db.query(Order).delete()
        self.db.query(Customer).delete()
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_1_rfm_segmentation(self):
        """Test calculating R, F, M scores and assigning correct tags to customers."""
        now = datetime.now()
        
        # Create 5 mock customers with varying spend/orders/recency
        # Champion: ordered 2 days ago, 10 orders, spent 12000
        c1 = Customer(name="Champion User", phone="9111111111", email="c1@test.com", channel_preference="whatsapp",
                      total_orders=10, total_spent=12000.0, last_order_date=now - timedelta(days=2), tags=[])
        # At Risk: ordered 50 days ago, 6 orders, spent 8000
        c2 = Customer(name="At Risk User", phone="9222222222", email="c2@test.com", channel_preference="sms",
                      total_orders=6, total_spent=8000.0, last_order_date=now - timedelta(days=50), tags=[])
        # Promising: ordered 3 days ago, 1 order, spent 500
        c3 = Customer(name="Promising User", phone="9333333333", email="c3@test.com", channel_preference="email",
                      total_orders=1, total_spent=500.0, last_order_date=now - timedelta(days=3), tags=[])
        # Sleeping: ordered 40 days ago, 1 order, spent 200
        c4 = Customer(name="Sleeping User", phone="9444444444", email="c4@test.com", channel_preference="email",
                      total_orders=1, total_spent=200.0, last_order_date=now - timedelta(days=40), tags=[])
        # Hibernating: ordered 80 days ago, 1 order, spent 100
        c5 = Customer(name="Hibernating User", phone="9555555555", email="c5@test.com", channel_preference="sms",
                      total_orders=1, total_spent=100.0, last_order_date=now - timedelta(days=80), tags=[])

        self.db.add_all([c1, c2, c3, c4, c5])
        self.db.commit()

        # Recalculate
        counts = recalculate_rfm_tags(self.db)
        
        # Verify tag updates
        self.db.refresh(c1)
        self.db.refresh(c2)
        self.db.refresh(c3)
        self.db.refresh(c4)
        self.db.refresh(c5)

        self.assertIn("rfm_champions", c1.tags)
        self.assertIn("rfm_at_risk", c2.tags)
        self.assertIn("rfm_promising", c3.tags)
        self.assertIn("rfm_about_to_sleep", c4.tags)
        self.assertIn("rfm_hibernating", c5.tags)
        
        print(f"      [Test:RFM] Segments assigned successfully: {counts}")

    def test_2_budget_allocation_greedy(self):
        """Test greedy budget optimizer algorithm under different spend limits."""
        # Create mock customer objects with varying monetary values (total_spent)
        customers = [
            Customer(id="cust_1", name="Alice", phone="911", email="a@t.com", channel_preference="whatsapp", total_spent=500.0),
            Customer(id="cust_2", name="Bob", phone="912", email="b@t.com", channel_preference="whatsapp", total_spent=2000.0),
            Customer(id="cust_3", name="Charlie", phone="913", email="c@t.com", channel_preference="sms", total_spent=150.0),
            Customer(id="cust_4", name="Diana", phone="914", email="d@t.com", channel_preference="email", total_spent=8000.0),
            Customer(id="cust_5", name="Evan", phone="915", email="e@t.com", channel_preference="whatsapp", total_spent=100.0)
        ]
        # Total = 5 customers.
        # Costs: WhatsApp = 0.80, SMS = 0.20, Email = 0.05.
        
        # Case A: Budget = ₹1.00 (We want to check if it upgrades or drops correctly)
        # Cost of 5 emails = 0.25. leftover = 0.75.
        # Upgrade to WhatsApp costs 0.75. We can afford exactly 1 WhatsApp upgrade!
        # Top spent is Diana (8000). She should get WhatsApp (₹0.80).
        # Next spent is Bob (2000), Alice (500), Charlie (150), Evan (100). They should get Email (₹0.05).
        # Total cost: 0.80 + 4*0.05 = ₹1.00. Fits budget exactly!
        allocation_a = allocate_channels_for_budget(customers, 1.00)
        self.assertEqual(allocation_a["cust_4"], "whatsapp") # Top spent Diana
        self.assertEqual(allocation_a["cust_2"], "email")
        self.assertEqual(allocation_a["cust_5"], "email")
        
        # Case B: Budget = ₹0.15 (Super small budget!)
        # 5 emails = 0.25 > 0.15. We can't even afford 5 emails.
        # Max emails = 0.15 // 0.05 = 3 emails.
        # The top 3 spenders (Diana, Bob, Alice) should get Email.
        # The bottom 2 spenders (Charlie, Evan) should be dropped (None).
        allocation_b = allocate_channels_for_budget(customers, 0.15)
        self.assertEqual(allocation_b["cust_4"], "email") # Diana
        self.assertEqual(allocation_b["cust_2"], "email") # Bob
        self.assertEqual(allocation_b["cust_1"], "email") # Alice
        self.assertIsNone(allocation_b["cust_3"])         # Charlie (dropped)
        self.assertIsNone(allocation_b["cust_5"])         # Evan (dropped)
        
        print("      [Test:Budget] Greedy allocation allocations matched cost constraints correctly.")

    def test_3_journey_fallback(self):
        """Test event-driven retargeting fallback. Unopened WhatsApp messages trigger fallback SMS."""
        # Setup Campaign
        campaign = Campaign(
            name="Journey Test Campaign",
            goal="Test automated fallback journey",
            segment_filters={
                "journey": {
                    "duration_seconds": 1,
                    "fallback_channel": "sms",
                    "fallback_template": "Hi {{name}}, missed you on WhatsApp! Use {{discount_code}} for 10% off."
                }
            },
            status="launched",
            message_template="Hi {{name}}, view WhatsApp offer!"
        )
        self.db.add(campaign)
        self.db.commit()

        # Create two customers
        c1 = Customer(name="Opener User", phone="9900000001", email="o@t.com", channel_preference="whatsapp", total_spent=100.0)
        c2 = Customer(name="Non-Opener User", phone="9900000002", email="n@t.com", channel_preference="whatsapp", total_spent=50.0)
        self.db.add_all([c1, c2])
        self.db.commit()

        # Create initial communications (sent via WhatsApp)
        comm1 = Communication(campaign_id=campaign.id, customer_id=c1.id, channel="whatsapp", message="Hi Opener!", status="sent")
        comm2 = Communication(campaign_id=campaign.id, customer_id=c2.id, channel="whatsapp", message="Hi Non-Opener!", status="sent")
        self.db.add_all([comm1, comm2])
        self.db.commit()

        # Simulate: Customer 1 opens the WhatsApp message, Customer 2 remains unopened
        comm1.status = "opened"
        self.db.commit()

        # Execute the journey fallback worker asynchronously
        # For testing, we run the coroutine directly in an event loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_journey_followup(campaign.id, campaign.segment_filters["journey"]))

        # Verify that Customer 2 (Non-Opener) received a fallback SMS communication
        # while Customer 1 (Opener) did not.
        all_comms = self.db.query(Communication).filter(Communication.campaign_id == campaign.id).all()
        
        # We should have 3 communications total (2 initial WhatsApps + 1 fallback SMS)
        self.assertEqual(len(all_comms), 3)
        
        # Verify c2 has a fallback SMS communication
        c2_comms = self.db.query(Communication).filter(Communication.campaign_id == campaign.id, Communication.customer_id == c2.id).all()
        self.assertEqual(len(c2_comms), 2)
        channels = [c.channel for c in c2_comms]
        self.assertIn("whatsapp", channels)
        self.assertIn("sms", channels)
        
        # Verify c1 only has the WhatsApp communication
        c1_comms = self.db.query(Communication).filter(Communication.campaign_id == campaign.id, Communication.customer_id == c1.id).all()
        self.assertEqual(len(c1_comms), 1)
        self.assertEqual(c1_comms[0].channel, "whatsapp")

        print("      [Test:Journey] Retargeting fallback triggered successfully for non-openers only.")

    def test_4_token_resolution(self):
        """Test resolve_message_tokens replaces {{first_name}}, {{total_spent}}, {{total_orders}}, {{customer_tags}} correctly."""
        customer = Customer(
            id="cust_abc123",
            name="Aashvi Sharma",
            phone="9988776655",
            email="aashvi@test.com",
            channel_preference="whatsapp",
            total_spent=15450.75,
            total_orders=12,
            tags=["vip", "rfm_champions", "fashion_lover"],
            last_order_date=datetime(2026, 4, 15)
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)

        template = (
            "Hi {{first_name}} (aka {{name}}), thank you for placing {{total_orders}} orders! "
            "You have spent a total of {{total_spent}} with us. We love having a {{customer_tags}} in our family. "
            "Your discount code is {{discount_code}} based on your order on {{last_order_date}}."
        )

        resolved = resolve_message_tokens(
            template=template,
            customer=customer,
            campaign_name="VIP Special Campaign",
            campaign_id="camp_987654"
        )

        self.assertIn("Hi Aashvi", resolved)
        self.assertIn("(aka Aashvi Sharma)", resolved)
        self.assertIn("placing 12 orders", resolved)
        self.assertIn("spent a total of ₹15,451 with us", resolved)
        # Note: 'rfm_champions' should be filtered out, leaving 'vip, fashion_lover'
        self.assertIn("having a vip, fashion_lover in our family", resolved)
        self.assertIn("discount code is VIPCAMPCUST", resolved) # prefix from 'VIP Special Campaign' -> VIP + campaign suffix 'CAMP' + customer suffix 'CUST'
        self.assertIn("order on 15 April", resolved)

        print("      [Test:Tokens] Personalization tokens resolved and validated successfully.")

    def test_5_active_days_segmentation(self):
        """Test active_days parser and build_segment_query filter."""
        from agent.copilot import parse_goal_to_filters
        from dispatcher import build_segment_query

        # 1. Verify parse_goal_to_filters with active goals
        f_active_1 = parse_goal_to_filters("active in last 7 days")
        self.assertIn("active_days", f_active_1)
        self.assertEqual(f_active_1["active_days"], 7)

        f_active_2 = parse_goal_to_filters("who have bought something in last 5 days")
        self.assertIn("active_days", f_active_2)
        self.assertEqual(f_active_2["active_days"], 5)

        # Verify default fallback if active/bought keywords are present without numeric spec
        f_active_3 = parse_goal_to_filters("target active customers")
        self.assertIn("active_days", f_active_3)
        self.assertEqual(f_active_3["active_days"], 30)

        # Verify inactive goals are still parsed as inactive_days
        f_inactive = parse_goal_to_filters("inactive for 14 days")
        self.assertIn("inactive_days", f_inactive)
        self.assertEqual(f_inactive["inactive_days"], 14)

        # 2. Verify build_segment_query with active_days filter
        now = datetime.now()
        c_active = Customer(name="Active Cust", phone="9990001111", email="act@test.com", channel_preference="whatsapp",
                            total_orders=3, total_spent=4500.0, last_order_date=now - timedelta(days=2), tags=[])
        c_inactive = Customer(name="Inactive Cust", phone="9990002222", email="inact@test.com", channel_preference="whatsapp",
                              total_orders=3, total_spent=4500.0, last_order_date=now - timedelta(days=10), tags=[])
        
        self.db.add_all([c_active, c_inactive])
        self.db.commit()

        # Query for customers active in the last 5 days
        q = build_segment_query(self.db, {"active_days": 5})
        results = q.all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "Active Cust")

        print("      [Test:ActiveDays] active_days parsing and query builder validated successfully.")


if __name__ == "__main__":
    unittest.main()
