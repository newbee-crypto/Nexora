import os
import re
import json
import logging
from typing import Optional, List, Sequence, Union
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from agent.tools import llm_call, execute_tool
from dispatcher import build_segment_query

logger = logging.getLogger(__name__)

# ── Pydantic Schema for Slot Extraction ───────────────────────────────────────
class SegmentFiltersSlot(BaseModel):
    active_days: Optional[int] = None
    inactive_days: Optional[int] = None
    min_orders: Optional[int] = None
    min_spent: Optional[float] = None
    tags: Optional[List[str]] = None
    is_sufficient: bool = False
    reasoning: str = ""

# ── LangGraph Agent State ─────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: List[dict]
    accumulated_filters: dict
    clarification_needed: bool
    final_output: dict

# ── Slots Extractor Prompt ────────────────────────────────────────────────────
SLOTS_EXTRACTOR_PROMPT = """You are a customer segmentation assistant for an Indian e-commerce brand.
Analyze the user's conversation history and their latest message to extract and accumulate target segment filters.

Fill in the following fields in the JSON object:
- "active_days": integer or null (target customers who bought within the last N days)
- "inactive_days": integer or null (target customers who haven't ordered in N+ days)
- "min_orders": integer or null (minimum total orders)
- "min_spent": float or null (minimum spend in INR)
- "tags": array of strings or null (e.g. ["vip", "new", "rfm_at_risk"])

Rules:
1. Preserve existing filters from the history if the user hasn't explicitly changed or overridden them.
2. If the user clarifies a parameter (e.g. "active in last 7 days" after saying "attract my active customers"), update that specific slot (e.g. "active_days" = 7).
3. "is_sufficient": boolean. Set to true ONLY if we have at least one clear, concrete parameter (like active_days, inactive_days, tags, or spend limit) to query the database. Set to false if the goal is vague (e.g., "attract my old customer" or "retain my customer") and lacks numeric/tag specs.
4. "reasoning": string. Provide a short description of what filters were found, or what crucial parameter is missing.

Respond with ONLY a valid JSON object matching the schema. Do NOT wrap in markdown code blocks, do not explain."""

# ── Node 1: Analyze user input and extract slots ─────────────────────────────
def extract_original_goal(messages: List[dict]) -> str:
    """
    Scans the conversation history forward to find the first user message
    that represents the core campaign request (not a simple greeting or launch command).
    """
    campaign_keywords = [
        "customer", "segment", "win back", "inactive", "loyal", "spent", "spend", "spending",
        "orders", "ordered", "re-engage", "churn", "vip", "new", "reward", "target", "campaign",
        "send", "mail", "text", "sms", "whatsapp", "email", "discount", "coupon", "purchased",
        "purchase", "buy", "bought", "days", "months", "rupees", "inr", "rs", "₹", "sale", "off", "offer"
    ]
    
    # First, scan for any user message that looks like a campaign goal
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            content_lower = content.lower()
            if len(content) > 15 and any(kw in content_lower for kw in campaign_keywords):
                # Make sure it's not a simple correction/refinement (e.g. starting with "only", "include")
                if not any(content_lower.startswith(prefix) for prefix in ["only ", "just ", "include ", "change ", "update ", "min ", "inactive "]):
                    return content

    # Fallback to the first user message that isn't a greeting
    greetings = {"hi", "hello", "hey", "hola", "yo", "greetings", "restart", "namaste"}
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            if content.lower() not in greetings:
                return content
                
    # Ultimate fallback to the latest user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
            
    return ""


