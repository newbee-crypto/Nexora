# backend/agent/tools.py
# Defines OpenAI function-calling tool schemas and their execution logic.
# Each tool has a JSON schema (for the LLM) and an execution function (Python).

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy.orm import Session

from dispatcher import build_segment_query, dispatch_campaign
from models import Campaign, Customer

load_dotenv()

logger = logging.getLogger("crm.agent.tools")

class GeminiKeyRotationManager:
    """
    Manages a pool of up to 5 Gemini API keys (GEMINI_KEY_1..5).
    Automatically rotates to the next key on 429 rate-limit errors (round-robin).
    Thread-safe via a lock.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._keys = self._load_keys()
        self._current_idx = 0
        self._base_url = os.getenv("OPENAI_BASE_URL") or None
        self._model = os.getenv("OPENAI_MODEL", "gemini-2.5-flash")
        logger.info(f"[KeyRotator] Initialized with {len(self._keys)} API key(s) in pool")
    
    def _load_keys(self) -> list[str]:
        """Load all non-empty API keys depending on the active provider."""
        base_url = os.getenv("OPENAI_BASE_URL", "")
        
        # 1. If using Groq (detect via base_url)
        if base_url and "groq.com" in base_url.lower():
            keys = []
            for i in range(1, 6):  # GROQ_KEY_1 through GROQ_KEY_5
                key = os.getenv(f"GROQ_KEY_{i}", "").strip()
                if key:
                    keys.append(key)
            if not keys:
                legacy = os.getenv("OPENAI_API_KEY", "").strip()
                if legacy:
                    keys.append(legacy)
            return keys

        # 2. If using standard Gemini or default
        keys = []
        for i in range(1, 6):  # GEMINI_KEY_1 through GEMINI_KEY_5
            key = os.getenv(f"GEMINI_KEY_{i}", "").strip()
            if key:
                keys.append(key)
        # Fallback to legacy OPENAI_API_KEY if no GEMINI_KEY_N keys defined
        if not keys:
            legacy = os.getenv("OPENAI_API_KEY", "").strip()
            if legacy:
                keys.append(legacy)
        return keys
    
    def _build_client(self, api_key: str) -> OpenAI:
        """Build an OpenAI-compatible client for the given API key."""
        return OpenAI(api_key=api_key, base_url=self._base_url)
    
    def get_client(self) -> OpenAI:
        """Get the current active client."""
        with self._lock:
            if not self._keys:
                raise RuntimeError("No Gemini API keys configured. Add GEMINI_KEY_1 to .env")
            return self._build_client(self._keys[self._current_idx])
    
    def rotate(self) -> OpenAI:
        """Rotate to the next API key and return a new client."""
        with self._lock:
            if len(self._keys) <= 1:
                logger.warning("[KeyRotator] Only 1 key in pool, cannot rotate. Add more GEMINI_KEY_N keys.")
                return self._build_client(self._keys[0])
            self._current_idx = (self._current_idx + 1) % len(self._keys)
            new_key = self._keys[self._current_idx]
            logger.info(f"[KeyRotator] Rotated to key index {self._current_idx} (key ends: ...{new_key[-8:]})")
            return self._build_client(new_key)
    
    def call_with_rotation(self, fn, *args, max_retries: int = None, **kwargs):
        """
        Call fn(client, *args, **kwargs) with automatic key rotation on 429.
        
        fn must accept 'client' as its first argument.
        Tries all keys in the pool before raising the last error.
        Self-heals by removing invalid/403 keys from the pool, and back-off
        sleeps when all keys are rate-limited.
        """
        import time
        max_total_attempts = 30
        last_error = None
        
        for attempt in range(max_total_attempts):
            with self._lock:
                if not self._keys:
                    raise RuntimeError("All Gemini API keys in pool have been disabled due to auth errors.")
            
            client = self.get_client() if attempt == 0 else self.rotate()
            try:
                return fn(client, *args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                
                # ── Auth / Permission Errors (403, 401) ──
                if any(kw in error_str for kw in ["403", "401", "denied", "invalid", "forbidden"]):
                    with self._lock:
                        if self._keys:
                            bad_key = self._keys[self._current_idx]
                            if bad_key in self._keys:
                                logger.error(f"[KeyRotator] Removing invalid key index {self._current_idx} (ends: ...{bad_key[-8:]}) from pool due to: {error_str[:60]}")
                                self._keys.remove(bad_key)
                                if self._keys:
                                    self._current_idx = self._current_idx % len(self._keys)
                                else:
                                    self._current_idx = 0
                    last_error = e
                    continue
                
                # ── Rate Limits (429) / Truncated Responses ──
                elif any(kw in error_str for kw in ["429", "quota", "rate", "resource_exhausted", "truncated"]):
                    logger.warning(f"[KeyRotator] Rate limit or truncated response on key index {self._current_idx} (attempt {attempt + 1}/{max_total_attempts}). Rotating key...")
                    last_error = e
                    
                    # If we've already rotated through all active keys, sleep briefly to let quotas reset
                    with self._lock:
                        num_keys = len(self._keys)
                    if num_keys > 0 and (attempt + 1) % num_keys == 0:
                        sleep_time = 5.0
                        logger.warning(f"[KeyRotator] All {num_keys} keys rate-limited/exhausted. Sleeping for {sleep_time}s before retrying...")
                        time.sleep(sleep_time)
                    continue
                
                # ── Other Errors (raise immediately) ──
                else:
                    raise
        raise last_error


# Singleton key rotation manager — shared across all tool calls
_key_manager = GeminiKeyRotationManager()

# Legacy single client for backward compatibility
openai_client = _key_manager.get_client()

# The model to use for all AI calls in the agent
AGENT_MODEL = os.getenv("OPENAI_MODEL", "gemini-2.5-flash")


def llm_call(messages: list, temperature: float = 0.7, max_tokens: int = 500) -> str:
    """
    Make a single LLM call with automatic key rotation on 429 errors.
    
    This is the PREFERRED way to call the LLM in this codebase.
    It handles key rotation transparently — callers never need to worry
    about rate limits or which key is active.
    
    Returns the text content of the first choice.
    """
    def _do_call(client: OpenAI):
        response = client.chat.completions.create(
            model=AGENT_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        # Check for obvious truncations/incomplete responses from Gemini rate-limiting
        # (e.g. very short and doesn't end with standard ending punctuation)
        stripped = content.strip()
        if 0 < len(stripped) < 60:
            if not stripped[-1] in ('.', '?', '!', '"', '*', ')', '`', '}'):
                raise ValueError(f"Truncated/incomplete response detected from Gemini: '{stripped}'")
        return content
    
    return _key_manager.call_with_rotation(_do_call)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: TOOL JSON SCHEMAS
# These are passed to GPT-4o in the `tools` parameter of every chat.completions.create() call.
# GPT-4o reads these to decide which tool to call and what arguments to pass.
#
# Schema rules (OpenAI function calling format):
#   - "type": "function" — required outer wrapper
#   - "function.name" — must match the Python execution function name exactly
#   - "function.description" — GPT reads this to decide WHEN to call the tool.
#     Write it in plain English. Be specific about what it produces.
#   - "function.parameters" — JSON Schema object defining the arguments
#   - "required" — list of parameter names that MUST be provided
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS = [
    # ── Tool 1: build_segment ─────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "build_segment",
            "description": (
                "Translates a marketer's natural language goal into SQL filter parameters, "
                "queries the customer database, and returns the matching audience. "
                "ALWAYS call this tool first when the marketer states a campaign goal. "
                "Examples: 'win back inactive customers', 'reward VIP buyers', "
                "'convert first-time purchasers'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": (
                            "The marketer's campaign goal in plain English. "
                            "Example: 'Win back customers who haven't ordered in 45 days'"
                        ),
                    }
                },
                "required": ["goal"],
                "additionalProperties": False,
            },
        },
    },

    # ── Tool 2: suggest_channel ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "suggest_channel",
            "description": (
                "Recommends the best delivery channel (WhatsApp, SMS, or Email) "
                "based on audience size and campaign goal. Uses rule-based logic "
                "for fast, explainable recommendations. "
                "Call this AFTER build_segment, using the audience count it returned."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "audience_count": {
                        "type": "integer",
                        "description": "Number of customers in the segment (from build_segment)",
                    },
                    "avg_spend": {
                        "type": "number",
                        "description": "Average total spend across the audience in INR",
                    },
                    "goal": {
                        "type": "string",
                        "description": "The original campaign goal (used for context in rule logic)",
                    },
                },
                "required": ["audience_count", "avg_spend", "goal"],
                "additionalProperties": False,
            },
        },
    },

    # ── Tool 3: generate_message ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "generate_message",
            "description": (
                "Generates two message variants (A and B) for the campaign using GPT-4o, "
                "tailored to the selected channel's constraints. "
                "WhatsApp: conversational, emoji OK, max 1024 chars. "
                "SMS: max 160 chars, no emoji, direct CTA. "
                "Email: subject line + formal body. "
                "Messages include {{name}}, {{last_order_date}}, {{discount_code}} tokens. "
                "Call this AFTER suggest_channel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The campaign goal for message context",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["whatsapp", "sms", "email"],
                        "description": "Delivery channel (determines message constraints)",
                    },
                    "audience_description": {
                        "type": "string",
                        "description": (
                            "Brief description of the target audience. "
                            "Example: '180 customers inactive for 45+ days'"
                        ),
                    },
                    "brand_tone": {
                        "type": "string",
                        "enum": ["casual", "formal", "festive"],
                        "description": "Tone of voice for the message",
                        "default": "casual",
                    },
                },
                "required": ["goal", "channel", "audience_description"],
                "additionalProperties": False,
            },
        },
    },

    # ── Tool 4: preview_campaign ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "preview_campaign",
            "description": (
                "Assembles a campaign preview card for the marketer to review and approve. "
                "This is the APPROVAL GATE — no database records are created yet. "
                "The marketer sees the audience size, channel, and both message variants "
                "before deciding to launch. "
                "Call this AFTER generate_message to present the full campaign plan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "campaign_name": {
                        "type": "string",
                        "description": "Auto-generated or marketer-provided campaign name",
                    },
                    "segment_filters": {
                        "type": "object",
                        "description": "The SQL filter dict from build_segment",
                    },
                    "audience_count": {
                        "type": "integer",
                        "description": "Number of matching customers",
                    },
                    "channel": {
                        "type": "string",
                        "description": "The selected channel",
                    },
                    "variant_a": {
                        "type": "string",
                        "description": "First message variant from generate_message",
                    },
                    "variant_b": {
                        "type": "string",
                        "description": "Second message variant from generate_message",
                    },
                    "channel_reason": {
                        "type": "string",
                        "description": "Why this channel was recommended",
                    },
                },
                "required": [
                    "campaign_name", "segment_filters", "audience_count",
                    "channel", "variant_a", "variant_b",
                ],
                "additionalProperties": False,
            },
        },
    },

    # ── Tool 5: launch_campaign ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "launch_campaign",
            "description": (
                "Creates the Campaign record in the database and triggers async dispatch "
                "to all customers in the segment. "
                "ONLY call this when the marketer explicitly approves the campaign "
                "(says 'launch', 'send it', 'go ahead', 'yes', or clicks the Launch button). "
                "This is irreversible — it immediately starts sending messages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "campaign_name": {
                        "type": "string",
                        "description": "The campaign name",
                    },
                    "goal": {
                        "type": "string",
                        "description": "The original campaign goal",
                    },
                    "segment_filters": {
                        "type": "object",
                        "description": "SQL filter dict from build_segment",
                    },
                    "message_template": {
                        "type": "string",
                        "description": "The chosen message variant (A or B) with {{token}} placeholders",
                    },
                    "channel": {
                        "type": "string",
                        "description": "Delivery channel",
                    },
                },
                "required": [
                    "campaign_name", "goal", "segment_filters",
                    "message_template", "channel",
                ],
                "additionalProperties": False,
            },
        },
    },
    # ── Tool 6: query_customer_directory ──────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "query_customer_directory",
            "description": (
                "Queries the customer CRM directory to retrieve analytics, statistics, or list specific subsets "
                "of customers (e.g. top loyal spenders, recently added customers, segment counts, tag listings). "
                "Use this tool when the marketer asks questions about customers, spend, loyalty, or recent registrations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {
                        "type": "string",
                        "enum": ["total_spent", "total_orders", "last_order_date", "created_at"],
                        "description": "Metric to sort the customer list by. Use 'total_spent' or 'total_orders' for loyalty/VIPs, 'created_at' for recently registered customers.",
                    },
                    "sort_order": {
                        "type": "string",
                        "enum": ["desc", "asc"],
                        "description": "Order of sorting. Default is 'desc'.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of customer records to return. Default is 10, max is 100.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by customer tag (e.g., 'vip', 'new', 'at-risk').",
                    },
                    "channel_preference": {
                        "type": "string",
                        "enum": ["whatsapp", "sms", "email"],
                        "description": "Filter by customer's preferred communication channel.",
                    }
                },
                "required": [],
                "additionalProperties": False,
            }
        }
    }
]

# Create a name → schema lookup for quick access in the copilot loop
TOOLS_BY_NAME = {tool["function"]["name"]: tool for tool in TOOLS}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: TOOL EXECUTION FUNCTIONS
# Each function here corresponds to a tool schema above.
# These are called by the copilot loop when GPT-4o requests a tool call.
# ═══════════════════════════════════════════════════════════════════════════════

async def execute_build_segment(args: dict, db: Session) -> dict:
    """
    Tool 1: Translate natural language goal → SQL filters → customer count.

    TWO-STEP DESIGN:
    Step A: Call GPT-4o with a structured sub-prompt to translate the goal
            into a JSON filter dict. This is a DETERMINISTIC extraction task —
            GPT-4o is good at this because we give it clear examples and output format.
    Step B: Execute the filter dict against the customers table using
            build_segment_query() from dispatcher.py (reuse existing logic).

    WHY a sub-prompt for filter extraction?
    → The main agent loop handles conversation flow. A separate focused sub-call
      for "goal → filters" keeps the extraction logic isolated and testable.
    → We use low temperature (0.1) for this sub-call — we want structured JSON,
      not creative output. Temperature 0 would also work.

    Returns a dict matching the "segment_built" step card format expected by the frontend.
    """
    goal = args["goal"]
    logger.info(f"[tool:build_segment] Translating goal: '{goal}'")

    # ── Sub-call to GPT-4o: goal → filter JSON ────────────────────────────────
    # We send a focused prompt to extract structured filter parameters.
    # The system prompt is carefully crafted to output ONLY valid JSON.
    filter_extraction_prompt = f"""You are a customer segmentation assistant for an Indian e-commerce brand.
