import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import get_db
from models import Customer
from agent.tools import llm_call

logger = logging.getLogger("crm.opportunities")

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])

AI_OPPORTUNITIES_CACHE = None

WIN_BACK_CONVERSION_RATE = 0.15
VIP_UPSELL_CONVERSION_RATE = 0.20
NEW_CUSTOMER_CONVERSION = 0.25


def clear_opportunities_cache():
    """Clear the cached AI opportunities. Called when database resets."""
    global AI_OPPORTUNITIES_CACHE
    AI_OPPORTUNITIES_CACHE = None
    logger.info("[Opportunities] Cache cleared.")


def get_db_stats_summary(db: Session) -> str:
    """Gather current customer statistics to feed the LLM prompt."""
    try:
        total_customers = db.query(Customer).count()

        spent_stats = db.query(
            func.avg(Customer.total_spent).label("avg_spent"),
            func.max(Customer.total_spent).label("max_spent")
        ).first()
        avg_spent = float(spent_stats.avg_spent or 0)
        max_spent = float(spent_stats.max_spent or 0)

        now = datetime.now(timezone.utc)
        cutoff_45 = (now - timedelta(days=45)).replace(tzinfo=None)
        cutoff_60 = (now - timedelta(days=60)).replace(tzinfo=None)

        inactive_45 = db.query(Customer).filter(Customer.last_order_date < cutoff_45).count()
        inactive_60 = db.query(Customer).filter(Customer.last_order_date < cutoff_60).count()

        if db.bind.dialect.name == "sqlite":
            vip_tag_filter = text("exists (select 1 from json_each(customers.tags) where value = 'vip')")
            new_tag_filter = text("exists (select 1 from json_each(customers.tags) where value = 'new')")
        else:
            vip_tag_filter = text("tags::jsonb @> '[\"vip\"]'")
            new_tag_filter = text("tags::jsonb @> '[\"new\"]'")

        vip_count = db.query(Customer).filter(vip_tag_filter).count()
        new_count = db.query(Customer).filter(new_tag_filter).count()

        return f"""
        - Total Customers in DB: {total_customers}
        - Average Customer Total Lifetime Spend: ₹{avg_spent:.2f}
        - Maximum Customer Spend: ₹{max_spent:.2f}
        - Customers Inactive > 45 days: {inactive_45}
        - Customers Inactive > 60 days: {inactive_60}
        - VIP Customers (tagged 'vip'): {vip_count}
        - New Customers (tagged 'new'): {new_count}
        """
    except Exception as e:
        logger.error(f"Failed to gather database stats summary: {e}")
        return "- Total Customers: 400\n- Average Spent: 3200"