# ── Node 1: Analyze user input and extract slots ─────────────────────────────
def analyze_user_input(state: AgentState) -> AgentState:
    messages = state["messages"]
    logger.info("[conversational_agent] Node: analyze_user_input")

    # Get user message
    user_msg = messages[-1].get("content", "") if messages else ""

    # Retrieve current filters from the last segment_built step in the history
    current_filters = {}
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            try:
                content = json.loads(msg.get("content", "{}"))
                if content.get("step") == "segment_built":
                    current_filters = content.get("filters", {})
                    logger.info(f"[conversational_agent] Found previous filters in history: {current_filters}")
                    break
            except Exception:
                continue

    # Check if the deterministic parser detects cohort context carryover or sufficient filters
    from agent.copilot import parse_goal_to_filters
    # Call with use_defaults=False to avoid overriding with defaults
    parsed_filters = parse_goal_to_filters(user_msg, messages, use_defaults=False)
    
    # Check if there is any instruction to clear/remove filters (which requires LLM reasoning)
    has_clear_signal = any(kw in user_msg.lower() for kw in ["anything", "clear", "remove", "no limit", "reset", "everyone", "any limit", "no orders", "no spent"])
    
    if parsed_filters and not has_clear_signal and ("customer_ids" in parsed_filters or any(k in parsed_filters for k in ["active_days", "inactive_days", "min_orders", "min_spent", "tags"])):
        # Merge parsed_filters with current_filters
        merged_filters = {**current_filters, **parsed_filters}
        logger.info(f"[conversational_agent] Deterministic parser extracted filters: {parsed_filters}. Merged: {merged_filters}")
        state["accumulated_filters"] = merged_filters
        state["clarification_needed"] = False
        return state

    # Combine message history as context for the LLM
    context = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Skip internal tool execution logs from the prompt context to save tokens
        if role != "tool" and content:
            context.append(f"{role.upper()}: {content}")
            
    # Inject current filters into the prompt to maintain state and allow modifications/clearing
    prompt_with_filters = f"""{SLOTS_EXTRACTOR_PROMPT}

Current accumulated filters (before this message): {json.dumps(current_filters)}

Instructions for slot-filling updates:
- If the user specifies a change, update the corresponding slot.
- If the user says a filter can be anything / no limit / all / any (e.g. 'min orders can be anything' or 'include everyone'), set that slot to null to clear it.
- Keep all other existing filters unless the user explicitly requested to change or remove them.
- DO NOT extract filters from copywriting promotional offers (e.g. 'buy 2 get 3', 'buy 1 get 1'), discount percentages (e.g. '40% off'), or tag filters from event names (e.g. 'new season sale').

Conversation history:
""" + "\n".join(context)
    
    try:
        raw_json = llm_call(
            messages=[{"role": "user", "content": prompt_with_filters}],
            temperature=0.1,
            max_tokens=300
        ).strip()
        
        # Clean markdown wrappers if present
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
        
        extracted = json.loads(raw_json.strip())
        logger.info(f"[conversational_agent] Extracted slots from LLM: {extracted}")
    except Exception as e:
        logger.error(f"[conversational_agent] Slot extraction failed: {e}, falling back.")
        extracted = {
            "active_days": None,
            "inactive_days": None,
            "min_orders": None,
            "min_spent": None,
            "tags": None,
            "is_sufficient": False,
            "reasoning": "Failed to parse query, need clarification."
        }
        # Fallback: keep existing filters if extraction failed
        for k, v in current_filters.items():
            extracted[k] = v
        extracted["is_sufficient"] = len(current_filters) > 0

    # Build filters dictionary by starting with current_filters, 
    # updating with extracted values, and removing keys explicitly set to null
    filters = dict(current_filters)
    for key in ["active_days", "inactive_days", "min_orders", "min_spent", "tags"]:
        if key in extracted:
            val = extracted[key]
            if val is None:
                if key in filters:
                    del filters[key]
            else:
                filters[key] = val

    state["accumulated_filters"] = filters
    state["clarification_needed"] = not extracted.get("is_sufficient", False) and len(filters) == 0
    return state

# ── Node 2: Ask user for clarification ────────────────────────────────────────
def clarify_missing_slots(state: AgentState) -> AgentState:
    logger.info("[conversational_agent] Node: clarify_missing_slots")
    messages = state["messages"]
    filters = state["accumulated_filters"]

    # Generate a context-aware clarifying question
    clarify_prompt = f"""You are Nexora AI, the Campaign Copilot for an Indian e-commerce brand.
The user wants to launch a campaign, but the segmentation criteria is vague.
Current filters extracted: {json.loads(json.dumps(filters))}

Write a friendly, polite, and brief message in English (do NOT use Hinglish or Hindi) explaining what we need to build the target segment.
Ask the user to clarify:
- If they want active customers (e.g. bought in the last 7 days) or inactive customers (e.g. inactive for 30+ days).
- Any specific spend or order count limits they would prefer.
Keep the output short and direct (max 2-3 sentences)."""

    try:
        question = llm_call(
            messages=[{"role": "user", "content": clarify_prompt}],
            temperature=0.6,
            max_tokens=200
        ).strip()
    except Exception:
        question = "I understand you want to launch a campaign, but I need some details. Do you want to target active customers (e.g. bought in the last 7 days) or inactive customers (e.g. 30 days inactive)?"

    state["final_output"] = {
        "session_id": "conversational",
        "steps": [],
        "final_message": question
    }
    return state