Convert the marketer's campaign goal into SQL filter parameters.

Return ONLY a valid JSON object with these optional fields (include only relevant ones):
- "inactive_days": integer — customers whose last order was N+ days ago
- "active_days": integer — customers whose last order was within the last N days
- "min_orders": integer — minimum total orders placed
- "min_spent": float — minimum total spend in INR
- "max_spent": float — maximum total spend in INR (for budget-sensitive segments)
- "tags": array of strings — one or more of ["vip", "new", "at-risk"]

Rules:
- "win back" / "inactive" / "re-engage" → use inactive_days (45 or 60)
- "loyal" / "VIP" / "reward" → use min_spent >= 5000 and tags: ["vip"]
- "new customers" / "first-time" → use tags: ["new"] and min_orders: 1
- "at-risk" → use inactive_days: 30 and tags: ["at-risk"]
- Be conservative: don't add filters not implied by the goal

Marketer's goal: {goal}

Respond with ONLY the JSON object, no markdown, no explanation."""

    try:
        raw_json = llm_call(
            messages=[{"role": "user", "content": filter_extraction_prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        logger.info(f"[tool:build_segment] LLM extracted filters (raw): {raw_json[:100]}")

        # Strip markdown code fences if GPT wraps the JSON in ```json ... ```
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]

        filters = json.loads(raw_json)
        logger.info(f"[tool:build_segment] GPT extracted filters: {filters}")

    except (json.JSONDecodeError, Exception) as e:
        # Fallback: if GPT returns invalid JSON or fails, use a safe default
        # based on simple keyword matching. This makes the tool resilient.
        logger.warning(f"[tool:build_segment] Filter extraction failed ({e}), using keyword fallback")
        filters = _keyword_fallback_filters(goal)

    # ── Execute filters against DB ────────────────────────────────────────────
    try:
        query = build_segment_query(db, filters)
        customers = query.limit(400).all()  # Safety limit — never scan entire table unbounded
        count = len(customers)

        # Compute avg spend for the segment (used by suggest_channel)
        avg_spend = (
            sum(c.total_spent for c in customers) / count
            if count > 0 else 0.0
        )

        # Sample customer names for the preview card (first 3)
        sample_names = [c.name for c in customers[:3]]

        logger.info(f"[tool:build_segment] Segment: {count} customers, avg_spend=₹{round(avg_spend)}")

        return {
            "step": "segment_built",
            "filters": filters,
            "count": count,
            "avg_spend": round(avg_spend, 2),
            "sample_names": sample_names,
            "summary": f"Found {count} customers matching your goal. Average spend: ₹{round(avg_spend):,}.",
        }

    except Exception as e:
        logger.error(f"[tool:build_segment] DB query failed: {e}")
        return {
            "step": "segment_built",
            "filters": filters,
            "count": 0,
            "avg_spend": 0.0,
            "sample_names": [],
            "summary": f"Segment query failed: {e}",
            "error": str(e),
        }


def _keyword_fallback_filters(goal: str) -> dict:
    """
    Simple keyword-based fallback when GPT-4o fails to extract filters.
    Ensures the tool always returns SOMETHING useful rather than crashing.
    """
    goal_lower = goal.lower()
    has_inactive = any(kw in goal_lower for kw in ["inactive", "win back", "re-engage", "haven't ordered"])
    has_active = any(kw in goal_lower for kw in ["active", "bought", "purchased", "within", "last", "recently"]) and not any(kw in goal_lower for kw in ["not", "haven't", "inactive", "win back"])
    days_matches = re.findall(r"(\d+)\s*day", goal_lower)
    
    if days_matches:
        days_val = int(days_matches[-1])
        if has_active:
            return {"active_days": days_val}
        else:
            return {"inactive_days": days_val}
            
    if has_inactive:
        return {"inactive_days": 45, "min_orders": 1}
    elif has_active:
        return {"active_days": 30}
    elif any(kw in goal_lower for kw in ["vip", "loyal", "reward", "top"]):
        return {"min_spent": 5000, "tags": ["vip"]}
    elif any(kw in goal_lower for kw in ["new", "first", "onboard"]):
        return {"tags": ["new"]}
    else:
        return {"inactive_days": 30}


def execute_suggest_channel(args: dict) -> dict:
    """
    Tool 2: Rule-based channel recommendation & Budget Optimizer.

    If a budget_limit is provided in args, runs the greedy budget allocation optimizer:
    - Base cost: Email to everyone (₹0.05). If total email cost > budget, drop bottom customers.
    - Leftover: Upgrade top customers to WhatsApp (₹0.80, diff ₹0.75) first, then SMS (₹0.20, diff ₹0.15).
    Otherwise, falls back to standard heuristics based on audience count and average spend.
    """
    audience_count = args["audience_count"]
    avg_spend = args.get("avg_spend", 0)
    goal = args.get("goal", "").lower()
    budget_limit = args.get("budget_limit")

    # ── Budget Optimizer Simulation Mode ──────────────────────────────────────
    if budget_limit is not None:
        budget = float(budget_limit)
        budget_paise = int(round(budget * 100))
        email_cost_paise = 5
        base_cost_paise = audience_count * email_cost_paise
        
        if base_cost_paise > budget_paise:
            # We can't even afford to send emails to everyone. Drop bottom customers.
            emails = budget_paise // email_cost_paise
            whatsapp = 0
            sms = 0
            dropped = audience_count - emails
            reason = (
                f"Optimized channel allocation to fit within ₹{budget:,.0f} budget limit. "
                f"With ₹0.05 per Email, we can only afford to reach {emails} of the {audience_count} customers. "
                f"The remaining {dropped} customers will be dropped to prevent budget overrun."
            )
        else:
            leftover_paise = budget_paise - base_cost_paise
            # Upgrade to WhatsApp (upgrade cost: 0.80 - 0.05 = 0.75)
            whatsapp = int(min(audience_count, leftover_paise // 75))
            leftover_paise -= whatsapp * 75
            
            # Upgrade remaining to SMS (upgrade cost: 0.20 - 0.05 = 0.15)
            sms = int(min(audience_count - whatsapp, leftover_paise // 15))
            emails = audience_count - whatsapp - sms
            dropped = 0
            reason = (
                f"Optimized channel allocation to fit within ₹{budget:,.0f} budget limit. "
                f"WhatsApp (₹0.80) is allocated to the top {whatsapp} highest-spending customers. "
                f"SMS (₹0.20) is allocated to the next {sms} customers. "
                f"The remaining {emails} customers will receive Emails (₹0.05) to maximize reach."
            )
            
        logger.info(
            f"[tool:suggest_channel] Budget Optimizer: WhatsApp={whatsapp}, "
            f"SMS={sms}, Email={emails}, Dropped={dropped} | Reason: {reason}"
        )
        return {
            "step": "channel_suggested",
            "channel": "optimized",
            "reason": reason,
            "audience_count": audience_count,
            "budget_limit": budget,
            "budget_allocation": {
                "whatsapp": whatsapp,
                "sms": sms,
                "email": emails,
                "dropped": dropped
            }
        }

    # ── User Preference Override ──────────────────────────────────────────────
    # If the user explicitly mentions a channel in their goal prompt, respect it.
    if "email" in goal:
        channel = "email"
        reason = "Selected Email based on your explicit request in the campaign goal."
    elif "whatsapp" in goal:
        channel = "whatsapp"
        reason = "Selected WhatsApp based on your explicit request in the campaign goal."
    elif "sms" in goal or "text message" in goal:
        channel = "sms"
        reason = "Selected SMS based on your explicit request in the campaign goal."
    # ── Rule-based channel selection ──────────────────────────────────────────
    # The rules are intentionally simple and fast. No AI needed here.
    elif audience_count >= 500 or any(kw in goal for kw in ["formal", "invoice", "refund", "policy"]):
        channel = "email"
        reason = (
            f"Email is preferred for large audiences ({audience_count:,} customers). "
            "It allows longer content and formal communication."
        )
    elif audience_count < 500 and avg_spend > 3000:
        # High-value small segment → WhatsApp for personal touch
        channel = "whatsapp"
        reason = (
            f"WhatsApp gives a personal feel for this high-value segment "
            f"(avg spend ₹{avg_spend:,.0f}). Highest open rates in India."
        )
    elif audience_count < 500:
        channel = "whatsapp"
        reason = (
            f"WhatsApp is ideal for re-engagement campaigns with smaller audiences "
            f"({audience_count:,} customers). Delivers 55%+ open rates in India."
        )
    else:
        channel = "sms"
        reason = "SMS as fallback — reliable delivery, no smartphone required."

    logger.info(f"[tool:suggest_channel] Recommended: {channel} — {reason}")

    return {
        "step": "channel_suggested",
        "channel": channel,
        "reason": reason,
        "audience_count": audience_count,
    }


async def execute_generate_message(args: dict) -> dict:
    """
    Tool 3: Generate two message variants using GPT-4o with channel constraints.

    CHANNEL-SPECIFIC CONSTRAINTS (from spec):
        WhatsApp: conversational, emoji OK, max 1024 chars, {{name}} personalization
        SMS:      max 160 chars STRICTLY, no emoji, direct CTA, include opt-out
        Email:    subject line + body, formal structure, HTML-friendly

    We ask GPT-4o to generate BOTH variants in a single call (as JSON) to:
    → Save tokens vs. two separate calls
    → Ensure variants are genuinely different in tone/approach
    → Get char_count in the same response for validation

    HALLUCINATION GUARD:
    We validate that generated messages contain the {{name}} token (GPT sometimes
    forgets). If missing, we inject it. We also validate SMS char count < 160.
    """
    goal = args["goal"]
    channel = args["channel"]
    audience_description = args.get("audience_description", "your customers")
    brand_tone = args.get("brand_tone", "casual")
    discount_percent = args.get("discount_percent")       # e.g. "70"
    min_spend_threshold = args.get("min_spend_threshold") # e.g. "10000"
    requested_variables = args.get("requested_variables") # e.g. ["{{first_name}}", "{{total_spent}}"]

    # Build variable instruction constraint if provided
    var_instruction = ""
    if requested_variables:
        var_instruction = (
            f"\n- You MUST strictly use the following personalization variables in the message drafts: {', '.join(requested_variables)}."
            "\n- IMPORTANT: Integrate these variables naturally into the sentences of the message copy. DO NOT list, dump, or prepend them at the start or end of the message (e.g. do not write '{{total_spent}}{{total_orders}}Hey...'). Instead, integrate them contextually (e.g. 'Since you have placed {{total_orders}} orders and spent a total of {{total_spent}} with us...')."
        )

    # Build channel-specific constraints for the prompt
    channel_constraints = {
        "whatsapp": (
            "- Conversational and warm tone\n"
            "- Use 1-2 relevant emoji (not excessive)\n"
            "- Max 1024 characters per variant\n"
            "- Include {{name}} for personalization\n"
            "- Include {{last_order_date}} naturally\n"
            "- Include {{discount_code}} with a clear CTA\n"
            "- Variant A: win-back angle (we miss you)\n"
            "- Variant B: urgency/offer angle (limited time)"
        ),
        "sms": (
            "- STRICT maximum 160 characters per variant (count carefully!)\n"
            "- No emoji\n"
            "- Start with brand name: 'Nexora:'\n"
            "- Direct CTA with a short link placeholder [LINK]\n"
            "- Include {{name}} (counts toward 160 chars)\n"
            "- Add 'Reply STOP to opt out' at end\n"
            "- Variant A: discount offer\n"
            "- Variant B: product recommendation angle"
        ),
        "email": (
            "- Format: SUBJECT: [subject line] | BODY: [email body]\n"
            "- Professional but warm tone\n"
            "- Subject line: max 60 chars, include {{name}}\n"
            "- Body: 3-4 sentences, include {{last_order_date}} and {{discount_code}}\n"
            "- Clear CTA button text at the end\n"
            "- Variant A: personal win-back from brand founder\n"
            "- Variant B: product-focused recommendation email"
        ),
    }

    # Build specific offer details if provided
    offer_details = ""
    if discount_percent:
        offer_details += f"\n- The offer is a FLAT {discount_percent}% discount. Mention this exact percentage in the message."
    if min_spend_threshold:
        offer_details += f"\n- The offer applies on orders above ₹{int(min_spend_threshold):,}. Mention this minimum spend threshold clearly."
    if offer_details:
        offer_details = "\nOFFER DETAILS (MUST include exactly as specified):" + offer_details

    # ── Optimized Channel Prompt (Generate All 3) ──────────────────────────────
    if channel == "optimized":
        prompt = f"""You are a marketing copywriter for an Indian e-commerce brand.
