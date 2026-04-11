"""Smoke test for MCP modules."""

from backend.src.mcp.context_assembler import assemble, quality_gate
print("mcp.context_assembler OK")

from backend.src.mcp.orchestrator import classify_intent, select_tools
print("mcp.orchestrator OK")

tests = [
    ("Virat Kohli batting average", "batting_stats"),
    ("live score India vs Australia", "live"),
    ("who won the toss", "toss"),
    ("predict CSK vs MI", "prediction"),
    ("what is cricket", "general"),
    ("Bumrah bowling economy in T20", "bowling_stats"),
    ("India vs Australia head to head", "head_to_head"),
    ("Wankhede stadium stats", "venue"),
    ("Kohli recent form last 10 innings", "form"),
    ("dream11 fantasy team for CSK vs MI", "fantasy"),
]
print()
all_pass = True
for query, expected in tests:
    actual = classify_intent(query)
    ok = "PASS" if actual == expected else "FAIL"
    if ok == "FAIL":
        all_pass = False
    print(f"  {ok} Intent({query!r}) = {actual} (expected: {expected})")

print()
tools_for = select_tools("Virat Kohli batting stats in T20", "batting_stats")
print(f"  Tools for batting_stats: {[t['tool_name'] for t in tools_for]}")

tools_for = select_tools("live score India vs Australia", "live")
print(f"  Tools for live: {[t['tool_name'] for t in tools_for]}")

tools_for = select_tools("who won the toss today India", "toss")
print(f"  Tools for toss: {[t['tool_name'] for t in tools_for]}")

tools_for = select_tools("India vs Australia head to head T20", "head_to_head")
print(f"  Tools for h2h: {[t['tool_name'] for t in tools_for]}")

tools_for = select_tools("predict CSK vs MI IPL", "prediction")
print(f"  Tools for prediction: {[t['tool_name'] for t in tools_for]}")

# Test quality gate with mock ToolResult
from backend.src.core.result import ToolResult
r1 = ToolResult(tool_name="player_batting_stats", data="V Kohli: 12000 runs", source="cricsheet", tokens_estimate=50)
r2 = ToolResult(tool_name="live_scores", data="India 250/4", source="live", tokens_estimate=30)
r3 = ToolResult(tool_name="bad_tool", data="", source="cricsheet", error="Failed")
gate = quality_gate([r1, r2, r3])
print(f"\n  Quality gate (2 good + 1 error): pass={gate['pass']}, good_count={gate['good_count']}, sources={gate['sources']}")

gate2 = quality_gate([r3])
print(f"  Quality gate (all errors): pass={gate2['pass']}, reason={gate2.get('reason','')}")

# Test context assembly
assembled = assemble([r1, r2])
print(f"\n  Assembled context length: {len(assembled)} chars")
print(f"  Contains 'CRICSHEET': {'CRICSHEET' in assembled}")
print(f"  Contains 'LIVE': {'LIVE' in assembled}")

print(f"\n{'='*60}")
print(f"All intent tests passed: {all_pass}")
print(f"{'='*60}")