def generate_campaign_name(goal: str, filters: dict) -> str:
    """
    Generates a descriptive campaign name based on the target segment filters and campaign goal.
    """
    goal_lower = goal.lower()
    
    # Check for specific tags
    tags = filters.get("tags", [])
    if tags:
        # Match RFM segments
        if "rfm_champions" in tags:
            return "Champion Customers Appreciation"
        if "rfm_loyal" in tags:
            return "Loyal Shoppers Engagement"
        if "rfm_at_risk" in tags or "at-risk" in tags:
            return "At-Risk Customers Win-Back"
        if "rfm_about_to_sleep" in tags:
            return "Re-engage Dormant Shoppers"
        if "rfm_hibernating" in tags:
            return "Reactivate Hibernating Customers"
        if "new" in tags:
            return "New Customer Welcome Campaign"
        if "vip" in tags:
            return "VIP Spenders Loyalty Campaign"

    # Check for inactivity days
    inactive_days = filters.get("inactive_days")
    if inactive_days is not None:
        return f"{inactive_days}-Day Inactive Customers Win-Back"
        
    # Check for activity days
    active_days = filters.get("active_days")
    if active_days is not None:
        return f"{active_days}-Day Active Shoppers Campaign"

    # Check for spend or order counts
    min_spent = filters.get("min_spent")
    min_orders = filters.get("min_orders")
    if min_spent is not None and min_orders is not None:
        return f"Premium Buyers Promo (₹{int(min_spent):,}+ Spend)"
    if min_spent is not None:
        return f"High-Value Shoppers Promo (₹{int(min_spent):,}+)"
    if min_orders is not None:
        return f"Frequent Buyers Reward ({min_orders}+ Orders)"

    # Fallback to analyzing keywords in the goal
    if "vip" in goal_lower or "loyal" in goal_lower:
        return "VIP Customers Loyalty Reward"
    if "inactive" in goal_lower or "win back" in goal_lower or "win-back" in goal_lower or "churn" in goal_lower:
        return "Shoppers Win-Back Campaign"
    if "new" in goal_lower or "welcome" in goal_lower or "first" in goal_lower:
        return "New Customers onboarding Welcome"
        
    return f"Targeted Customer Campaign"

# ── Node 3: Execute Campaign Workflow ──────────────────────────────────────────
async def execute_campaign_workflow(state: AgentState, db) -> AgentState:
    logger.info("[conversational_agent] Node: execute_campaign_workflow")
    messages = state["messages"]
    filters = state["accumulated_filters"]
    
    # Extract the original campaign goal from history to preserve copywriting and offer details
    original_goal = extract_original_goal(messages)
    logger.info(f"[conversational_agent] Extracted original campaign goal: '{original_goal}'")
    
    # Step 1: Query database to count matching audience
    try:
        query = build_segment_query(db, filters)
        customers = query.limit(400).all()
        count = len(customers)
        avg_spent = sum(c.total_spent for c in customers) / count if count > 0 else 0.0
        sample_names = [c.name for c in customers[:3]]
        
        segment_result = {
            "step": "segment_built",
            "filters": filters,
            "count": count,
            "avg_spend": round(avg_spent, 2),
            "sample_names": sample_names,
            "summary": f"Found {count} customers matching your goal. Average spend: ₹{round(avg_spent):,}.",
        }
    except Exception as e:
        logger.error(f"[conversational_agent] Query builder failed: {e}")
        segment_result = {
            "step": "segment_built",
            "filters": filters,
            "count": 0,
            "avg_spend": 0.0,
            "sample_names": [],
            "summary": f"Segment query failed: {e}",
            "error": str(e)
        }
        count = 0
        avg_spent = 0.0

    # Step 2: Suggest channel using original_goal
    channel_args = {
        "audience_count": count,
        "avg_spend": avg_spent,
        "goal": original_goal
    }
    if "budget_limit" in filters:
        channel_args["budget_limit"] = filters["budget_limit"]
        
    channel_result = await execute_tool("suggest_channel", channel_args, db)
    channel = channel_result.get("channel", "whatsapp")

    # Step 3: Generate copywriting message drafts using original_goal
    # Check for custom requested variables/tokens from original_goal
    user_tokens = re.findall(r"\{\{[a-zA-Z_]+\}\}", original_goal)
    
    msg_args = {
        "goal": original_goal,
        "channel": channel,
        "audience_description": segment_result["summary"]
    }
    if user_tokens:
        msg_args["requested_variables"] = user_tokens
        
    msg_result = await execute_tool("generate_message", msg_args, db)

    # Step 4: Extract campaign name
    campaign_name = generate_campaign_name(original_goal, filters)

    # Step 5: Render preview using original_goal
    preview_args = {
        "campaign_name": campaign_name,
        "segment_filters": filters,
        "audience_count": count,
        "channel": channel,
        "variant_a": msg_result["variant_a"],
        "variant_b": msg_result["variant_b"],
        "channel_reason": channel_result["reason"],
        "goal": original_goal
    }
    preview_result = await execute_tool("preview_campaign", preview_args, db)

    steps = [segment_result, channel_result, msg_result, preview_result]
    summary_msg = f"I have built a campaign targeting {count} customers. I recommend using {channel} based on the audience size. Shall I launch this campaign?"

    state["final_output"] = {
        "session_id": "conversational",
        "steps": steps,
        "final_message": summary_msg
    }
    return state

# ── Main Conversational Agent Runner ──────────────────────────────────────────
async def run_conversational_agent(session_id: str, user_message: str, db, history: List[dict]) -> dict:
    """
    Executes a turn of the conversational agent using the LangGraph design.
    """
    # Initialize state
    state = AgentState(
        messages=history,
        accumulated_filters={},
        clarification_needed=True,
        final_output={}
    )

    # Run Node 1: Analyze user input
    state = analyze_user_input(state)

    # Route based on sufficiency
    if state["clarification_needed"]:
        state = clarify_missing_slots(state)
    else:
        state = await execute_campaign_workflow(state, db)

    return state["final_output"]