Generate message variants for WhatsApp, SMS, and Email.

Campaign goal: {goal}
Target audience: {audience_description}
Brand tone: {brand_tone}{offer_details}{var_instruction}

Constraints for each channel:
1. WhatsApp:
   - Conversational and warm tone, 1-2 relevant emojis, max 1024 characters.
   - Include {{name}}, {{last_order_date}}, and {{discount_code}} with a clear CTA.
2. SMS:
   - STRICT maximum 160 characters per variant. No emoji.
   - Start with brand name: 'Nexora:' and end with 'Reply STOP to opt out'.
   - Include {{name}} for personalization.
3. Email:
   - Format: SUBJECT: [subject line] | BODY: [email body]
   - Professional but warm, subject max 60 chars (include {{name}}).
   - Include {{last_order_date}} and {{discount_code}} in body.

Token placeholders to use exactly as-is (they will be replaced with real values at send time):
- {{{{name}}}} — customer's full name (e.g., Naksh Agate)
- {{{{first_name}}}} — customer's first name only (e.g., Naksh) (recommended for casual greetings)
- {{{{last_order_date}}}} — their last order date (e.g., 15 April) (recommended for win-back goals)
- {{{{discount_code}}}} — their personal discount code (e.g., REWARDTEMP01)
- {{{{total_spent}}}} — customer's total spent formatted as currency (e.g., ₹12,450) (highly recommended for VIP upsells/loyalty messaging)
- {{{{total_orders}}}} — total number of orders placed (e.g., 5) (useful for loyalty appreciation)
- {{{{customer_tags}}}} — user-facing tags (e.g., vip, promising)

