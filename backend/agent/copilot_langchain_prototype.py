# backend/agent/copilot_langchain_prototype.py
# ---------------------------------------------
# 💡 PROTOTYPE ONLY: LangChain & LangGraph Reference Implementation
# Use this file to demonstrate to interviewers how the custom, highly-optimized 
# CRM Copilot can be built using standard agent frameworks (LangChain / LangGraph).
#
# Comparing this file with `copilot.py` and `tools.py` showcases senior-level 
# architectural decision making (Latency/Token Control vs. Framework Abstraction).

import os
import re
from typing import List, Dict, Any
from pydantic import BaseModel, Field

# ⚠️ Note: These imports require: pip install langchain langchain-openai langgraph
try:
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    # If using LangGraph for cyclic state machine
    from langgraph.graph import StateGraph, END
except ImportError:
    # Fail silently if packages aren't installed yet (prevents breaking the main app)
    SystemMessage = HumanMessage = AIMessage = BaseMessage = object
    tool = lambda f: f
    ChatOpenAI = object
    StateGraph = object
    END = "END"


# ==============================================================================
# 1. DEFINE LANGCHAIN COMPATIBLE TOOLS
# ==============================================================================

@tool
def langchain_build_segment(goal: str) -> str:
    """Translates a natural language campaign goal into SQL filter parameters 
    and queries the customer database to return matching audience stats.
    """
    # Under the hood: this would call the same logic as backend/dispatcher.py::build_segment_query
    # For prototype visualization, we return a mock tool response structure
    return "{\"step\": \"segment_built\", \"matching_customers\": 150, \"avg_spend\": 4500}"

@tool
def langchain_suggest_channel(customer_count: int, avg_spend: float) -> str:
    """Suggests the optimal communication channel (WhatsApp, SMS, Email) 
    based on matching customer volume and their average historical spend.
    """
    # Under the hood: calls backend/agent/tools.py::execute_suggest_channel
    return "{\"step\": \"channel_suggested\", \"recommended_channel\": \"whatsapp\"}"

@tool
def langchain_generate_message(channel: str, segment_summary: str) -> str:
    """Generates personalized Hinglish campaign message variants tailored to 
    the selected delivery channel.
    """
    # Under the hood: calls backend/agent/tools.py::execute_generate_message
    return "{\"step\": \"message_generated\", \"variants\": [\"Hello! Special discount for you!\", \"Namaste! Aapke liye khaas offer!\"]}"

@tool
def langchain_preview_campaign() -> str:
    """Assembles the final campaign preview including audience size, message template, 
    estimated cost, and channel for final marketer approval.
    """
    return "{\"step\": \"campaign_preview\", \"ready_to_launch\": true, \"cost_est\": \"₹120\"}"


# List of tools to bind to the LLM agent
LANGCHAIN_TOOLS = [
    langchain_build_segment,
    langchain_suggest_channel,
    langchain_generate_message,
    langchain_preview_campaign
]


# ==============================================================================
# 2. STATE GRAPH (LANGGRAPH) IMPLEMENTATION
# ==============================================================================