def get_deterministic_opportunities(db: Session) -> dict:
    """SQL-based fallback campaign opportunities."""
    now = datetime.now(timezone.utc)
    cutoff_45 = (now - timedelta(days=45)).replace(tzinfo=None)
    cutoff_60 = (now - timedelta(days=60)).replace(tzinfo=None)
    cutoff_90 = (now - timedelta(days=90)).replace(tzinfo=None)

    opportunities = []

    # Win-Back (45-Day Inactive)
    inactive_45_stats = (
        db.query(
            func.count(Customer.id).label("count"),
            func.avg(Customer.total_spent).label("avg_spent"),
        )
        .filter(Customer.last_order_date < cutoff_45)
        .filter(Customer.last_order_date >= cutoff_90)
        .first()
    )
    inactive_45_count = inactive_45_stats.count or 0
    inactive_45_avg_spent = float(inactive_45_stats.avg_spent or 0)

    if inactive_45_count > 0:
        estimated_recovery = int(
            inactive_45_count * (inactive_45_avg_spent * 0.15) * WIN_BACK_CONVERSION_RATE
        )
        opportunities.append({
            "id": "win_back_45",
            "title": "Win Back 45-Day Inactive Customers",
            "description": (
                f"{inactive_45_count:,} customers haven't ordered in 45+ days. "
                "A targeted WhatsApp message with a welcome back discount can recover them before they churn."
            ),
            "audience_count": inactive_45_count,
            "avg_spend": round(inactive_45_avg_spent, 2),
            "estimated_recovery": estimated_recovery,
            "suggested_filters": {"inactive_days": 45, "min_orders": 1},
            "suggested_goal": "Win back customers who haven't ordered in 45 days",
            "urgency": "high",
            "channel_hint": "whatsapp",
            "icon": "clock",
        })

    # VIP Reward
    if db.bind.dialect.name == "sqlite":
        vip_tag_filter = text("exists (select 1 from json_each(customers.tags) where value = 'vip')")
    else:
        vip_tag_filter = text("tags::jsonb @> '[\"vip\"]'")

    vip_stats = (
        db.query(
            func.count(Customer.id).label("count"),
            func.avg(Customer.total_spent).label("avg_spent"),
        )
        .filter(Customer.total_spent > 5000)
        .filter(vip_tag_filter)
        .first()
    )
    vip_count = vip_stats.count or 0
    vip_avg_spent = float(vip_stats.avg_spent or 0)

    if vip_count > 0:
        estimated_upsell = int(
            vip_count * (vip_avg_spent * 0.20) * VIP_UPSELL_CONVERSION_RATE
        )
        opportunities.append({
            "id": "vip_reward",
            "title": "Reward Your VIP Customers",
            "description": (
                f"{vip_count:,} high-value customers (avg spend ₹{vip_avg_spent:,.0f}) "
                "deserve exclusive rewards. Exclusive offers keep them loyal."
            ),
            "audience_count": vip_count,
            "avg_spend": round(vip_avg_spent, 2),
            "estimated_recovery": estimated_upsell,
            "suggested_filters": {"min_spent": 5000, "tags": ["vip"]},
            "suggested_goal": "Reward VIP customers with a loyalty discount",
            "urgency": "medium",
            "channel_hint": "whatsapp",
            "icon": "star",
        })

    # New Customer Nexoran
    if db.bind.dialect.name == "sqlite":
        new_tag_filter = text("exists (select 1 from json_each(customers.tags) where value = 'new')")
    else:
        new_tag_filter = text("tags::jsonb @> '[\"new\"]'")

    new_customer_stats = (
        db.query(
            func.count(Customer.id).label("count"),
            func.avg(Customer.total_spent).label("avg_spent"),
        )
        .filter(new_tag_filter)
        .filter(Customer.total_orders <= 2)
        .first()
    )
    new_count = new_customer_stats.count or 0
    new_avg_spent = float(new_customer_stats.avg_spent or 0)

    if new_count > 0:
        estimated_second_purchase = int(
            new_count * (new_avg_spent * 0.8) * NEW_CUSTOMER_CONVERSION
        )
        opportunities.append({
            "id": "new_customer_convert",
            "title": "Convert New Customers to Regulars",
            "description": (
                f"{new_count:,} new customers made only 1-2 purchases. "
                "A timely follow-up message converts first-timers into loyals."
            ),
            "audience_count": new_count,
            "avg_spend": round(new_avg_spent, 2),
            "estimated_recovery": estimated_second_purchase,
            "suggested_filters": {"tags": ["new"], "min_orders": 1},
            "suggested_goal": "Convert new customers to regulars",
            "urgency": "medium",
            "channel_hint": "whatsapp",
            "icon": "user-plus",
        })

    opportunities.sort(key=lambda x: x["estimated_recovery"], reverse=True)
    total_recovery = sum(o["estimated_recovery"] for o in opportunities)
    total_audience = sum(o["audience_count"] for o in opportunities)

    return {
        "opportunities": opportunities,
        "summary": {
            "total_opportunities": len(opportunities),
            "total_addressable_audience": total_audience,
            "total_estimated_recovery_inr": total_recovery,
        },
    }