AI PERSONALIZATION GUIDELINES:
- Dynamically choose and insert the most relevant variables for the goal.
- For VIP or loyalty goals, include {{{{total_spent}}}} or {{{{total_orders}}}} to thank them for their customer value (e.g., "Since you've spent {{{{total_spent}}}} on our brand...").
- For re-engaging inactive customers, mention their {{{{last_order_date}}}} and provide a {{{{discount_code}}}}.
- Always try to insert a personalized variable contextually in the copies.

Return ONLY a JSON object with this exact structure (do not add any extra fields, no Markdown formatting):
{{
  "whatsapp_a": "whatsapp message text here",
  "whatsapp_b": "whatsapp message text here",
  "sms_a": "sms message text here",
  "sms_b": "sms message text here",
  "email_a": "SUBJECT: [subject line] | BODY: [email body]",
  "email_b": "SUBJECT: [subject line] | BODY: [email body]"
}}
No markdown, no explanation — just the JSON."""
    else:
        # Standard Single Channel Prompt
        constraints = channel_constraints.get(channel, channel_constraints["whatsapp"])
        if var_instruction:
            constraints += f"\n{var_instruction}"
        prompt = f"""You are a marketing copywriter for an Indian e-commerce brand.
Generate two message variants for a {channel.upper()} campaign.