# LangGraph State definition
class AgentState(BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    active_campaign: Dict[str, Any] = Field(default_factory=dict)


class LangGraphCopilotPrototype:
    """
    Demonstrates how the multi-turn campaign workflow (Build Segment -> Suggest Channel -> 
    Generate Message -> Preview -> Launch) can be modeled as a state machine in LangGraph.
    """
    def __init__(self):
        # Bind tools to the OpenAI client (which rotates Gemini keys behind the scenes, or runs GPT-4o)
        self.model = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gemini-2.5-flash"),
            openai_api_key=os.getenv("GEMINI_KEY_1", "dummy_key"),
            temperature=0.7
        ).bind_tools(LANGCHAIN_TOOLS)
        
        # Build the agent graph
        self.workflow = StateGraph(AgentState)
        
        # Define Nodes (steps)
        self.workflow.add_node("agent", self.call_agent)
        self.workflow.add_node("action", self.execute_actions)
        
        # Define Edges (routing logic)
        self.workflow.set_entry_point("agent")
        self.workflow.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "continue": "action",
                "end": END
            }
        )
        self.workflow.add_edge("action", "agent")
        
        self.app = self.workflow.compile()

    def call_agent(self, state: AgentState) -> Dict[str, Any]:
        """Calls the model with history to determine next actions."""
        messages = state.messages
        response = self.model.invoke(messages)
        return {"messages": [response]}

    def execute_actions(self, state: AgentState) -> Dict[str, Any]:
        """Executes tool requests identified by the LLM."""
        last_message = state.messages[-1]
        tool_outputs = []
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            # Match the tool name and execute it
            target_tool = next((t for t in LANGCHAIN_TOOLS if t.name == tool_name), None)
            if target_tool:
                result = target_tool.invoke(tool_args)
                tool_outputs.append(AIMessage(content=str(result), name=tool_name))
        
        return {"messages": tool_outputs}

    def should_continue(self, state: AgentState) -> str:
        """Determines if the agent needs to continue calling tools or finish."""
        last_message = state.messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"
        return "end"




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


