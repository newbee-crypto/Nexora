# backend/agent/copilot.py
# Multi-turn AI Campaign Copilot conversation loop.

import json
import logging
import asyncio
import re
from typing import Optional
from datetime import datetime
import os

from agent.tools import llm_call, execute_tool, AGENT_MODEL

logger = logging.getLogger("crm.agent.copilot")

# In-memory session store: session_id → list of message dicts
SESSIONS: dict[str, list[dict]] = {}

# Safety limit — prevent runaway agent loops
MAX_TOOL_CALLS_PER_TURN = 10

# System prompt defining the agent's personality, workflow, and guardrails
SYSTEM_PROMPT = """You are an AI Campaign Copilot for Nexora, an Indian e-commerce CRM platform.
Your job is to help brand marketers create and launch targeted customer campaigns through conversation.

STRICT GUARDRAIL — OFF-TOPIC RESTRICTION:
- You are strictly a marketing campaign and CRM assistant.
- You MUST refuse to answer any questions, requests, or instructions that are not related to e-commerce marketing, campaigns, segments, CRM data, or customer analysis.
- If the user asks general programming/coding questions (e.g. "write python code"), general knowledge, history, math, or anything unrelated, politely refuse and redirect them back to creating/managing campaigns (e.g., "I am your AI Campaign Copilot, and I can only assist you with setting up marketing campaigns or analyzing customer directories. Let me know if you would like to target a segment!").

WORKFLOW — always follow this exact sequence when creating campaigns:
1. When the marketer states a campaign goal → call build_segment
2. After build_segment → call suggest_channel (use the count and avg_spend from step 1)
3. After suggest_channel → call generate_message (use channel from step 2)
4. After generate_message → call preview_campaign (assemble everything for approval)
5. ONLY when the marketer explicitly says "launch", "send it", "go ahead", or "yes" → call launch_campaign

IMPORTANT RULES:
- Never skip steps. Always go 1 → 2 → 3 → 4 before offering launch.
- After preview_campaign, ask: "Shall I launch this campaign?" — don't auto-launch.
- If the marketer asks to change the message or channel, re-run generate_message or suggest_channel.
- Be concise and friendly. Use Indian currency (₹) when mentioning spend.
- After launch_campaign succeeds, tell the marketer to check the campaign analytics page.
- NEVER make up customer counts or data — always use the actual numbers from tool results.
- You remember the full conversation — use context from earlier messages to answer follow-ups.

STYLE: Friendly, professional, proactive. Keep narration short — the UI shows cards for details."""