Campaign goal: {goal}
Target audience: {audience_description}
Brand tone: {brand_tone}{offer_details}

Channel constraints:
{constraints}

Token placeholders to use exactly as-is (they will be replaced with real values at send time):
- {{{{name}}}} — customer's full name (e.g., Naksh Agate)
- {{{{first_name}}}} — customer's first name only (e.g., Naksh) (recommended for casual greetings)
- {{{{last_order_date}}}} — their last order date (e.g., 15 April) (recommended for win-back goals)
- {{{{discount_code}}}} — their personal discount code (e.g., REWARDTEMP01)
- {{{{total_spent}}}} — customer's total spent formatted as currency (e.g., ₹12,450) (highly recommended for VIP upsells/loyalty messaging)
- {{{{total_orders}}}} — total number of orders placed (e.g., 5) (useful for loyalty appreciation)
- {{{{customer_tags}}}} — user-facing tags (e.g., vip, promising)

AI PERSONALIZATION GUIDELINES:
- Dynamically choose and insert the most relevant variables for the goal.
- For VIP or loyalty goals, include {{{{total_spent}}}} or {{{{total_orders}}}} to thank them for their customer value (e.g., "Since you've spent {{{{total_spent}}}} on our brand...").
- For re-engaging inactive customers, mention their {{{{last_order_date}}}} and provide a {{{{discount_code}}}}.
- Always try to insert a personalized variable contextually in the copies.

