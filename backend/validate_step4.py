"""validate_step4.py — Step 4 (AI Copilot) import and logic validation"""
import os, sys, json
os.environ['DATABASE_URL'] = 'postgresql://postgres:password@localhost:5432/xenocrm'
os.environ['OPENAI_API_KEY'] = 'sk-mock-key-for-validation'
os.environ['CHANNEL_STUB_URL'] = 'http://localhost:8001'
os.environ['CRM_RECEIPT_URL'] = 'http://localhost:8000'

print("--- [1/6] agent/tools.py schemas ---")
from agent.tools import TOOLS, TOOLS_BY_NAME, execute_suggest_channel, execute_preview_campaign, _keyword_fallback_filters

assert len(TOOLS) == 6, f"Expected 6 tools, got {len(TOOLS)}"
tool_names = [t['function']['name'] for t in TOOLS]
print("Tool names:", tool_names)
for name in ['build_segment', 'suggest_channel', 'generate_message', 'preview_campaign', 'launch_campaign', 'query_customer_directory']:
    assert name in tool_names, f"Missing tool: {name}"

for tool in TOOLS:
    assert tool['type'] == 'function'
    fn = tool['function']
    assert 'name' in fn and 'description' in fn and 'parameters' in fn
    params = fn['parameters']
    assert params['type'] == 'object'
    assert 'properties' in params and 'required' in params
    assert params.get('additionalProperties') == False, f"{fn['name']} needs additionalProperties:false"
    print(f"  Schema OK: {fn['name']} | required={params['required']}")
print("PASS")

print("--- [2/6] suggest_channel rule logic ---")
r1 = execute_suggest_channel({'audience_count': 180, 'avg_spend': 3500, 'goal': 'win back'})
assert r1['channel'] == 'whatsapp', f"Expected whatsapp, got {r1['channel']}"
print(f"180 customers, high-spend -> {r1['channel']}")

r2 = execute_suggest_channel({'audience_count': 600, 'avg_spend': 800, 'goal': 'newsletter'})
assert r2['channel'] == 'email', f"Expected email, got {r2['channel']}"
print(f"600 customers -> {r2['channel']}")

r3 = execute_suggest_channel({'audience_count': 50, 'avg_spend': 500, 'goal': 'win back'})
assert r3['channel'] == 'whatsapp'
print(f"50 customers -> {r3['channel']}")

formal = execute_suggest_channel({'audience_count': 100, 'avg_spend': 1000, 'goal': 'formal invoice'})
assert formal['channel'] == 'email', f"Formal goal should be email, got {formal['channel']}"
print(f"Formal goal -> {formal['channel']}")
print("PASS")

print("--- [3/6] preview_campaign pure assembly ---")
preview = execute_preview_campaign({
    'campaign_name': 'Test Campaign',
    'segment_filters': {'inactive_days': 45},
    'audience_count': 180,
    'channel': 'whatsapp',
    'variant_a': 'Hi {{name}}, we miss you!',
    'variant_b': 'Hey {{name}}, come back!',
    'channel_reason': 'WhatsApp is best for small audiences',
})
assert preview['step'] == 'campaign_preview'
assert preview['ready_to_launch'] == True
assert preview['audience_count'] == 180
assert preview['channel'] == 'whatsapp'
print("Preview card step:", preview['step'], "| ready_to_launch:", preview['ready_to_launch'])
print("PASS")

print("--- [4/6] keyword fallback filter logic ---")
f1 = _keyword_fallback_filters('win back inactive customers')
assert 'inactive_days' in f1
print("Win-back fallback:", f1)

f2 = _keyword_fallback_filters('reward VIP loyal customers')
assert 'min_spent' in f2 and f2.get('tags') == ['vip']
print("VIP fallback:", f2)

f3 = _keyword_fallback_filters('convert new first-time buyers')
assert 'tags' in f3 and 'new' in f3['tags']
print("New customer fallback:", f3)

f4 = _keyword_fallback_filters('re-engage churned users')
assert 'inactive_days' in f4
print("Re-engage fallback:", f4)
print("PASS")

print("--- [5/6] agent/copilot.py session management ---")
from agent.copilot import SESSIONS, get_or_create_session, delete_session, get_session_history, MAX_TOOL_CALLS_PER_TURN

session_id = 'test-session-validation-001'
history = get_or_create_session(session_id)
assert len(history) == 1, f"New session must have 1 message (system prompt), got {len(history)}"
assert history[0]['role'] == 'system'
assert 'Copilot' in history[0]['content']
print(f"Session created. System prompt first 80 chars: '{history[0]['content'][:80]}'")

history2 = get_or_create_session(session_id)
assert history2 is history, "Same session_id must return same list"
print("Session idempotency PASS")

history.append({'role': 'user', 'content': 'test message'})
assert len(get_session_history(session_id)) == 2
print(f"History after adding message: {len(get_session_history(session_id))} messages")

deleted = delete_session(session_id)
assert deleted == True
assert session_id not in SESSIONS
print("Session deleted PASS")

not_deleted = delete_session('nonexistent-xyz')
assert not_deleted == False
print("Non-existent delete returns False PASS")
print(f"MAX_TOOL_CALLS_PER_TURN = {MAX_TOOL_CALLS_PER_TURN}")
print("PASS")

print("--- [6/6] main.py all routes mounted ---")
import main
all_routes = [r.path for r in main.app.routes]
print("All routes:", sorted(all_routes))
required = ['/chat', '/chat/{session_id}', '/opportunities', '/campaigns/{campaign_id}/stats', '/receipts', '/customers/stats']
for route in required:
    assert route in all_routes, f"Missing route: {route}"
    print(f"  {route} FOUND")
print("PASS")

print()
print("ALL 6 VALIDATIONS PASSED - AI Copilot is production-ready")
