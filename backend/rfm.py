# backend/rfm.py
# --------------
# Implements Recency, Frequency, and Monetary (RFM) segmentation logic.
# Categorizes customers into segments (Champions, Loyal, Promising, At Risk, About to Sleep, Hibernating)
# and writes these categories as tags to Customer records in a backward-compatible way.

import logging
from datetime import datetime
from models import Customer

logger = logging.getLogger("crm.rfm")

def recalculate_rfm_tags(db) -> dict:
    """
    Recalculate RFM scores and tags for all customers in the database.
    
    Scores are calculated on a scale of 1-5:
    - Recency (R): Lower days since last order = higher score (5)
    - Frequency (F): Custom binning based on order count (higher = 5)
    - Monetary (M): Higher lifetime spent = higher score (5)
    
    Returns a dictionary summarizing the counts in each segment.
    """
    customers = db.query(Customer).all()
    if not customers:
        logger.warning("[rfm] No customers found in DB to calculate RFM tags.")
        return {}
    
    # Calculate raw values
    now_naive = datetime.now()
    raw_data = []
    for c in customers:
        if c.last_order_date:
            # Strip timezone if present to prevent naive vs aware subtraction TypeError
            lod_naive = c.last_order_date.replace(tzinfo=None) if c.last_order_date.tzinfo else c.last_order_date
            r_days = (now_naive - lod_naive).days
        else:
            r_days = 999
        f_count = c.total_orders
        m_spent = c.total_spent
        raw_data.append({
            "customer": c,
            "r_days": r_days,
            "f_count": f_count,
            "m_spent": m_spent
        })
        
    # ── Recency Quintiles (lower r_days is better -> score 5) ──────────────────
    raw_data.sort(key=lambda x: x["r_days"])
    n = len(raw_data)
    for idx, item in enumerate(raw_data):
        rank = idx / n
        if rank < 0.2:
            item["r_score"] = 5
        elif rank < 0.4:
            item["r_score"] = 4
        elif rank < 0.6:
            item["r_score"] = 3
        elif rank < 0.8:
            item["r_score"] = 2
        else:
            item["r_score"] = 1

    # ── Monetary Quintiles (higher m_spent is better -> score 5) ────────────────
    raw_data.sort(key=lambda x: x["m_spent"], reverse=True)
    for idx, item in enumerate(raw_data):
        rank = idx / n
        if rank < 0.2:
            item["m_score"] = 5
        elif rank < 0.4:
            item["m_score"] = 4
        elif rank < 0.6:
            item["m_score"] = 3
        elif rank < 0.8:
            item["m_score"] = 2
        else:
            item["m_score"] = 1

    # ── Frequency Custom Bins ──────────────────────────────────────────────────
    # Discrete distribution requires custom binning to prevent tie issues in quintiles
    for item in raw_data:
        f = item["f_count"]
        if f == 1:
            item["f_score"] = 1
        elif f == 2:
            item["f_score"] = 2
        elif f in (3, 4):
            item["f_score"] = 3
        elif f in (5, 6):
            item["f_score"] = 4
        else:
            item["f_score"] = 5

    # ── Classify into RFM segments ─────────────────────────────────────────────
    rfm_tags = {"rfm_champions", "rfm_loyal", "rfm_promising", "rfm_about_to_sleep", "rfm_at_risk", "rfm_hibernating"}
    segment_counts = {tag: 0 for tag in rfm_tags}
    
    for item in raw_data:
        c = item["customer"]
        r = item["r_score"]
        f = item["f_score"]
        m = item["m_score"]
        
        # Standard marketing RFM matrix logic
        if r >= 4 and f >= 4 and m >= 4:
            segment = "rfm_champions"
        elif r >= 3 and f >= 3 and m >= 3:
            segment = "rfm_loyal"
        elif r <= 2 and f >= 3 and m >= 3:
            segment = "rfm_at_risk"
        elif r >= 4 and f <= 2:
            segment = "rfm_promising"
        elif r >= 2 and f <= 2:
            segment = "rfm_about_to_sleep"
        else:
            segment = "rfm_hibernating"
            
        # Update customer tags list (removing old RFM tags first to avoid duplicates)
        updated_tags = [t for t in c.tags if t not in rfm_tags]
        updated_tags.append(segment)
        c.tags = updated_tags
        
        segment_counts[segment] += 1
        
    db.flush()
    logger.info(f"[rfm] Recalculated tags successfully. Counts: {segment_counts}")
    return segment_counts