Return ONLY a JSON object with this exact structure:
{{
  "variant_a": "message text here",
  "variant_b": "message text here",
  "char_count_a": integer,
  "char_count_b": integer
}}
No markdown, no explanation — just the JSON."""

    try:
        raw = llm_call(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1000 if channel == "optimized" else 800,
        )
        raw = raw.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)

        if channel == "optimized":
            whatsapp_a = result.get("whatsapp_a", "")
            whatsapp_b = result.get("whatsapp_b", "")
            sms_a = result.get("sms_a", "")
            sms_b = result.get("sms_b", "")
            email_a = result.get("email_a", "")
            email_b = result.get("email_b", "")

            # Personalization checks
            if "{{name}}" not in whatsapp_a and "{{first_name}}" not in whatsapp_a: whatsapp_a = "Hi {{name}}, " + whatsapp_a
            if "{{name}}" not in whatsapp_b and "{{first_name}}" not in whatsapp_b: whatsapp_b = "Hi {{name}}, " + whatsapp_b
            if "{{name}}" not in sms_a and "{{first_name}}" not in sms_a: sms_a = "Hi {{name}}, " + sms_a
            if "{{name}}" not in sms_b and "{{first_name}}" not in sms_b: sms_b = "Hi {{name}}, " + sms_b
            if "{{name}}" not in email_a and "{{first_name}}" not in email_a: email_a = "SUBJECT: Special offer for {{name}}! | BODY: " + email_a
            if "{{name}}" not in email_b and "{{first_name}}" not in email_b: email_b = "SUBJECT: Special offer for {{name}}! | BODY: " + email_b

            # Truncate SMS if LLM exceeded SMS limit
            if len(sms_a) > 160: sms_a = sms_a[:157] + "..."
            if len(sms_b) > 160: sms_b = sms_b[:157] + "..."

            # Store variant_a and variant_b as serialized JSON strings holding channel breakdowns
            variant_a = json.dumps({"whatsapp": whatsapp_a, "sms": sms_a, "email": email_a})
            variant_b = json.dumps({"whatsapp": whatsapp_b, "sms": sms_b, "email": email_b})
            char_count = [len(whatsapp_a), len(whatsapp_b)]
        else:
            variant_a = result.get("variant_a", "")
            variant_b = result.get("variant_b", "")

            # ── Hallucination guard: ensure {{name}} or {{first_name}} is in messages ───────────────
            if "{{name}}" not in variant_a and "{{first_name}}" not in variant_a:
                variant_a = "Hi {{name}}, " + variant_a
            if "{{name}}" not in variant_b and "{{first_name}}" not in variant_b:
                variant_b = "Hi {{name}}, " + variant_b

            # ── SMS strict length validation ──────────────────────────────────────
            if channel == "sms":
                if len(variant_a) > 160:
                    variant_a = variant_a[:157] + "..."
                if len(variant_b) > 160:
                    variant_b = variant_b[:157] + "..."
            char_count = [len(variant_a), len(variant_b)]

        logger.info(
            f"[tool:generate_message] Generated {channel} variants successfully."
        )

        return {
            "step": "message_generated",
            "channel": channel,
            "variant_a": variant_a,
            "variant_b": variant_b,
            "char_count": char_count,
        }

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[tool:generate_message] GPT call failed: {e}")
        return _generate_dynamic_fallback_messages(goal, channel, brand_tone, args=args)


def _generate_dynamic_fallback_messages(goal: str, channel: str, brand_tone: str = "casual", args: dict = None) -> dict:
    """
    Generate context-specific fallback message drafts locally using keywords in the goal.
    Ensures that when the Gemini API hits rate limits, the drafts are still dynamic
    and relevant to the user's campaign goal (e.g. free gift vs. VIP reward vs. win back).
    Utilizes a pool of varied templates to ensure variety.
    """
    import json
    if channel == "optimized":
        # Recursively generate local fallbacks for each channel type
        wa_result = _generate_dynamic_fallback_messages(goal, "whatsapp", brand_tone, args)
        sms_result = _generate_dynamic_fallback_messages(goal, "sms", brand_tone, args)
        email_result = _generate_dynamic_fallback_messages(goal, "email", brand_tone, args)
        
        variant_a = json.dumps({
            "whatsapp": wa_result["variant_a"],
            "sms": sms_result["variant_a"],
            "email": email_result["variant_a"]
        })
        variant_b = json.dumps({
            "whatsapp": wa_result["variant_b"],
            "sms": sms_result["variant_b"],
            "email": email_result["variant_b"]
        })
        return {
            "step": "message_generated",
            "channel": "optimized",
            "variant_a": variant_a,
            "variant_b": variant_b,
            "char_count": [len(wa_result["variant_a"]), len(wa_result["variant_b"])],
            "warning": "Rate limit fallback activated (local templates used for all channels)."
        }

    goal_lower = goal.lower()
    import re
    import random
    
    # Use discount_percent from args first (explicitly extracted by copilot)
    # Then fall back to regex extraction from goal text
    explicit_discount = args.get("discount_percent") if args else None
    explicit_min_spend = args.get("min_spend_threshold") if args else None
    
    if explicit_discount:
        discount_val = explicit_discount
    else:
        discount_match = re.search(r"(\d+)\s*(?:%|percent|per cent)", goal_lower)
        if not discount_match:
            discount_match = re.search(r"discount\s*(?:of|for|at)?\s*(\d+)", goal_lower)
        if not discount_match:
            discount_match = re.search(r"(\d+)\s*(?:discount|off)", goal_lower)
        discount_val = discount_match.group(1) if discount_match else None

    # Build min-spend clause for messages if provided
    min_spend_clause = f" on orders above \u20b9{int(explicit_min_spend):,}" if explicit_min_spend else ""
    
    # 1. Determine campaign theme — but if explicit discount given, override "gift" theme
    if explicit_discount:
        theme = "discount"   # has specific % offer — use discount templates
    elif any(kw in goal_lower for kw in ["gift", "free", "present"]):
        theme = "gift"
    elif any(kw in goal_lower for kw in ["vip", "loyal", "reward", "top", "spent", "spend"]):
        theme = "vip"
    elif any(kw in goal_lower for kw in ["inactive", "win back", "re-engage", "miss you", "haven't ordered", "churn"]):
        theme = "winback"
    else:
        theme = "generic"

    # 2. Define pool of templates by channel and theme
    if channel == "whatsapp":
        if theme == "discount":
            d = discount_val or "10"
            pool_a = [
                f"Hi {{{{name}}}}! 🎁 Thank you for shopping with us! Here's a special gift — flat {d}% OFF{min_spend_clause} using code {{{{discount_code}}}}. Last order: {{{{last_order_date}}}}.  Limited time!",
                f"Hey {{{{name}}}}! 🛍️ We appreciate you! Enjoy FLAT {d}% off{min_spend_clause} on your next order. Use code {{{{discount_code}}}} at checkout. Offer expires soon! Last purchase: {{{{last_order_date}}}}.  ",
                f"Hi {{{{name}}}}! 🎉 Exciting news! We're giving you {d}% OFF{min_spend_clause} as a thank you. Apply code {{{{discount_code}}}} now. Last ordered: {{{{last_order_date}}}}. Don't miss out!"
            ]
            pool_b = [
                f"Hey {{{{name}}}}! 💥 FLAT {d}% discount{min_spend_clause} just for you! Redeem code {{{{discount_code}}}} before it expires. Your last order was {{{{last_order_date}}}}.  Grab it now!",
                f"Hello {{{{name}}}}! 🌟 Exclusive {d}% off deal{min_spend_clause} waiting for you! Use {{{{discount_code}}}} on checkout. Last purchase: {{{{last_order_date}}}}. Hurry, limited time!",
                f"Hi {{{{name}}}}! 🔥 {d}% OFF{min_spend_clause} — your special reward! Code: {{{{discount_code}}}}. Last order: {{{{last_order_date}}}}. Shop now and save big!"
            ]
        elif theme == "gift":
            pool_a = [
                "Hi {{name}}! 🎁 As one of our top customers, we have a special free gift waiting for you on your next order! Use code {{discount_code}} at checkout to claim it. Last order: {{last_order_date}}.",
                "Hey {{name}}! 🎁 You've unlocked a special surprise. Claim your free gift on your next purchase by using code {{discount_code}} at checkout. Last order: {{last_order_date}}.",
                "Hi {{name}}! 🌟 To thank you for your support, we have a free gift ready for you. Apply code {{discount_code}} on your next checkout! Last order: {{last_order_date}}."
            ]
            pool_b = [
                "Hey {{name}}! We love having you shop with us. Here is a free gift for your loyalty! Use {{discount_code}} on your next order before it expires. Last purchase: {{last_order_date}}.",
                "Hello {{name}}! Ready for a reward? Enjoy a free gift on us with code {{discount_code}} on your next order today. Last order date: {{last_order_date}}.",
                "Hey {{name}}! 💖 A special token of appreciation: use code {{discount_code}} for a free gift with your next shop. Last purchase was {{last_order_date}}."
            ]
        elif theme == "vip":
            pool_a = [
                "Hi {{name}}! 🌟 Thank you for being a VIP customer. Enjoy an exclusive 20% off your next order with code {{discount_code}}. Last purchase: {{last_order_date}}.",
                "Hey {{name}}! 🌟 Exclusive VIP treatment: Get 20% off your next order with code {{discount_code}} at checkout. Last order: {{last_order_date}}.",
                "Hi {{name}}! 👑 As a VIP member, enjoy 20% off our new collections. Use code {{discount_code}} today. Last ordered on {{last_order_date}}."
            ]
            pool_b = [
                "Hey {{name}}! We appreciate your loyalty. Here's a special VIP discount: {{discount_code}} for 15% off. Valid for a limited time! Last order: {{last_order_date}}.",
                "Hello {{name}}! 🌟 Thank you for shopping frequently. Enjoy 15% off your next cart with VIP code {{discount_code}}. Last order: {{last_order_date}}.",
                "Hey {{name}}! 💎 Just for you: 15% off your next purchase using code {{discount_code}} at checkout. Last purchase: {{last_order_date}}."
            ]
        elif theme == "winback":
            pool_a = [
                "Hi {{name}}, we miss you! It's been a while since your last order on {{last_order_date}}. Use code {{discount_code}} for 15% off your next purchase.",
                "Hey {{name}}! We've missed having you around. Your last order was on {{last_order_date}}. We'd love to welcome you back with code {{discount_code}} for 15% off!",
                "Hi {{name}}! 💙 It has been a while since your last shop on {{last_order_date}}. Here is a special 15% discount code {{discount_code}} to help you get started again."
            ]
            pool_b = [
                "Hey {{name}}! We noticed you haven't shopped in a bit. Last ordered on {{last_order_date}}. Here is 10% off with code {{discount_code}} to welcome you back!",
                "Hi {{name}}! Ready to refresh your wardrobe? We noticed your last purchase was on {{last_order_date}}. Use code {{discount_code}} to get 10% off your next checkout today!",
                "Hey {{name}}! ⏰ Limited time offer: Enjoy 10% off your next purchase with code {{discount_code}}. Your last order was on {{last_order_date}}. Don't miss out!"
            ]
        else:
            pool_a = [
                "Hi {{name}}! Check out our latest collection. Use code {{discount_code}} for 10% off your next order. Last purchase: {{last_order_date}}.",
                "Hey {{name}}! Fresh new arrivals have landed! Explore them today and get 10% off with code {{discount_code}}. Last order: {{last_order_date}}.",
                "Hi {{name}}! 👗 Upgrade your style with our newly launched items. Get 10% off using code {{discount_code}} now. Last ordered on {{last_order_date}}."
            ]
            pool_b = [
                "Hey {{name}}! We have exciting new arrivals. Get 15% off your purchase with code {{discount_code}} today. Last order: {{last_order_date}}.",
                "Hello {{name}}! Special treats inside: Take 15% off your next cart items using code {{discount_code}}. Last purchase: {{last_order_date}}.",
                "Hey {{name}}! Ready for a shopping spree? Enjoy 15% off with code {{discount_code}} on any item today! Last order: {{last_order_date}}."
            ]

    elif channel == "sms":
        # Strictly under 160 characters
        if theme == "gift":
            pool_a = [
                "Nexora: Hi {{name}}, get a free gift on your next order! Use code {{discount_code}}. Last order: {{last_order_date}}. Reply STOP to opt out",
                "Nexora: Hey {{name}}! Free gift surprise awaits on your next cart! Redeem code: {{discount_code}}. Reply STOP to opt out",
                "Nexora: Hi {{name}}, thank you for loyalty. Claim free gift with code {{discount_code}} on next shop. Reply STOP to opt out"
            ]
            pool_b = [
                "Nexora: Hey {{name}}! Claim your exclusive free gift using code {{discount_code}} on your next purchase. Reply STOP to opt out",
                "Nexora: Hello {{name}}! Exclusive free gift is yours with code {{discount_code}}. Redeemed at checkout today. Reply STOP to opt out",
                "Nexora: Hey {{name}}! A loyalty gift is waiting. Enter code {{discount_code}} on your next order. Reply STOP to opt out"
            ]
        elif theme == "vip":
            pool_a = [
                "Nexora: Hi {{name}}, enjoy VIP-only 20% off your next purchase. Use code {{discount_code}}. Reply STOP to opt out",
                "Nexora: Hey {{name}}! Special VIP access: enjoy 20% off your next checkout with code {{discount_code}}. Reply STOP to opt out",
                "Nexora: Hi {{name}}! VIP rewards are live: use code {{discount_code}} for 20% off your order. Reply STOP to opt out"
            ]
            pool_b = [
                "Nexora: Hey {{name}}! Thank you for your loyalty. Get 15% off with code {{discount_code}}. Reply STOP to opt out",
                "Nexora: Hello {{name}}! Enjoy 15% off your next cart items. Code: {{discount_code}}. Limited period only. Reply STOP to opt out",
                "Nexora: Hey {{name}}! Just for loyal buyers: enjoy 15% off with code {{discount_code}}. Reply STOP to opt out"
            ]
        elif theme == "winback":
            pool_a = [
                "Nexora: Hi {{name}}, we miss you! Use code {{discount_code}} for 15% off your next order. Last purchase: {{last_order_date}}. Reply STOP to opt out",
                "Nexora: Hey {{name}}! It has been a while since your order on {{last_order_date}}. Use code {{discount_code}} for 15% off. Reply STOP to opt out",
                "Nexora: Hi {{name}}, we miss having you shop. Get 15% off with code {{discount_code}} on your next checkout! Reply STOP to opt out"
            ]
            pool_b = [
                "Nexora: Hey {{name}}! We want you back. Get 10% off using code {{discount_code}} today. Reply STOP to opt out",
                "Nexora: Hi {{name}}, ready to shop again? Enjoy 10% off with code {{discount_code}} today. Reply STOP to opt out",
                "Nexora: Hey {{name}}! Missed our new styles? Enjoy 10% off with code {{discount_code}}. Reply STOP to opt out"
            ]
        else:
            pool_a = [
                "Nexora: Hi {{name}}, new arrivals are here! Use code {{discount_code}} for 10% off. Reply STOP to opt out",
                "Nexora: Hey {{name}}! Check out our fresh collection today. Use code {{discount_code}} for 10% off. Reply STOP to opt out",
                "Nexora: Hi {{name}}! Upgrade your style. Save 10% on your next order with code {{discount_code}}. Reply STOP to opt out"
            ]
            pool_b = [
                "Nexora: Hey {{name}}! Special offer for you: 15% off with code {{discount_code}}. Reply STOP to opt out",
                "Nexora: Hello {{name}}! Enjoy 15% off your cart items using code {{discount_code}} today. Reply STOP to opt out",
                "Nexora: Hey {{name}}! Time to save: take 15% off your next checkout with code {{discount_code}}. Reply STOP to opt out"
            ]

    else:  # email
        if theme == "gift":
            pool_a = [
                "SUBJECT: A free gift for you, {{name}}! 🎁 | BODY: Hi {{name}},\n\nWe want to thank you for shopping with us! Since you have ordered more than 3 times, you have unlocked a free gift. Use code {{discount_code}} on your next order. Last purchase: {{last_order_date}}.\n\nClaim Gift",
                "SUBJECT: Surprise gift waiting for {{name}}! 🎁 | BODY: Hey {{name}},\n\nYou are one of our top customers! As a thank you, we've prepared a special gift. Use code {{discount_code}} on your next checkout. Last purchase: {{last_order_date}}.\n\nRedeem Gift"
            ]
            pool_b = [
                "SUBJECT: Claim your exclusive free gift, {{name}}! | BODY: Hello {{name}},\n\nYou are one of our VIP customers! We've added a free gift to your account. Use code {{discount_code}} to redeem it on your next purchase. Last order: {{last_order_date}}.\n\nShop Now",
                "SUBJECT: Loyalty reward unlocked, {{name}}! | BODY: Hi {{name}},\n\nThank you for shopping at Nexora! We've added a special loyalty reward to your next cart. Simply enter code {{discount_code}} at checkout to get your free gift. Last order: {{last_order_date}}.\n\nView Cart"
            ]
        elif theme == "vip":
            pool_a = [
                "SUBJECT: Exclusive VIP Reward for {{name}}! 🌟 | BODY: Hi {{name}},\n\nThank you for being one of our most valued customers. We're happy to offer you 20% off your next purchase. Use code {{discount_code}} at checkout. Last order: {{last_order_date}}.\n\nUnlock Reward",
                "SUBJECT: VIP 20% Discount for {{name}}! | BODY: Hello {{name}},\n\nYou're in our top tier! As a thank you, enjoy 20% off your next order. Enter code {{discount_code}} at checkout today. Last order was on {{last_order_date}}.\n\nShop VIP Collection"
            ]
            pool_b = [
                "SUBJECT: Thank you for your loyalty, {{name}} | BODY: Hello {{name}},\n\nAs a token of our appreciation for your continued support, here is a special offer. Use code {{discount_code}} for 15% off your next order. Last order: {{last_order_date}}.\n\nRedeem Offer",
                "SUBJECT: Exclusive 15% Offer for {{name}} | BODY: Hi {{name}},\n\nWe're so grateful for your loyalty. Enjoy 15% off your next purchase with code {{discount_code}}. Last order: {{last_order_date}}.\n\nRedeem Now"
            ]
        elif theme == "winback":
            pool_a = [
                "SUBJECT: We miss you, {{name}}! Here's 15% off 💙 | BODY: Hi {{name}},\n\nIt has been a while since you last ordered on {{last_order_date}}. We'd love to welcome you back with a special 15% discount. Use code {{discount_code}}.\n\nCome Back Now",
                "SUBJECT: We've missed you, {{name}}! | BODY: Hello {{name}},\n\nThings aren't the same without you! Your last order was on {{last_order_date}}. We'd love to welcome you back with code {{discount_code}} for 15% off.\n\nClaim Your Code"
            ]
            pool_b = [
                "SUBJECT: Hey {{name}}, your favorite items miss you! | BODY: Hello {{name}},\n\nCome back and see what's new! Enjoy 10% off your next order with code {{discount_code}}. Last order: {{last_order_date}}.\n\nBrowse Collection",
                "SUBJECT: A special welcome back offer for {{name}}! | BODY: Hi {{name}},\n\nIt's been a while! Check out our new arrivals and enjoy 10% off your next purchase. Code: {{discount_code}}. Last order: {{last_order_date}}.\n\nShop New Arrivals"
            ]
        else:
            pool_a = [
                "SUBJECT: Special offer for {{name}}! | BODY: Hi {{name}},\n\nCheck out our latest collection and enjoy a special 10% discount on your next order. Use code {{discount_code}}.\n\nShop Now",
                "SUBJECT: Check out our new arrivals, {{name}}! | BODY: Hello {{name}},\n\nWe have exciting updates! Take 10% off your next purchase with code {{discount_code}} and refresh your style. Last purchase: {{last_order_date}}.\n\nBrowse Now"
            ]
            pool_b = [
                "SUBJECT: New arrivals just for you, {{name}} | BODY: Hello {{name}},\n\nWe've added new items you might love. Use code {{discount_code}} for 15% off your purchase. Last order: {{last_order_date}}.\n\nView Collection",
                "SUBJECT: Enjoy 15% off today, {{name}}! | BODY: Hi {{name}},\n\nGet ready for a wardrobe upgrade. Use code {{discount_code}} at checkout to get 15% off your next cart items. Last order: {{last_order_date}}.\n\nRedeem 15% Discount"
            ]

    # 3. Select templates randomly
    variant_a = random.choice(pool_a)
    variant_b = random.choice(pool_b)

    if discount_val:
        discount_str = f"{discount_val}%"
        variant_a = re.sub(r"\b(?:10|15|20)%", discount_str, variant_a)
        variant_b = re.sub(r"\b(?:10|15|20)%", discount_str, variant_b)

    return {
        "step": "message_generated",
        "channel": channel,
        "variant_a": variant_a,
        "variant_b": variant_b,
        "char_count": [len(variant_a), len(variant_b)],
        "warning": f"Used local dynamic fallback messages for theme '{theme}' (discount: {discount_str if discount_val else 'default'})",
    }


def execute_preview_campaign(args: dict) -> dict:
    """
    Tool 4: Assemble campaign preview card — NO database writes.

    This is a pure data assembly function. It takes all the information
    gathered by tools 1-3 and packages it into a preview card that the
    frontend renders with a "Launch Campaign" button.

    WHY no DB writes here?
    → The marketer hasn't approved yet. They might say "change the tone" or
      "use email instead". No records should exist until they explicitly launch.
    → The preview card IS the approval gate. Clicking "Launch" calls launch_campaign.

    This function is intentionally simple — it's a coordinator, not a worker.
    """
    return {
        "step": "campaign_preview",
        "campaign_name": args.get("campaign_name", "New Campaign"),
        "segment_filters": args.get("segment_filters", {}),
        "audience_count": args.get("audience_count", 0),
        "channel": args.get("channel", "whatsapp"),
        "variant_a": args.get("variant_a", ""),
        "variant_b": args.get("variant_b", ""),
        "channel_reason": args.get("channel_reason", ""),
        "ready_to_launch": True,  # Signal to frontend to show the Launch button
    }


async def execute_launch_campaign(args: dict, db: Session, background_tasks) -> dict:
    """
    Tool 5: Create Campaign in DB and trigger async dispatch.

    This is the ONLY tool that writes to the database and has side effects.
    It's separated from preview_campaign to enforce the approval gate.

    FLOW:
    1. Create Campaign record (status='launched')
    2. Count the actual segment size (may differ from preview count if data changed)
    3. Commit to DB
    4. Add dispatch_campaign to BackgroundTasks → triggers async message sending
    5. Return campaign_id and queued count to GPT-4o for its final summary

    WHY not call POST /campaigns/{id}/launch internally?
    → That would be an HTTP round-trip to ourselves (localhost → localhost).
    → We have direct access to the DB session and BackgroundTasks here.
    → Direct Python function calls are simpler, faster, and avoid network overhead.
    """
    logger.info(f"[tool:launch_campaign] Launching campaign: '{args.get('campaign_name')}'")

    # ── Create Campaign record ────────────────────────────────────────────────
    # Count actual segment size before creating the campaign
    actual_count = build_segment_query(db, args["segment_filters"]).count()

    if actual_count == 0:
        raise ValueError(
            f"No customers match the segment filters: {args['segment_filters']}. "
            "Please adjust your segment filters to target at least 1 customer before launching."
        )

    campaign = Campaign(
        name=args["campaign_name"],
        goal=args["goal"],
        segment_filters=args["segment_filters"],
        segment_size=actual_count,
        message_template=args["message_template"],
        channel=args["channel"],
        status="launched",
        launched_at=datetime.now(timezone.utc),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    logger.info(
        f"[tool:launch_campaign] Campaign created: id={campaign.id[:8]} "
        f"size={actual_count} channel={campaign.channel}"
    )

    # ── Trigger async dispatch via BackgroundTasks ────────────────────────────
    # This schedules dispatch_campaign to run AFTER the HTTP response is sent.
    # By the time the marketer sees "campaign launched", messages are already
    # queuing up in the background.
    background_tasks.add_task(dispatch_campaign, campaign.id)

    return {
        "step": "campaign_launched",
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "channel": campaign.channel,
        "communications_queued": actual_count,
        "summary": (
            f"Campaign '{campaign.name}' launched! "
            f"Sending {actual_count} {campaign.channel} messages now. "
            f"Track delivery at /campaigns/{campaign.id}/stats"
        ),
    }


def execute_query_customer_directory(args: dict, db: Session) -> dict:
    """
    Retrieve customer listings and analytics from the database.
    Supports sorting by spent, orders, dates, and filtering by tags/channels.
    """
    sort_by = args.get("sort_by", "total_spent")
    sort_order = args.get("sort_order", "desc")
    limit = min(int(args.get("limit", 10)), 100)
    tag = args.get("tag")
    channel = args.get("channel_preference")
    
    from sqlalchemy import text
    import json
    
    query = db.query(Customer)
    
    # Apply channel filter
    if channel:
        query = query.filter(Customer.channel_preference == channel.lower())
        
    # Apply tag filter (tags stored as JSON column)
    if tag:
        if db.bind.dialect.name == "sqlite":
            query = query.filter(
                text("exists (select 1 from json_each(customers.tags) where value = :tag_val)").bindparams(
                    tag_val=tag
                )
            )
        else:
            query = query.filter(
                text("tags::jsonb @> :tag_val").bindparams(
                    tag_val=json.dumps([tag])
                )
            )
        
    # Apply sorting
    sort_col = getattr(Customer, sort_by, Customer.total_spent)
    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())
        
    # Fetch records
    customers = query.limit(limit).all()
    
    # Format response list
    results = []
    for c in customers:
        results.append({
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "channel_preference": c.channel_preference,
            "total_orders": c.total_orders,
            "total_spent": c.total_spent,
            "tags": c.tags,
            "last_order_date": c.last_order_date.isoformat() if c.last_order_date else None,
            "created_at": c.created_at.isoformat() if c.created_at else None
        })
        
    # Generate some quick summary stats of this query for context
    total_db_count = db.query(Customer).count()
    
    return {
        "step": "customer_query_results",
        "query_parameters": {
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit,
            "tag": tag,
            "channel_preference": channel
        },
        "total_directory_size": total_db_count,
        "returned_count": len(results),
        "customers": results
    }


# ── Tool Dispatcher ────────────────────────────────────────────────────────────

async def execute_tool(
    tool_name: str,
    tool_args: dict,
    db: Session,
    background_tasks=None,
) -> dict:
    """
    Route a tool call from GPT-4o to the correct execution function.

    This is the DISPATCH TABLE for tool execution. The copilot loop calls
    this function with the tool name and arguments from GPT-4o's response.

    Args:
        tool_name: Name of the tool GPT-4o wants to call
        tool_args: Arguments parsed from GPT-4o's JSON string
        db: SQLAlchemy Session (for DB-accessing tools)
        background_tasks: FastAPI BackgroundTasks (for launch_campaign)

    Returns:
        Dict result that will be serialized and sent back to GPT-4o as a tool result.
        Also contains "step" key for the frontend step card type.
    """
    logger.info(f"[execute_tool] Executing tool: {tool_name} with args: {tool_args}")

    if tool_name == "build_segment":
        return await execute_build_segment(tool_args, db)

    elif tool_name == "suggest_channel":
        return execute_suggest_channel(tool_args)  # sync, no await needed

    elif tool_name == "generate_message":
        return await execute_generate_message(tool_args)

    elif tool_name == "preview_campaign":
        return execute_preview_campaign(tool_args)  # sync, pure assembly

    elif tool_name == "launch_campaign":
        if background_tasks is None:
            raise ValueError("launch_campaign requires BackgroundTasks context")
        return await execute_launch_campaign(tool_args, db, background_tasks)

    elif tool_name == "query_customer_directory":
        return execute_query_customer_directory(tool_args, db)

    else:
        logger.error(f"[execute_tool] Unknown tool requested: {tool_name}")
        return {
            "step": "error",
            "error": f"Unknown tool '{tool_name}'. Valid tools: {list(TOOLS_BY_NAME.keys())}",
        }