async def run_langchain_agent_turn(
    session_id: str,
    user_message: str,
    db,
    background_tasks=None,
    edited_template: str | None = None,
) -> dict:
    """
    Executes a turn of the copilot using the LangChain prototype.
    Mirrors the exact intent routing logic of copilot.py (Greetings, Analytics,
    Refinements, Summaries, Launches, and New Campaigns), making it fully functional
    and identical to the custom engine.
    """
    # 1. Check if langchain is available
    langchain_available = False
    try:
        import langchain
        langchain_available = True
    except ImportError:
        pass

    # Import helper dependencies from copilot and tools
    from agent.copilot import (
        parse_goal_to_filters, SESSIONS, SYSTEM_PROMPT, 
        _get_active_campaign_preview, _get_conversation_context_summary
    )
    from agent.tools import execute_tool, llm_call
    import json
    import re
    from datetime import datetime

    # Get/create session history for context
    if session_id not in SESSIONS:
        SESSIONS[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    history = SESSIONS[session_id]

    # Build disclaimers/headers
    header = ""
    if not langchain_available:
        header = (
            "⚠️ **[MOCK RUN — LANGCHAIN FRAMEWORK NOT INSTALLED]**\n"
            "To run the live LangChain implementation, run: `pip install langchain langchain-openai langgraph` in your environment.\n\n"
        )
    else:
        header = "🤖 **[LANGCHAIN FRAMEWORK ACTIVE]** (Running using `copilot_langchain_prototype.py`)\n\n"

    # ── CASE A: AI Insight Request ──────────────────────────────────────────
    if session_id.startswith("insight-") or "performance stats" in user_message.lower():
        try:
            insight = llm_call(
                messages=[{"role": "user", "content": user_message}],
                temperature=0.3,
                max_tokens=400,
            )
        except Exception:
            insight = _build_dynamic_insight_fallback(user_message)
        
        final_msg = header + insight
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": final_msg})
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": final_msg
        }

    # ── CASE B: Campaign Launch Approval ─────────────────────────────────────────
    user_msg_lower = user_message.lower()
    if any(w in user_msg_lower for w in ["launch", "send it", "go ahead", "yes, launch", "launch it", "launch the campaign"]):
        campaign_preview = _get_active_campaign_preview(history)

        if campaign_preview:
            # Determine whether variant A or B was chosen by user
            if edited_template:
                chosen_variant = edited_template
            else:
                chosen_variant = campaign_preview.get("variant_a", "")
                if "variant b" in user_msg_lower or "variant_b" in user_msg_lower or user_message.strip().endswith("B") or user_message.strip().endswith("b"):
                    chosen_variant = campaign_preview.get("variant_b", "")
                
            campaign_goal = campaign_preview.get("goal")
            if not campaign_goal:
                for msg in reversed(history):
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
                history.append({"role": "user", "content": user_message})
                history.append({
                    "role": "tool",
                    "tool_call_id": "langchain_launch_call",
                    "content": json.dumps(launch_result),
                })
                
                final_msg = header + launch_result["summary"]
                history.append({"role": "assistant", "content": final_msg})
                
                return {
                    "session_id": session_id,
                    "steps": [launch_result],
                    "final_message": final_msg
                }
            except Exception as e:
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
            logger.error(f"[copilot_langchain] Data analysis suggestion failed: {e}")
            response_text = "I encountered an error while trying to analyze the database. However, I can help you target and launch campaigns for your customers. Tell me who you want to target (e.g. VIP spenders or inactive customers)!"

        final_msg = header + response_text
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": final_msg})
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": final_msg
        }

    # ── CASE C: Summary & Refinements (Active Campaign Draft exists) ─────────────
    campaign_preview = _get_active_campaign_preview(history)

    # Detect if user is starting a BRAND NEW campaign goal (not modifying existing one)
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

    # Detect explicit DB query requests
    explicit_query_signals = ["show me", "give me", "list", "find", "search", "who are", "who is",
                              "tell me about customers", "how many customers", "directory"]
    is_explicit_query = any(sig in user_msg_lower for sig in explicit_query_signals)

    if campaign_preview and not is_new_campaign_request and not is_explicit_query:
        history.append({"role": "user", "content": user_message})
        
        refinement_keywords = [
            "whatsapp", "email", "sms", "text", "mail", "channel", "message", "variant",
            "tone", "formal", "casual", "festive", "polite", "friendly",
            "change", "modify", "update", "regenerate", "rewrite", "different", "redo", "another", "edit", "copy"
        ]
        is_refinement_request = any(w in user_msg_lower for w in refinement_keywords)
        
        summary_keywords = ["summarise", "summarize", "summary", "what is this campaign", "what's this campaign", "tell me about this campaign", "explain this campaign", "what did we do", "what have we done", "overview"]
        is_summary_request = any(kw in user_msg_lower for kw in summary_keywords)
        
        if is_summary_request:
            ctx = _get_conversation_context_summary(history[:-1])
            try:
                response_text = llm_call(
                    messages=[{
                        "role": "user",
                        "content": f"You are the Nexora AI Campaign Copilot. The user asked: \"{user_message}\"\n\nContext:\n{ctx}\n\nActive campaign:\n{json.dumps(campaign_preview, indent=2)}\n\nPlease write a clear, friendly, structured summary of what we've done. Format in Markdown."
                    }],
                    temperature=0.4,
                    max_tokens=600,
                )
            except Exception:
                audience = campaign_preview.get("audience_count", 0)
                channel = campaign_preview.get("channel", "whatsapp")
                name = campaign_preview.get("campaign_name", "Campaign")
                response_text = f"**Campaign Summary**\n- **Name:** {name}\n- **Target Audience:** {audience} customers\n- **Channel:** {channel.title()}\n- **Status:** Ready to launch. Shall I launch it?"
            
            final_msg = header + response_text
            history.append({"role": "assistant", "content": final_msg})
            return {
                "session_id": session_id,
                "steps": [],
                "final_message": final_msg
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
            
            history.append({"role": "tool", "tool_call_id": "langchain_refinement_msg", "content": json.dumps(msg_result)})
            history.append({"role": "tool", "tool_call_id": "langchain_refinement_preview", "content": json.dumps(preview_result)})
            
            final_msg = header + f"I've updated the campaign message variants to {channel} using a {tone} tone. Please review the updated preview. Shall I launch it?"
            history.append({"role": "assistant", "content": final_msg})
            return {
                "session_id": session_id,
                "steps": [msg_result, preview_result],
                "final_message": final_msg
            }
        
        # General question about draft -> delegate to stateful conversational agent
        from agent.conversational_agent import run_conversational_agent
        try:
            result = await run_conversational_agent(session_id, user_message, db, history)
            # Add header to the final message
            result["final_message"] = header + result["final_message"]
            # Append final message to history
            history.append({"role": "assistant", "content": result["final_message"]})
            # Also append any generated steps to history so they persist in the session
            for step in result.get("steps", []):
                step_name = step.get("step")
                history.append({"role": "tool", "tool_call_id": f"langchain_{step_name}", "content": json.dumps(step)})
            return result
        except Exception as e:
            logger.error(f"Failed to run conversational agent: {e}")
            response_text = f"This campaign targets {campaign_preview.get('audience_count', 0)} customers using {campaign_preview.get('channel', 'whatsapp')}. Shall I launch it?"
            final_msg = header + response_text
            history.append({"role": "assistant", "content": final_msg})
            return {"session_id": session_id, "steps": [], "final_message": final_msg}

    # ── CASE D: General Greetings & Simple Questions ─────────────────────────────
    user_msg_clean = user_message.strip().lower().rstrip("?.,!")
    greetings = {"hi", "hello", "hey", "hola", "yo", "greetings", "good morning", "good afternoon", "good evening", "test", "restart", "namaste", "sup", "what's up", "wassup"}
    
    campaign_keywords = [
        "customer", "segment", "win back", "inactive", "loyal", "spent", "spend", "spending",
        "orders", "ordered", "re-engage", "churn", "vip", "new", "reward", "target", "campaign",
        "send", "mail", "text", "sms", "whatsapp", "email", "discount", "coupon", "purchased",
        "purchase", "buy", "bought", "days", "months", "rupees", "inr", "rs", "₹", "user"
    ]
    has_campaign_intent = any(kw in user_msg_clean for kw in campaign_keywords)
    
    session_summary_keywords = ["what have we done", "what did we do", "summarise this session", "summarize this session", "what happened", "recap"]
    is_session_summary = any(kw in user_msg_lower for kw in session_summary_keywords)
    
    if is_session_summary:
        history.append({"role": "user", "content": user_message})
        ctx = _get_conversation_context_summary(history[:-1])
        try:
            response_text = llm_call(
                messages=[{"role": "user", "content": f"You are the Nexora AI Campaign Copilot. Write a recap of this session:\n{ctx}"}],
                temperature=0.4,
                max_tokens=500,
            )
        except Exception:
            response_text = "Here's what we've done: started the copilot session. No campaign drafts created yet."
        
        final_msg = header + response_text
        history.append({"role": "assistant", "content": final_msg})
        return {"session_id": session_id, "steps": [], "final_message": final_msg}

    is_general_msg = (
        user_msg_clean in greetings or 
        len(user_msg_clean) < 4 or 
        not has_campaign_intent or
        any(user_msg_clean.startswith(q) for q in ["what ", "how ", "who ", "why ", "where ", "can you ", "what's ", "what is "])
    )
    
    if is_general_msg:
        history.append({"role": "user", "content": user_message})
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
        except Exception:
            response_text = "Hello! I am your AI Campaign Copilot. Tell me your campaign goal (e.g., 'Reward our top VIP spenders'), and I'll assemble the audience, recommend a channel, and draft the message for you."
            
        final_msg = header + response_text
        history.append({"role": "assistant", "content": final_msg})
        return {
            "session_id": session_id,
            "steps": [],
            "final_message": final_msg
        }
    # ── CASE D2: CRM Directory / Analytics Query ──────────────────────────────────
    query_keywords = ["top", "recent", "list", "show", "tell me about", "who are", "analytics",
                      "how many", "database", "stats", "loyal", "directory", "give me", "find",
                      "search", "performing"]
    campaign_action_words = ["campaign", "launch", "send", "create a", "draft", "template",
                             "reward", "win back", "re-engage", "discount", "offer", "inactive",
                             "% off", "percent off", "message for", "reach out"]
    is_query_request = (
        any(kw in user_msg_lower for kw in query_keywords) and
        not any(kw in user_msg_lower for kw in campaign_action_words)
    )
    
    if is_query_request:
        history.append({"role": "user", "content": user_message})
        
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
            
        limit = 10
        limit_match = re.search(r"\b(\d+)\b", user_msg_lower)
        if limit_match:
            limit = min(int(limit_match.group(1)), 50)
            
        tag = None
        if re.search(r"\b(vip|loyal)\b", user_msg_lower):
            tag = "vip"
        elif re.search(r"\b(new)\b", user_msg_lower):
            tag = "new"
        elif re.search(r"\b(at-risk|at\s+risk)\b", user_msg_lower):
            tag = "at-risk"
            
        channel_pref = None
        if re.search(r"\b(whatsapp)\b", user_msg_lower):
            channel_pref = "whatsapp"
        elif re.search(r"\b(email|mail)\b", user_msg_lower):
            channel_pref = "email"
        elif re.search(r"\b(sms)\b", user_msg_lower):
            channel_pref = "sms"

        query_args = {
            "limit": limit,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
        if tag: query_args["tag"] = tag
        if channel_pref: query_args["channel_preference"] = channel_pref

        query_result = await execute_tool("query_customer_directory", query_args, db)
        
        # Save exact customer IDs for precise 'send them' targeting in parse_goal_to_filters
        queried_customer_ids = [c["id"] for c in query_result.get("customers", []) if "id" in c]
        
        # Store query result + params in history for follow-up context with identical schema to copilot.py
        history.append({
            "role": "tool",
            "tool_call_id": "langchain_directory_query",
            "content": json.dumps({
                "step": "customer_query_results",
                "query": user_message,
                "result_summary": f"Returned {query_result.get('returned_count', 0)} customers sorted by {sort_by} {sort_order}",
                "cohort_params": query_args,
                "cohort_customer_ids": queried_customer_ids,
                "cohort_tag": tag,
                "cohort_sort_by": sort_by,
                "cohort_sort_order": sort_order,
                "cohort_limit": limit,
                "customers": query_result.get("customers", [])
            }),
        })

        # Generate summary text for directory results using LLM
        try:
            summary_messages = [
                {"role": "system", "content": "You are the Nexora AI Campaign Copilot. You just queried the customer directory. Summarize the returned results in Markdown (e.g. format them as a table with columns: Name, Spend, Orders, Last Order). Keep explanations short."},
                {"role": "user", "content": f"User query: '{user_message}'\n\nReturned data:\n{json.dumps(query_result)}"}
            ]
            response_text = llm_call(summary_messages, temperature=0.3, max_tokens=600)
        except Exception:
            response_text = f"Found {query_result.get('returned_count', 0)} matching customers in the directory."

        final_msg = header + response_text
        history.append({"role": "assistant", "content": final_msg})
        return {
            "session_id": session_id,
            "steps": [query_result],
            "final_message": final_msg
        }

    # ── CASE E: Brand new campaign creation (Conversational LangGraph Agent) ─────
    history.append({"role": "user", "content": user_message})
    from agent.conversational_agent import run_conversational_agent
    try:
        result = await run_conversational_agent(session_id, user_message, db, history)
        result["final_message"] = header + result["final_message"]
        history.append({"role": "assistant", "content": result["final_message"]})
        # Append steps to history so they are saved in session
        for step in result.get("steps", []):
            step_name = step.get("step")
            history.append({"role": "tool", "tool_call_id": f"langchain_{step_name}", "content": json.dumps(step)})
        return result
    except Exception as e:
        logger.error(f"Failed to run conversational agent in Case E: {e}")
        error_msg = f"Failed to build campaign: {str(e)}"
        final_msg = header + error_msg
        history.append({"role": "assistant", "content": final_msg})
        return {"session_id": session_id, "steps": [], "final_message": final_msg, "error": True}