def generate_ai_opportunities_with_llm(db: Session) -> dict:
    """Generate 3 tailored campaign opportunities using the LLM based on live DB stats."""
    stats_summary = get_db_stats_summary(db)

    prompt = f"""You are an e-commerce CRM marketing and conversion optimization expert.
Here are the current statistics of our customer base:
{stats_summary}

Your task is to dynamically generate exactly 3 highly targeted campaign recommendations for the dashboard.
Each recommendation must be distinct, creative, and aligned with database cohorts. Choose 3 different strategies from this list:
- Win Back Inactive Customers (targeting inactive_days > 45 or 60)
- Reward VIP Customers (targeting tag 'vip' or spent > 5000)
- Convert New Customers (targeting tag 'new')
- Re-engage Slipping Loyalists (targeting min_orders >= 2 and inactive_days > 30)
- High-AOV Upsell Campaign (targeting high-value spenders who order infrequently)
- Brand Advocacy Invite (targeting Champions/high order count)

For each campaign, calculate:
1. estimated_recovery: audience_count * average spent * conversion_rate (assume 10% to 20% conversion rate). Make sure it's a clean integer.

You MUST return a valid JSON array of exactly 3 objects.
Each object MUST strictly adhere to this JSON structure:
{{
  "id": "a_unique_string_id",
  "title": "Short, catchy title",
  "description": "2-3 sentences explaining why this campaign is recommended with specific numbers.",
  "audience_count": 120,
  "avg_spend": 4500.50,
  "estimated_recovery": 12000,
  "suggested_filters": {{
    "inactive_days": 45,
    "min_orders": 1
  }},
  "suggested_goal": "A clear marketing objective statement to pre-fill in the chat",
  "urgency": "high" | "medium" | "low",
  "channel_hint": "whatsapp" | "email" | "sms",
  "icon": "clock" | "star" | "user-plus" | "alert" | "trending-up"
}}

Respond ONLY with the JSON array. Do not wrap it in markdown code blocks.
"""
    try:
        messages = [
            {"role": "system", "content": "You are a database-driven marketing CRM assistant. Output valid JSON arrays only."},
            {"role": "user", "content": prompt}
        ]
        response_text = llm_call(messages, temperature=0.85)

        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()

        opportunities = json.loads(clean_text)

        if not isinstance(opportunities, list):
            raise ValueError("LLM response is not a JSON list")

        opportunities = opportunities[:3]

        for opp in opportunities:
            opp["id"] = opp.get("id") or "ai_campaign"
            opp["title"] = opp.get("title") or "Dynamic Campaign"
            opp["description"] = opp.get("description") or "AI recommended campaign."
            opp["audience_count"] = int(opp.get("audience_count") or 100)
            opp["avg_spend"] = float(opp.get("avg_spend") or 3000.0)
            opp["estimated_recovery"] = int(opp.get("estimated_recovery") or 30000)
            opp["suggested_filters"] = opp.get("suggested_filters") or {}
            opp["suggested_goal"] = opp.get("suggested_goal") or "Run a campaign"
            opp["urgency"] = opp.get("urgency") or "medium"
            opp["channel_hint"] = opp.get("channel_hint") or "whatsapp"
            opp["icon"] = opp.get("icon") or "trending-up"

        total_recovery = sum(o["estimated_recovery"] for o in opportunities)
        total_audience = sum(o["audience_count"] for o in opportunities)

        logger.info("[Opportunities] AI-generated opportunities created successfully.")
        return {
            "opportunities": opportunities,
            "summary": {
                "total_opportunities": len(opportunities),
                "total_addressable_audience": total_audience,
                "total_estimated_recovery_inr": total_recovery,
            }
        }
    except Exception as e:
        logger.error(f"[Opportunities] LLM generation failed: {e}. Falling back to SQL opportunities.")
        return get_deterministic_opportunities(db)


@router.get("")
def get_opportunities(refresh: bool = False, db: Session = Depends(get_db)):
    """Return AI-generated campaign opportunity recommendations."""
    global AI_OPPORTUNITIES_CACHE
    AI_OPPORTUNITIES_CACHE = generate_ai_opportunities_with_llm(db)
    return AI_OPPORTUNITIES_CACHE