def get_or_create_session(session_id: str) -> list[dict]:
    """Retrieve an existing conversation session or create a fresh one."""
    if session_id not in SESSIONS:
        SESSIONS[session_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        logger.info(f"[copilot] New session created: {session_id}")
    return SESSIONS[session_id]


def delete_session(session_id: str) -> bool:
    """Delete a session's conversation history."""
    if session_id in SESSIONS:
        del SESSIONS[session_id]
        logger.info(f"[copilot] Session deleted: {session_id}")
        return True
    return False


def get_session_history(session_id: str) -> list[dict]:
    """Return the conversation history for a session (for debugging)."""
    return SESSIONS.get(session_id, [])


def _get_conversation_context_summary(history: list[dict]) -> str:
    """Build a readable summary of the conversation so far (excluding system prompt)."""
    parts = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            continue
        if role == "user":
            parts.append(f"User: {content[:200]}")
        elif role == "assistant":
            parts.append(f"Assistant: {content[:200]}")
        elif role == "tool":
            try:
                data = json.loads(content)
                step = data.get("step", "tool_result")
                summary = data.get("summary", "")
                parts.append(f"[Tool: {step}] {summary[:150]}")
            except Exception:
                parts.append(f"[Tool result]")
    return "\n".join(parts[-20:])  # Last 20 exchanges


def _get_active_campaign_preview(history: list[dict]) -> Optional[dict]:
    """Scan history backwards for the latest campaign_preview step."""
    for msg in reversed(history):
        if msg.get("role") == "tool":
            try:
                content = json.loads(msg.get("content", "{}"))
                if content.get("step") == "campaign_preview":
                    return content
            except Exception:
                continue
    return None


def clean_copywriting_noise(text: str) -> str:
    """
    Strips promotional and copywriting noise (e.g. 'buy 2 get 3', '40% off') 
    to prevent false positives in filter extraction.
    """
    text_lower = text.lower()
    # Remove buy X get Y offers
    text_lower = re.sub(r"\bbuy\s+\d+\s+get\s+\d+(?:\s+free)?\b", "", text_lower)
    text_lower = re.sub(r"\bbuy\s+\d+\s+pay\s+for\s+\d+\b", "", text_lower)
    # Remove percentage discount expressions
    text_lower = re.sub(r"\b\d+%\s*(?:off|discount|cashback)\b", "", text_lower)
    text_lower = re.sub(r"\bup\s+to\s+\d+%\b", "", text_lower)
    text_lower = re.sub(r"\bflat\s+\d+%\b", "", text_lower)
    # Remove rs/inr amounts that are clearly discounts, e.g. "off rs 500", "save rs 500", "discount of 500"
    text_lower = re.sub(r"\b(?:off|save|discount\s+(?:of)?|coupon\s+(?:of)?|code\s+(?:of)?)\s*(?:rs\.?|inr|₹)?\s*\d+\b", "", text_lower)
    return text_lower


def parse_goal_to_filters(goal: str, history: Optional[list[dict]] = None, use_defaults: bool = True) -> dict:
    """
    Extremely robust, regex-based Python parser that translates natural language
    campaign goals into PostgreSQL segmentation filters.
    
    This replaces calling the LLM for filter extraction, saving 1 full API call
    per turn and preventing 429 rate limits, while remaining 100% deterministic.
    """
    goal_cleaned = clean_copywriting_noise(goal)
    goal_lower = goal_cleaned.lower()
    
    # Replace simple word numbers with digits to simplify regex matching
    word_to_digit = {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10"
    }
    for word, digit in word_to_digit.items():
        goal_lower = re.sub(rf"\b{word}\b", digit, goal_lower)
    
    referencing_pronouns = [
        # English
        "them", "then", "these", "this cohort", "these customers", "these users",
        "this list", "that cohort", "this group", "these vip", "those",
        "the same", "same people", "same customers", "same group",
        "only them", "just them", "only these", "just these", "only", "just",
        # Hindi / Hinglish — "send them" equivalents
        "inhiko", "inhe", "inko", "unhe", "unko", "ko only",
        "inlogo", "in logo", "inhi logo", "sabko", "inhee",
        "yahi log", "yeh log", "ye log", "bas inhe", "sirf inhe",
        "bas inhiko", "sirf inhiko", "inhi ko", "inhi", "sirf", "bas",
    ]
    is_referencing = any(p in goal_lower for p in referencing_pronouns)

    # IMPLICIT CARRYOVER:
    # If the user message has no numeric filter specifications (no numbers at all, or no numbers matching days/spent/orders)
    # and we have a previous query/segment in the session, we should treat it as referencing.
    has_numeric_spec = (
        re.search(r"\d+", goal_lower) is not None or
        any(kw in goal_lower for kw in ["inactive", "days", "months", "spent", "orders", "purchase"])
    )
    if not has_numeric_spec and history:
        for msg in reversed(history[:-1]):
            if msg.get("role") == "tool":
                try:
                    content = json.loads(msg.get("content", "{}"))
                    if content.get("step") in ("customer_query_results", "segment_built"):
                        is_referencing = True
                        logger.info("[copilot] No numeric specs in user message. Implicitly carrying over previous cohort.")
                        break
                except Exception:
                    continue
    
    if is_referencing and history:
        # First: check if last tool result has exact customer IDs from a directory query
        for msg in reversed(history[:-1]):
            if msg.get("role") == "tool":
                try:
                    content = json.loads(msg.get("content", "{}"))
                    if content.get("step") == "customer_query_results":
                        # If the user's previous query had an explicit limit (like "top 5"), target those specific IDs.
                        # Otherwise, re-parse the query to target the entire segment!
                        prev_query_text = content.get("query", "").lower()
                        has_explicit_limit = re.search(r"\b(top|bottom|least|most|limit|first|last)\b\s*\d+|\b\d+\b\s*(customers|people|users|vip|vip's)", prev_query_text)
                        
                        if has_explicit_limit:
                            ids = content.get("cohort_customer_ids", [])
                            if ids:
                                logger.info(f"[copilot] Exact ID carryover: targeting {len(ids)} specific customers")
                                return {"customer_ids": ids}
                        
                        # Fallback to cohort_params if no IDs saved or no explicit limit
                        params = content.get("cohort_params")
                        if params:
                            logger.info(f"[copilot] Context carryover from query params: {params}")
                            cohort_filters = {}
                            if params.get("tag"):
                                cohort_filters["tags"] = [params["tag"]]
                            sort_by = params.get("sort_by", "total_spent")
                            sort_order = params.get("sort_order", "desc")
                            if sort_by == "total_spent":
                                if sort_order == "desc":
                                    cohort_filters["min_spent"] = 15000.0
                                else:
                                    cohort_filters["min_orders"] = 1
                                    cohort_filters["max_orders"] = 3
                            elif sort_by == "last_order_date" and sort_order == "asc":
                                cohort_filters["inactive_days"] = 45
                            elif sort_by == "total_orders":
                                if sort_order == "asc":
                                    cohort_filters["min_orders"] = 1
                                    cohort_filters["max_orders"] = 2
                                else:
                                    cohort_filters["min_orders"] = 7
                            if cohort_filters:
                                return cohort_filters
                except Exception:
                    pass

        # Fallback: look back at user's previous query message and re-parse it
        for msg in reversed(history[:-1]):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                content_lower = content.lower()
                query_keywords = ["customer", "directory", "show me", "give me", "find", "search", "list", "who", "top", "spenders", "loyal", "active", "inactive"]
                if any(kw in content_lower for kw in query_keywords) and not any(kw in content_lower for kw in ["campaign", "launch", "send"]):
                    logger.info(f"[copilot] Contextual reference found. Parsing previous query: '{content}'")
                    prev_filters = parse_goal_to_filters(content)
                    if prev_filters:
                        return prev_filters

    # Clean up welcome message template examples
    welcome_snippets = [
        "win back customers who haven't ordered in 45 days",
        "haven't ordered in 45 days",
        "inactive for 45 days"
    ]
    for snippet in welcome_snippets:
        goal_lower = goal_lower.replace(snippet, "")
        
    filters = {}
    
    # 1. Inactivity / Activity Days parsing
    has_inactive_keywords = any(kw in goal_lower for kw in ["inactive", "win back", "re-engage", "haven't ordered", "churn", "miss you"])
    has_active_keywords = any(kw in goal_lower for kw in ["active", "bought", "purchased", "within", "last", "recently"]) and not any(kw in goal_lower for kw in ["not", "haven't", "inactive", "win back"])
    days_matches = re.findall(r"(\d+)\s*day", goal_lower)
    months_matches = re.findall(r"(\d+)\s*month", goal_lower)
    
    if days_matches:
        days_val = int(days_matches[-1])
        if has_active_keywords:
            filters["active_days"] = days_val
        else:
            filters["inactive_days"] = days_val
    elif months_matches:
        days_val = int(months_matches[-1]) * 30
        if has_active_keywords:
            filters["active_days"] = days_val
        else:
            filters["inactive_days"] = days_val
    elif has_inactive_keywords:
        filters["inactive_days"] = 45
    elif has_active_keywords:
        filters["active_days"] = 30
        
    # 2. Spend Filter parsing
    spend_match = re.search(r"(?:spend|spent|spending|value|amount|worth|cost)\s*(?:of|more than|above|at least|over|>|>=)?\s*(?:rs\.?|inr|₹)?\s*(\d+)", goal_lower)
    if spend_match:
        filters["min_spent"] = float(spend_match.group(1))
    else:
        rupee_match = re.search(r"(?:rs\.?|inr|₹)\s*(\d+)", goal_lower)
        if rupee_match:
            filters["min_spent"] = float(rupee_match.group(1))
            
    # 3. Order Count parsing
    order_match = re.search(r"(?:order|ordered|purchase|purchases|purchased|buy|bought|time|times)\s*(?:more than|above|at least|over|>|>=)?\s*(\d+)", goal_lower)
    if not order_match:
        order_match = re.search(r"(\d+)\s*(?:order|ordered|purchase|purchases|time|times)", goal_lower)
        
    if order_match:
        num = int(order_match.group(1))
        if any(phrase in goal_lower for phrase in ["more than", "above", "greater than", ">"]):
            filters["min_orders"] = num + 1
        else:
            filters["min_orders"] = num
            
    # 4. Tags parsing
    if any(kw in goal_lower for kw in ["vip", "reward", "top"]):
        if "tags" not in filters:
            filters["tags"] = []
        if "vip" not in filters["tags"]:
            filters["tags"].append("vip")
            
    # Refined Tags parsing for "new"
    has_new_tag = False
    if "new" in goal_lower:
        if re.search(r"\bnew\s+(?:customer|user|member|signup|onboard|buyer|shopper|regist|client|lead|account|join|subscriber)s?\b", goal_lower):
            has_new_tag = True
        elif re.search(r"\bnewly\s+(?:registered|signed|joined|onboarded)\b", goal_lower):
            has_new_tag = True
        elif re.search(r"\btag\s*:\s*new\b", goal_lower):
            has_new_tag = True
        elif re.search(r"\btarget\s+new\b", goal_lower):
            has_new_tag = True
            
    if has_new_tag or any(kw in goal_lower for kw in ["first", "onboard", "welcome"]):
        if not re.search(r"\bnew\s+(?:sale|arrival|collection|product|item|stock|range|offer|discount|promo|code|message|template|email|sms|whatsapp|run|launch)\b", goal_lower):
            if "tags" not in filters:
                filters["tags"] = []
            if "new" not in filters["tags"]:
                filters["tags"].append("new")
            
    # Check for at-risk (both tag formats)
    if "at-risk" in goal_lower or "at risk" in goal_lower:
        if "tags" not in filters:
            filters["tags"] = []
        if "rfm_at_risk" not in filters["tags"]:
            filters["tags"].append("rfm_at_risk")
        if "at-risk" not in filters["tags"]:
            filters["tags"].append("at-risk")
        if "inactive_days" not in filters:
            filters["inactive_days"] = 30
            
    # 4.6 Budget limit parsing
    budget_match = re.search(r"\b(?:budget|limit|spend limit)\b.*?\b(?:rs\.?|inr|₹)?\s*(\d[\d,]*)\b", goal_lower)
    if budget_match:
        filters["budget_limit"] = int(budget_match.group(1).replace(",", ""))

    # 4.7 Predictive RFM segments parsing
    if any(kw in goal_lower for kw in ["champion", "champions", "best customer", "best customers"]):
        if "tags" not in filters:
            filters["tags"] = []
        if "rfm_champions" not in filters["tags"]:
            filters["tags"].append("rfm_champions")

    if any(kw in goal_lower for kw in ["loyal", "loyals", "regular", "regulars"]):
        if "tags" not in filters:
            filters["tags"] = []
        if "rfm_loyal" not in filters["tags"]:
            filters["tags"].append("rfm_loyal")

    if any(kw in goal_lower for kw in ["promising", "potential"]):
        if "tags" not in filters:
            filters["tags"] = []
        if "rfm_promising" not in filters["tags"]:
            filters["tags"].append("rfm_promising")

    if any(kw in goal_lower for kw in ["about to sleep", "sleepy", "sleeping"]):
        if "tags" not in filters:
            filters["tags"] = []
        if "rfm_about_to_sleep" not in filters["tags"]:
            filters["tags"].append("rfm_about_to_sleep")

    if any(kw in goal_lower for kw in ["hibernating", "dormant", "deep inactive"]):
        if "tags" not in filters:
            filters["tags"] = []
        if "rfm_hibernating" not in filters["tags"]:
            filters["tags"].append("rfm_hibernating")
            
    # 4.8 Retarget Campaign ID parsing
    uuid_match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", goal_lower)
    if uuid_match and "retarget" in goal_lower:
        filters["retarget_campaign_id"] = uuid_match.group(1)

    # 4.9 Automated Journey Fallback parsing
    if "fallback" in goal_lower or "journey" in goal_lower:
        fallback_channel = "sms"
        if "email" in goal_lower or "mail" in goal_lower:
            fallback_channel = "email"
        elif "whatsapp" in goal_lower:
            fallback_channel = "whatsapp"
            
        filters["journey"] = {
            "duration_seconds": 15,
            "fallback_channel": fallback_channel
        }
            
    # 5. Default Fallback
    if not filters and use_defaults:
        filters["inactive_days"] = 30
        filters["min_orders"] = 1
        
    # Resolve tag conflicts to prevent empty segment queries
    if "tags" in filters:
        if "vip" in filters["tags"] and "rfm_loyal" in filters["tags"]:
            filters["tags"].remove("rfm_loyal")
            
    return filters


def is_analysis_suggestion_request(message: str) -> bool:
    msg_lower = message.lower()
    # Match words starting with sug (e.g., suggest, sugest, suggeest, suggestion)
    has_suggest = re.search(r"\bsug{1,2}\w*\b", msg_lower) is not None
    has_analyze = re.search(r"\banal\w*\b", msg_lower) is not None
    has_campaign = any(kw in msg_lower for kw in ["campaign", "campain", "offer", "goal", "segment", "recommend"])
    has_data = any(kw in msg_lower for kw in ["data", "db", "database", "customer", "directory"])
    
    if (has_suggest and (has_campaign or has_data)) or (has_analyze and (has_data or has_campaign)) or (has_analyze and has_suggest):
        return True
        
    phrases = [
        "analyse the data", "analyze the data", "analyse data", "analyze data",
        "analyse database", "analyze database", "analyse customer", "analyze customer",
        "suggest a campaign", "suggest me a campaign", "suggest campaign", "suggest some campaign",
        "campaign recommendation", "which campaign should", "what campaign should",
        "campaign suggestions", "suggest a good campaign", "suggest some good campaign",
        "analyse and suggest", "analyze and suggest"
    ]
    return any(p in msg_lower for p in phrases)


def _build_dynamic_insight_fallback(message: str) -> str:
    """Parses campaign stats from the prompt and constructs a highly detailed, dynamic insight report."""
    try:
        sent_m = re.search(r"Total Sent:\s*(\d+)", message)
        delivered_m = re.search(r"Delivered:\s*(\d+)", message)
        opened_m = re.search(r"Opened:\s*(\d+)", message)
        purchased_m = re.search(r"Purchased:\s*(\d+)", message)
        revenue_m = re.search(r"Est\. Revenue:\s*₹?\s*([\d,.]+)", message)
        roi_m = re.search(r"ROI:\s*(-?[\d,.]+)%", message)
        conv_m = re.search(r"Nexoran Rate:\s*([\d,.]+)%", message)
        
        sent = int(sent_m.group(1)) if sent_m else 0
        delivered = int(delivered_m.group(1)) if delivered_m else 0
        opened = int(opened_m.group(1)) if opened_m else 0
        purchased = int(purchased_m.group(1)) if purchased_m else 0
        revenue = float(revenue_m.group(1).replace(",", "")) if revenue_m else 0.0
        roi = float(roi_m.group(1).replace(",", "")) if roi_m else 0.0
        conv = float(conv_m.group(1).replace(",", "")) if conv_m else 0.0
        
        open_rate = round((opened / max(delivered, 1)) * 100, 1) if delivered > 0 else 0.0
        
        if purchased > 0:
            if roi > 0:
                return f"Campaign is performing exceptionally well with a positive ROI of {roi}%. We have successfully converted {purchased} shoppers, generating an estimated ₹{round(revenue):,} in revenue. The strong open rate of {open_rate}% is the primary driver of this engagement."
            else:
                return f"Campaign has successfully generated {purchased} conversions and recaptured ₹{round(revenue):,} in sales. However, due to high delivery costs, the current ROI is {roi}%. Consider optimizing messaging copy or targeting a more qualified cohort next time."
        elif opened > 0:
            return f"Campaign delivery is healthy, achieving a {open_rate}% open rate. Although we have not recorded purchases yet, the active customer opens show solid engagement. Recommend sending a secondary retargeting SMS to non-responders."
        else:
            return f"Campaign has been dispatched to {sent} recipients. We are currently waiting for webhook delivery confirmations and shopper open events to populate performance details."
    except Exception:
        return "Campaign stats show steady delivery and active engagement. Keep monitoring the dashboard for further conversion events."


async def run_agent_turn(
    session_id: str,
    user_message: str,
    db,
    background_tasks=None,
    edited_template: Optional[str] = None,
) -> dict:
    """
    Process one user message through the optimized hybrid agent loop.

    HYBRID DETERMINISTIC DESIGN:
    ────────────────────────────
    To run reliably on the Google Gemini API Free Tier (which has strict rate limits),
    we avoid running standard OpenAI tool-calling loops (which take 5-7 LLM requests
    to orchestrate a simple 4-step pipeline).
    
    Instead:
    - AI Insights: Handled in exactly 1 direct LLM text call (with key rotation).
    - Launch Campaign: Parsed deterministically from history (0 LLM calls).
    - Channel/Tone Refinement: Re-generates copy in exactly 1 LLM call.
    - Campaign Building: Runs build_segment (SQL), suggest_channel, and preview_campaign
      locally in Python. Calls the LLM exactly ONCE inside generate_message for copy.
    - Greetings/Follow-ups/Summaries: All handled by 1 LLM call with conversation context.
      
    Key rotation ensures that if key #1 hits 429, the system automatically retries
    with key #2, #3, etc. — transparent to the caller.
    """
    # ── Get or initialize conversation history ────────────────────────────────
    history = get_or_create_session(session_id)
    history.append({"role": "user", "content": user_message})
    logger.info(f"[copilot] Session {session_id[:8]}: user → '{user_message[:80]}'")

    is_mock = not any([
        os.getenv(f"GEMINI_KEY_{i}", "").strip() for i in range(1, 6)
    ]) and not os.getenv("OPENAI_API_KEY", "").strip()

    # ── CASE A: AI Insight Request (Campaign details page stats analysis) ────────
    if session_id.startswith("insight-") or "performance stats" in user_message.lower():
        if is_mock:
            insight = _build_dynamic_insight_fallback(user_message)
        else:
            try:
                insight = llm_call(
                    messages=[{"role": "user", "content": user_message}],
                    temperature=0.3,
                    max_tokens=400,
                )
            except Exception as e:
                logger.error(f"[copilot] Insight generation failed: {e}")
                insight = _build_dynamic_insight_fallback(user_message)
        
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": insight
        }

    # ── CASE B: Campaign Launch Approval (0 LLM calls) ───────────────────────────
    user_msg_lower = user_message.lower()
    if any(w in user_msg_lower for w in ["launch", "send it", "go ahead", "yes, launch", "launch it", "launch the campaign"]):
        campaign_preview = _get_active_campaign_preview(history[:-1])

        if campaign_preview:
            # Determine whether variant A or B was chosen by user
            if edited_template:
                chosen_variant = edited_template
                logger.info(f"[copilot] Launching with manually edited template: {chosen_variant[:60]}...")
            else:
                chosen_variant = campaign_preview.get("variant_a", "")
                if "variant b" in user_msg_lower or "variant_b" in user_msg_lower or user_message.strip().endswith("B") or user_message.strip().endswith("b"):
                    chosen_variant = campaign_preview.get("variant_b", "")
                
            # Retrieve the original campaign goal from user messages by checking campaign_preview or looking backwards
            campaign_goal = campaign_preview.get("goal")
            if not campaign_goal:
                for msg in reversed(history[:-1]):
                    content = msg.get("content", "")
                    if msg.get("role") == "user" and not any(w in content.lower() for w in ["launch", "send it", "go ahead", "yes, launch", "launch it", "launch the campaign"]):
                        if content.strip().lower() not in ("hi", "hello", "hey", "hola"):
                            campaign_goal = content
                            break

            launch_args = {
                "campaign_name": campaign_preview.get("campaign_name", "New Campaign"),
                "goal": campaign_goal or "Custom Campaign",
                "segment_filters": campaign_preview.get("segment_filters", {}),
                "message_template": chosen_variant,
                "channel": campaign_preview.get("channel", "whatsapp")
            }

            try:
                launch_result = await execute_tool("launch_campaign", launch_args, db, background_tasks)
                history.append({
                    "role": "tool",
                    "tool_call_id": "launch_call",
                    "content": json.dumps(launch_result),
                })
                return {
                    "session_id": session_id,
                    "steps": [launch_result],
                    "final_message": launch_result["summary"]
                }
            except Exception as e:
                logger.error(f"[copilot] Launch execution failed: {e}")
                return {
                    "session_id": session_id,
                    "steps": [],
                    "final_message": f"Failed to launch campaign: {str(e)}",
                    "error": True
                }

    # ── CASE B.5: Data Analysis & Campaign Suggestion ──────────────────────────
    if is_analysis_suggestion_request(user_message):
        try:
            from rfm import recalculate_rfm_tags
            from models import Customer
            
            # Recalculate RFM tags
            rfm_counts = recalculate_rfm_tags(db)
            db.commit()
            
            # Query basic database stats
            total_customers = db.query(Customer).count()
            customers_spent = db.query(Customer.total_spent).all()
            total_revenue = sum(c[0] for c in customers_spent if c[0] is not None)
            avg_spent = total_revenue / total_customers if total_customers > 0 else 0
            
            # Call LLM for analysis and suggestion
            prompt = f"""You are the Nexora AI Campaign Copilot.
The user wants you to analyze the database and suggest some good marketing campaigns to launch.

Here are the current CRM database statistics:
- Total Customers: {total_customers}
- Total Customer Lifetime Value (Revenue): ₹{round(total_revenue):,}
- Average Lifetime Spend: ₹{round(avg_spent):,}
- RFM Segment Distribution:
  * Champions: {rfm_counts.get('rfm_champions', 0)} (Highest spending, most frequent, recent shoppers)
  * Loyal Customers: {rfm_counts.get('rfm_loyal', 0)} (High value, regular shoppers)
  * Promising Customers: {rfm_counts.get('rfm_promising', 0)} (Recent buyers, but low frequency/spend)
  * About to Sleep: {rfm_counts.get('rfm_about_to_sleep', 0)} (Below average recency and frequency)
  * At Risk: {rfm_counts.get('rfm_at_risk', 0)} (High value, frequent buyers who haven't ordered in a long time)
  * Hibernating: {rfm_counts.get('rfm_hibernating', 0)} (Low recency, low frequency, low spend)

Please analyze this data and suggest 3 concrete campaign ideas.
For each suggestion, provide:
1. **Campaign Name & Objective**
2. **Target Audience segment** (referencing the specific RFM count and segment)
3. **Recommended Channel & Offer/Pitch** (e.g. WhatsApp with a 15% discount for At-Risk, or Email for VIPs)
4. **Actionable trigger phrase** (e.g. "Just reply with: 'Launch Campaign 1' or 'Target at-risk customers'")

Keep the response structured, clear, and highly professional in Markdown. Use Indian currency (₹). Make it sound exciting and data-driven!"""
            
            response_text = llm_call(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=800,
            )
        except Exception as e:
            logger.error(f"[copilot] Data analysis suggestion failed: {e}")
            response_text = "I encountered an error while trying to analyze the database. However, I can help you target and launch campaigns for your customers. Tell me who you want to target (e.g. VIP spenders or inactive customers)!"

        history.append({"role": "assistant", "content": response_text})
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": response_text
        }

    # ── CASE C: Campaign Modification / Refinement (1 LLM call) ─────────────────
    campaign_preview = _get_active_campaign_preview(history[:-1])

    # Detect if user is starting a BRAND NEW campaign goal (not modifying existing one)
    # New campaign phrases signal a fresh request, so we skip CASE C entirely
    new_campaign_signals = [
        "win back", "re-engage", "reward vip", "reward our", "target customers",
        "send campaign", "create campaign", "build campaign", "new campaign",
        "inactive for", "haven't ordered", "customers who", "customers inactive",
        "loyal customers", "at-risk customers", "new customers", "onboard",
        "send them", "message them", "reach them", "target them", "campaign for them",
        "send a", "send an", "create a", "build a", "make a", "launch a",
        # Hindi / Hinglish — "send them a message" equivalents
        "inhiko", "inhe", "inko", "unhe", "unko", "inhi",
        "inlogo", "in logo", "sabko", "bas inhe", "sirf inhe",
        "yahi log", "yeh log", "ye log", "msg bejo", "message bejo",
        "bejo", "bhejo", "message karo", "msg karo",
        # New active/target signals
        "target those", "target these", "target this", "target that", 
        "target customer", "target segment", "target cohort", "target people", "target the"
    ]
    is_new_campaign_request = any(sig in user_msg_lower for sig in new_campaign_signals)

    # Detect explicit DB query requests — these always go to CASE D2
    # Even if a campaign is active, "show me"/"give me" phrases query the directory
    explicit_query_signals = ["show me", "give me", "list", "find", "search", "who are", "who is",
                              "tell me about customers", "how many customers", "directory"]
    is_explicit_query = any(sig in user_msg_lower for sig in explicit_query_signals)

    if campaign_preview and not is_new_campaign_request and not is_explicit_query:
        refinement_keywords = [
            "channel", "tone", "whatsapp", "sms", "email", "mail", "text", 
            "formal", "casual", "festive", "polite", "friendly",
            "change", "modify", "update", "regenerate", "rewrite", "different", "redo", "another", "edit", "copy"
        ]
        is_refinement_request = any(w in user_msg_lower for w in refinement_keywords)
        
        # ── CASE C0: Summary request ──────────────────────────────────────────
        summary_keywords = ["summarise", "summarize", "summary", "what is this campaign", "what's this campaign", "tell me about this campaign", "explain this campaign", "what did we do", "what have we done", "overview"]
        is_summary_request = any(kw in user_msg_lower for kw in summary_keywords)
        
        if is_summary_request:
            ctx = _get_conversation_context_summary(history[:-1])
            try:
                response_text = llm_call(
                    messages=[{
                        "role": "user",
                        "content": f"""You are the Nexora AI Campaign Copilot.
The user asked: "{user_message}"

Here is the full conversation context so far:
{ctx}

Active campaign details:
{json.dumps(campaign_preview, indent=2)}

Please write a clear, friendly, structured summary of what we've done in this session.
Include: who we are targeting, what channel is recommended, what the message looks like, and whether it's been launched.
Format it nicely in Markdown with bullet points. Keep it concise but complete."""
                    }],
                    temperature=0.4,
                    max_tokens=600,
                )
            except Exception as e:
                logger.error(f"[copilot] Summary generation failed: {e}")
                audience = campaign_preview.get("audience_count", 0)
                channel = campaign_preview.get("channel", "whatsapp")
                name = campaign_preview.get("campaign_name", "Campaign")
                response_text = f"""**Campaign Summary**

- **Campaign Name:** {name}
- **Target Audience:** {audience} customers
- **Channel:** {channel.title()}
- **Status:** Ready to launch (awaiting your approval)

The message drafts are prepared. Shall I launch it?"""
            
            return {
                "session_id": session_id,
                "steps": [],
                "final_message": response_text
            }
        
        if is_refinement_request:
            channel = campaign_preview.get("channel", "whatsapp")
            tone = "casual"
            
            if "email" in user_msg_lower: channel = "email"
            elif "whatsapp" in user_msg_lower: channel = "whatsapp"
            elif "sms" in user_msg_lower: channel = "sms"
            
            if "formal" in user_msg_lower: tone = "formal"
            elif "casual" in user_msg_lower: tone = "casual"
            elif "festive" in user_msg_lower: tone = "festive"
            
            # Get the original goal
            goal = campaign_preview.get("goal") or "Custom Campaign"
            for msg in history:
                if msg.get("role") == "user" and not any(w in msg.get("content", "").lower() for w in ["launch", "send", "yes", "go ahead", "tone", "channel", "email", "sms", "whatsapp"]):
                    goal = msg.get("content")
                    break
                    
            msg_args = {
                "goal": goal,
                "channel": channel,
                "audience_description": f"{campaign_preview.get('audience_count', 0)} customers matching goal",
                "brand_tone": tone
            }
            # Extract requested variables if specified
            user_tokens = re.findall(r"\{\{[a-zA-Z_]+\}\}", user_message)
            if user_tokens:
                msg_args["requested_variables"] = user_tokens
            msg_result = await execute_tool("generate_message", msg_args, db)
            
            preview_args = {
                "campaign_name": campaign_preview.get("campaign_name", "New Campaign"),
                "segment_filters": campaign_preview.get("segment_filters", {}),
                "audience_count": campaign_preview.get("audience_count", 0),
                "channel": channel,
                "variant_a": msg_result["variant_a"],
                "variant_b": msg_result["variant_b"],
                "channel_reason": f"Adjusted to {channel} based on feedback.",
                "goal": campaign_preview.get("goal")
            }
            preview_result = await execute_tool("preview_campaign", preview_args, db)
            
            history.append({"role": "tool", "tool_call_id": "refinement_msg", "content": json.dumps(msg_result)})
            history.append({"role": "tool", "tool_call_id": "refinement_preview", "content": json.dumps(preview_result)})
            
            final_msg = f"I've updated the campaign message variants to {channel} using a {tone} tone. Please review the updated preview. Shall I launch it?"
            return {
                "session_id": session_id,
                "steps": [msg_result, preview_result],
                "final_message": final_msg
            }
        else:
            # ── CASE C2: General Follow-up (Conversational LangGraph Agent) ──
            from agent.conversational_agent import run_conversational_agent
            try:
                result = await run_conversational_agent(session_id, user_message, db, history)
                # Append steps to history so they persist in session
                for step in result.get("steps", []):
                    step_name = step.get("step")
                    history.append({"role": "tool", "tool_call_id": f"{step_name}_call", "content": json.dumps(step)})
                return result
            except Exception as e:
                logger.error(f"[copilot] Conversational agent failed in Case C2: {e}")
                response_text = f"This campaign targets {campaign_preview.get('audience_count', 0)} customers using {campaign_preview.get('channel', 'whatsapp')}. The message templates are ready. Shall I launch it?"
                return {
                    "session_id": session_id,
                    "steps": [],
                    "final_message": response_text
                }

    # ── CASE D: General Greetings & Simple Questions (1 LLM call max) ────────────
    user_msg_clean = user_message.strip().lower().rstrip("?.,!")
    greetings = {"hi", "hello", "hey", "hola", "yo", "greetings", "good morning", "good afternoon", "good evening", "test", "restart", "namaste", "sup", "what's up", "wassup"}
    
    campaign_keywords = [
        "customer", "segment", "win back", "inactive", "loyal", "spent", "spend", "spending",
        "orders", "ordered", "re-engage", "churn", "vip", "new", "reward", "target", "campaign",
        "send", "mail", "text", "sms", "whatsapp", "email", "discount", "coupon", "purchased",
        "purchase", "buy", "bought", "days", "months", "rupees", "inr", "rs", "₹", "user"
    ]
    has_campaign_intent = any(kw in user_msg_clean for kw in campaign_keywords)
    
    # Summary/recap queries that reference the session but no active campaign
    session_summary_keywords = ["what have we done", "what did we do", "summarise this session", "summarize this session", "what happened", "recap"]
    is_session_summary = any(kw in user_msg_lower for kw in session_summary_keywords)
    
    if is_session_summary:
        ctx = _get_conversation_context_summary(history[:-1])
        try:
            response_text = llm_call(
                messages=[{
                    "role": "user",
                    "content": f"""You are the Nexora AI Campaign Copilot.
The user asked: "{user_message}"

Here is a summary of the conversation so far:
{ctx}

Please write a friendly, structured recap of what happened in this session.
Use Markdown formatting with bullet points for clarity."""
                }],
                temperature=0.4,
                max_tokens=500,
            )
        except Exception as e:
            response_text = "Here's what we've done so far in this session:\n\n- Started the AI Campaign Copilot session\n- No campaigns have been built or launched yet\n\nTell me your campaign goal to get started!"
        
        return {"session_id": session_id, "steps": [], "final_message": response_text}

    is_general_msg = (
        user_msg_clean in greetings or 
        len(user_msg_clean) < 4 or 
        not has_campaign_intent or
        any(user_msg_clean.startswith(q) for q in ["what ", "how ", "who ", "why ", "where ", "can you ", "what's ", "what is "])
    )
    
    if is_general_msg:
        try:
            ctx = _get_conversation_context_summary(history[:-1])
            response_text = llm_call(
                messages=[
                    {"role": "system", "content": "You are the Nexora AI Campaign Copilot for an Indian e-commerce CRM. You strictly help marketers build and launch customer campaigns. Answer greetings warmly, explain your capabilities clearly, and always invite the user to give a campaign goal. STRICT GUARDRAIL: You MUST refuse to answer any questions or requests that are not related to e-commerce campaigns, customer directory searches, segments, or CRM analysis. If the user asks general coding, python, math, or history questions, politely refuse and redirect them back to e-commerce campaigns. Use Markdown for formatting. Use Indian currency (₹) when relevant."},
                    {"role": "user", "content": f"Conversation so far:\n{ctx}\n\nUser now says: {user_message}"}
                ],
                temperature=0.7,
                max_tokens=300,
            )
        except Exception as e:
            logger.error(f"[copilot] Greeting generation failed: {e}")
            response_text = "Hello! I am your AI Campaign Copilot. Tell me your campaign goal (e.g., 'Reward our top VIP spenders'), and I'll assemble the audience, recommend a channel, and draft the message for you."
            
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": response_text
        }

    # ── CASE D2: CRM Directory / Analytics Query (1 LLM call) ───────────────────
    query_keywords = ["top", "recent", "list", "show", "tell me about", "who are", "analytics",
                      "how many", "database", "stats", "loyal", "directory", "give me", "find",
                      "search", "performing"]
    
    # Exclude campaign creation intent — "reward top VIP" means create campaign, not list customers
    campaign_action_words = ["campaign", "launch", "send", "create a", "draft", "template",
                             "reward", "win back", "re-engage", "discount", "offer", "inactive",
                             "% off", "percent off", "message for", "reach out"]
    is_query_request = (
        any(kw in user_msg_lower for kw in query_keywords) and
        not any(kw in user_msg_lower for kw in campaign_action_words)
    ) or is_explicit_query
    
    if is_query_request:
        # Parse sort direction — detect "least"/"worst" for ascending order
        # Use regex word boundaries (\b) to avoid substring matches (e.g. "performing" matching "min")
        sort_order = "asc" if re.search(r"\b(least|lowest|worst|bottom|poor|min|under|low)\b", user_msg_lower) else "desc"
        
        # Parse sorting column
        sort_by = "total_spent"
        if re.search(r"\b(recent|new|registered|joined)\b", user_msg_lower):
            sort_by = "created_at"
        elif re.search(r"\b(order|orders|purchase|purchases|bought)\b", user_msg_lower):
            sort_by = "total_orders"
        elif re.search(r"\b(last\s+order|inactive|activity)\b", user_msg_lower):
            sort_by = "last_order_date"
            
        # Parse limit parameter
        limit = 10
        limit_match = re.search(r"\b(\d+)\b", user_msg_lower)
        if limit_match:
            limit = min(int(limit_match.group(1)), 50)
            
        # Parse tag parameter
        tag = None
        if re.search(r"\b(vip|loyal)\b", user_msg_lower):
            tag = "vip"
        elif re.search(r"\b(new)\b", user_msg_lower):
            tag = "new"
        elif re.search(r"\b(at-risk|at\s+risk)\b", user_msg_lower):
            tag = "at-risk"
            
        # Parse channel preference
        channel = None
        if re.search(r"\b(whatsapp)\b", user_msg_lower):
            channel = "whatsapp"
        elif re.search(r"\b(email|mail)\b", user_msg_lower):
            channel = "email"
        elif re.search(r"\b(sms)\b", user_msg_lower):
            channel = "sms"

        # Store parsed query params in history so "send them" follow-ups can inherit the cohort
        _last_query_params = {
            "sort_by": sort_by, "sort_order": sort_order,
            "limit": limit, "tag": tag, "channel_preference": channel
        }
            
        try:
            from agent.tools import execute_query_customer_directory
            query_args = _last_query_params
            query_result = execute_query_customer_directory(query_args, db)
            
            # Build rich LLM prompt
            prompt = f"""You are the Nexora AI Campaign Copilot.
The user asked: "{user_message}"

I have queried the CRM database and found the following results:
{json.dumps(query_result, indent=2)}

Please write a professional, friendly, and structured response in Markdown:
1. Show the customers in a clean Markdown table with columns for Name, Total Spent (₹), Total Orders, Channel, Tags, and Last Order Date
2. At the end, suggest a brief campaign recommendation for this cohort (1-2 sentences)
3. Offer to build a campaign targeting this cohort

Keep it concise and data-driven. Format currency as ₹X,XXX."""
            
            response_text = llm_call(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=1500,
            )

            # Save exact customer IDs for precise 'send them' targeting
            queried_customer_ids = [c["id"] for c in query_result.get("customers", []) if "id" in c]

            # Store query result + params in history for follow-up context
            history.append({
                "role": "tool",
                "tool_call_id": "query_call",
                "content": json.dumps({
                    "step": "customer_query_results",
                    "query": user_message,
                    "result_summary": f"Returned {query_result['returned_count']} customers sorted by {sort_by} {sort_order}",
                    "cohort_params": _last_query_params,
                    "cohort_customer_ids": queried_customer_ids,  # ← exact IDs for 'send them'
                    "cohort_tag": tag,
                    "cohort_sort_by": sort_by,
                    "cohort_sort_order": sort_order,
                    "cohort_limit": limit
                })
            })
                
        except Exception as e:
            error_str = str(e)
            logger.error(f"[copilot] CRM query execution failed: {e}")
            # Check if this is a rate limit / quota issue
            is_quota_error = any(kw in error_str.lower() for kw in ["429", "quota", "rate", "resource_exhausted"])
            
            if is_quota_error:
                # Try to still show the data locally without LLM formatting
                try:
                    from agent.tools import execute_query_customer_directory
                    query_args = {"sort_by": sort_by, "sort_order": "desc", "limit": limit, "tag": tag, "channel_preference": channel}
                    query_result = execute_query_customer_directory(query_args, db)
                    customers = query_result.get("customers", [])
                    
                    lines = [f"### Top {len(customers)} Customers (sorted by {sort_by.replace('_', ' ').title()})\n"]
                    lines.append("| # | Name | Total Spent | Orders | Channel | Tags | Last Order |")
                    lines.append("|---|------|------------|--------|---------|------|------------|")
                    for idx, c in enumerate(customers, 1):
                        tags = ', '.join(c.get('tags', [])) or 'none'
                        last_order = (c.get('last_order_date') or 'N/A')[:10]
                        lines.append(f"| {idx} | {c['name']} | ₹{c['total_spent']:,.2f} | {c['total_orders']} | {c['channel_preference']} | {tags} | {last_order} |")
                    
                    lines.append(f"\n**Campaign Recommendation:** Add more API keys to GEMINI_KEY_2–5 in `.env` to restore AI-powered insights. The data above is fetched directly from the CRM database.")
                    response_text = "\n".join(lines)
                except Exception as e2:
                    response_text = "⚠️ **API Rate Limit Reached** — The AI quota for today is exhausted. Please add additional API keys (`GEMINI_KEY_2` to `GEMINI_KEY_5`) in the backend `.env` file to enable automatic key rotation and eliminate this issue."
            else:
                response_text = f"I encountered an error while searching the customer directory. Please try again."
            
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": response_text
        }

    # ── CASE E: Brand New Campaign Creation (Conversational LangGraph Agent) ─────
    from agent.conversational_agent import run_conversational_agent
    try:
        result = await run_conversational_agent(session_id, user_message, db, history)
        # Append steps to history so they persist in session
        for step in result.get("steps", []):
            step_name = step.get("step")
            history.append({"role": "tool", "tool_call_id": f"{step_name}_call", "content": json.dumps(step)})
        return result
    except Exception as e:
        logger.error(f"[copilot] Conversational agent failed in Case E: {e}")
        error_msg = f"Failed to build campaign: {str(e)}"
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": error_msg,
            "error": True
        }
