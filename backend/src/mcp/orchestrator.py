"""
MCP Orchestrator — the brain of the MCP pipeline.

Pipeline:
  1. Regex intent classification (0 tokens)
  2. Tool selection based on intent + entity extraction
  3. Parallel tool execution via ThreadPoolExecutor
  4. Context assembly with token-aware truncation
  5. Context quality gate
  6. Single LLM call with assembled context
  7. Escalation: LLM function-calling fallback (gated)

Design goals:
  - 1 LLM call per query (down from 3 in LangGraph) → ~33% token savings
  - Regex first (0 cost) → LLM fallback only when regex finds nothing
  - Live data integrated → avoids web search for time-sensitive queries
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from ..core.config import settings
from ..core.result import AskResult, ToolResult
from ..core.token_utils import count_tokens, max_tokens_for
from . import client, context_assembler

log = logging.getLogger("mcp.orchestrator")

# Thread pool for running sync tool handlers in parallel
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp-tool")

# ── Team aliases for entity extraction ─────────────────────────────────────────
TEAM_ALIASES: dict[str, str] = {
    "india": "India", "ind": "India", "team india": "India",
    "australia": "Australia", "aus": "Australia", "aussies": "Australia",
    "england": "England", "eng": "England",
    "pakistan": "Pakistan", "pak": "Pakistan",
    "south africa": "South Africa", "sa": "South Africa", "proteas": "South Africa",
    "new zealand": "New Zealand", "nz": "New Zealand", "kiwis": "New Zealand",
    "west indies": "West Indies", "wi": "West Indies", "windies": "West Indies",
    "sri lanka": "Sri Lanka", "sl": "Sri Lanka",
    "bangladesh": "Bangladesh", "ban": "Bangladesh",
    "afghanistan": "Afghanistan", "afg": "Afghanistan",
    "zimbabwe": "Zimbabwe", "zim": "Zimbabwe",
    "ireland": "Ireland", "ire": "Ireland",
    "netherlands": "Netherlands", "ned": "Netherlands",
    "scotland": "Scotland", "sco": "Scotland",
    # IPL teams
    "csk": "Chennai Super Kings", "chennai super kings": "Chennai Super Kings",
    "mi": "Mumbai Indians", "mumbai indians": "Mumbai Indians",
    "rcb": "Royal Challengers Bengaluru", "royal challengers": "Royal Challengers Bengaluru",
    "kkr": "Kolkata Knight Riders", "kolkata knight riders": "Kolkata Knight Riders",
    "srh": "Sunrisers Hyderabad", "sunrisers hyderabad": "Sunrisers Hyderabad",
    "dc": "Delhi Capitals", "delhi capitals": "Delhi Capitals",
    "pbks": "Punjab Kings", "punjab kings": "Punjab Kings",
    "rr": "Rajasthan Royals", "rajasthan royals": "Rajasthan Royals",
    "gt": "Gujarat Titans", "gujarat titans": "Gujarat Titans",
    "lsg": "Lucknow Super Giants", "lucknow super giants": "Lucknow Super Giants",
}

# ── Intent patterns (regex — 0 tokens) ────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Live / time-sensitive
    ("live", re.compile(
        r"\b(live\s*score|current\s*score|right\s*now|happening\s*now|"
        r"ongoing\s*match|today.s\s*match|score\s*update|what.s\s*the\s*score|"
        r"is\s*\w+\s*playing|who\s*is\s*batting|who\s*is\s*bowling)\b", re.I
    )),
    ("toss", re.compile(
        r"\b(toss|won\s*the\s*toss|toss\s*result|elected\s*to|chose\s*to\s*bat|"
        r"chose\s*to\s*bowl|batting\s*first|bowling\s*first)\b", re.I
    )),
    ("recent", re.compile(
        r"\b(recent\s*(match|result|game)|last\s*(match|game|result)|"
        r"yesterday.s?\s*match|who\s*won|result\s*of|score\s*of\s*yesterday|"
        r"latest\s*result)\b", re.I
    )),
    # Fantasy / prediction — checked BEFORE head_to_head because "CSK vs MI"
    # contains "vs" which would otherwise match head_to_head first.
    ("fantasy", re.compile(
        r"\b(fantasy|dream\s*11|dream11|playing\s*xi|playing\s*11|"
        r"captain|vice\s*captain|vc\b|best\s*team|pick\s*team)\b", re.I
    )),
    ("prediction", re.compile(
        r"\b(predict|prediction|who\s*will\s*win|forecast|chances|"
        r"probability|likely\s*winner|odds)\b", re.I
    )),

    # Stats / analysis
    ("batting_stats", re.compile(
        r"\b(batting|runs|average|strike\s*rate|centuries|fifties|"
        r"highest\s*score|bat\b|batsman|batter|sixes|fours|boundaries)\b", re.I
    )),
    ("bowling_stats", re.compile(
        r"\b(bowling|wickets|economy|bowl\b|bowler|overs|maiden|"
        r"dot\s*ball|spell|figures|best\s*bowling)\b", re.I
    )),
    ("head_to_head", re.compile(
        r"\b(head\s*to\s*head|h2h|vs\b|versus|against|matchup|face\s*off)\b", re.I
    )),
    ("venue", re.compile(
        r"\b(venue|ground|stadium|pitch|wankhede|eden\s*gardens|"
        r"chinnaswamy|lords|oval|mcg|scg|gabba|narendra\s*modi)\b", re.I
    )),
    ("form", re.compile(
        r"\b(form|recent\s*form|last\s*\d+\s*innings|current\s*form|"
        r"in\s*form|out\s*of\s*form|consistency)\b", re.I
    )),
    ("team_matchup", re.compile(
        r"\b(team\s*record|team\s*vs|team\s*matchup|team\s*comparison|"
        r"overall\s*record|win.loss\s*record|series\s*record)\b", re.I
    )),
]

# Freshness signals — if detected, prefer live tools
_FRESHNESS_RE = re.compile(
    r"\b(today|tonight|right\s*now|currently|ongoing|live|this\s*match|"
    r"this\s*game|now\b|happening|latest|just\s*now|update)\b", re.I
)

# Format extraction
_FORMAT_RE = re.compile(r"\b(T20I?|ODI|Test|IPL|BBL|CPL|PSL|WPL)\b", re.I)

# "X vs Y" pattern for team/player matchups
_VS_RE = re.compile(
    r"(\b[\w\s]+?)\s+(?:vs\.?|versus|against|v\.?)\s+([\w\s]+?)(?:\s|$|[,?.])",
    re.I,
)


# ── Intent classification ──────────────────────────────────────────────────────

def classify_intent(query: str) -> str:
    """
    Regex-based intent classification. Returns the first matching intent,
    or 'general' if nothing matches.
    """
    for intent_name, pattern in _INTENT_PATTERNS:
        if pattern.search(query):
            return intent_name
    return "general"


def _is_fresh_query(query: str) -> bool:
    """Does the query mention live/current/today signals?"""
    return bool(_FRESHNESS_RE.search(query))


def _extract_format(query: str) -> str:
    """Extract cricket format from query, or empty string."""
    m = _FORMAT_RE.search(query)
    if m:
        fmt = m.group(1).upper()
        if fmt in ("T20", "T20I"):
            return "T20"
        if fmt in ("IPL", "BBL", "CPL", "PSL", "WPL"):
            return "T20"  # franchise leagues are T20
        return fmt
    # IPL heuristic (in case regex misses it)
    if re.search(r"\bipl\b", query, re.I):
        return "T20"
    return ""


def _extract_teams(query: str) -> list[str]:
    """Extract team names from query using TEAM_ALIASES."""
    found: list[str] = []
    q_lower = query.lower()
    # Sort by length descending to match longer aliases first
    for alias in sorted(TEAM_ALIASES.keys(), key=len, reverse=True):
        # Short aliases (2-3 chars like "dc", "gt", "wi", "sa") need word-boundary
        # matching to avoid false positives ("wi" inside "win", "sa" inside "says")
        if len(alias) <= 3:
            if not re.search(r'\b' + re.escape(alias) + r'\b', q_lower):
                continue
        else:
            if alias not in q_lower:
                continue
        canonical = TEAM_ALIASES[alias]
        if canonical not in found:
            found.append(canonical)
        if len(found) >= 2:
            break
    return found


def _extract_players(query: str) -> list[str]:
    """Extract player names from query using PLAYER_ALIASES."""
    try:
        from backend.src.routers.players import PLAYER_ALIASES
    except ImportError:
        return []

    found: list[str] = []
    q_lower = query.lower()
    # Sort by length descending to match longer aliases first
    for alias in sorted(PLAYER_ALIASES.keys(), key=len, reverse=True):
        # Word-boundary match to avoid false positives
        if not re.search(r'\b' + re.escape(alias) + r'\b', q_lower):
            continue
        canonical = PLAYER_ALIASES[alias]
        if canonical not in found:
            found.append(canonical)
        if len(found) >= 4:
            break
    return found


def _extract_vs_entities(query: str) -> tuple[str, str] | None:
    """Extract 'X vs Y' entities from the query."""
    m = _VS_RE.search(query)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


# ── Tool selection ─────────────────────────────────────────────────────────────

def select_tools(query: str, intent: str) -> list[dict[str, Any]]:
    """
    Given intent + query, return a list of {tool_name, arguments} dicts
    for the tools to call.
    """
    tools: list[dict[str, Any]] = []
    fmt = _extract_format(query)
    players = _extract_players(query)
    teams = _extract_teams(query)
    is_fresh = _is_fresh_query(query)
    vs = _extract_vs_entities(query)

    # ── Live / time-sensitive intents ─────────────────────────────────────
    if intent == "live" or (is_fresh and intent in ("general", "recent")):
        tools.append({"tool_name": "live_scores", "arguments": {"format": fmt, "limit": 10}})
        if teams:
            tools.append({"tool_name": "match_status", "arguments": {"team": teams[0]}})

    if intent == "toss":
        args: dict[str, Any] = {"format": fmt}
        if teams:
            args["team"] = teams[0]
        tools.append({"tool_name": "toss_info", "arguments": args})

    if intent == "recent":
        args = {"format": fmt, "limit": 10}
        if teams:
            args["team"] = teams[0]
        tools.append({"tool_name": "recent_matches", "arguments": args})

    # ── Stats intents ────────────────────────────────────────────────────
    if intent == "batting_stats":
        for p in players or ["unknown"]:
            if p != "unknown":
                tools.append({"tool_name": "player_batting_stats", "arguments": {"player_name": p, "format": fmt or "T20"}})

    if intent == "bowling_stats":
        for p in players or ["unknown"]:
            if p != "unknown":
                tools.append({"tool_name": "player_bowling_stats", "arguments": {"player_name": p, "format": fmt or "T20"}})

    if intent == "head_to_head" and vs:
        # Could be player vs player or team vs team
        a, b = vs
        # Try to resolve as players first
        p_a = _resolve_player(a)
        p_b = _resolve_player(b)
        if p_a and p_b:
            tools.append({"tool_name": "head_to_head", "arguments": {"batter": p_a, "bowler": p_b, "format": fmt or "T20"}})
        # Also try team matchup
        t_a = _resolve_team(a)
        t_b = _resolve_team(b)
        if t_a and t_b:
            tools.append({"tool_name": "team_matchup", "arguments": {"team_a": t_a, "team_b": t_b, "format": fmt or "T20"}})
        # Fallback: just use the raw names
        if not tools:
            tools.append({"tool_name": "head_to_head", "arguments": {"batter": a, "bowler": b, "format": fmt or "T20"}})

    if intent == "venue":
        # Extract venue name — try to find it after "at" or "in" or just use full query
        venue = _extract_venue(query) or query
        tools.append({"tool_name": "venue_stats", "arguments": {"venue": venue, "format": fmt or "T20"}})

    if intent == "form":
        for p in players or []:
            tools.append({"tool_name": "recent_form", "arguments": {"player_name": p, "format": fmt or "T20"}})

    if intent == "team_matchup" and len(teams) >= 2:
        tools.append({"tool_name": "team_matchup", "arguments": {"team_a": teams[0], "team_b": teams[1], "format": fmt or "T20"}})

    # ── Fantasy / prediction — needs both stats + live ───────────────────
    if intent in ("fantasy", "prediction"):
        # Get live context for the match
        if teams:
            tools.append({"tool_name": "match_status", "arguments": {"team": teams[0]}})
            if len(teams) >= 2:
                tools.append({"tool_name": "team_matchup", "arguments": {"team_a": teams[0], "team_b": teams[1], "format": fmt or "T20"}})
        # Get player stats for mentioned players
        for p in players:
            tools.append({"tool_name": "player_batting_stats", "arguments": {"player_name": p, "format": fmt or "T20"}})
        if is_fresh:
            tools.append({"tool_name": "toss_info", "arguments": {"format": fmt, "team": teams[0] if teams else ""}})
        # Venue stats if venue is mentioned
        venue = _extract_venue(query)
        if venue:
            tools.append({"tool_name": "venue_stats", "arguments": {"venue": venue, "format": fmt or "T20"}})

    # ── General — try to be smart about what to fetch ────────────────────
    if intent == "general":
        # If we found players, get their stats
        for p in players:
            tools.append({"tool_name": "player_batting_stats", "arguments": {"player_name": p, "format": fmt or "T20"}})
            tools.append({"tool_name": "player_bowling_stats", "arguments": {"player_name": p, "format": fmt or "T20"}})
        # If we found teams
        if len(teams) >= 2:
            tools.append({"tool_name": "team_matchup", "arguments": {"team_a": teams[0], "team_b": teams[1], "format": fmt or "T20"}})
        if is_fresh:
            tools.append({"tool_name": "live_scores", "arguments": {"format": fmt, "limit": 5}})

    # Deduplicate by tool_name + arguments
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for t in tools:
        key = f"{t['tool_name']}:{sorted(t['arguments'].items())}"
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


def _resolve_player(name: str) -> str:
    """Try to resolve a name to a Cricsheet player name."""
    try:
        from backend.src.routers.players import PLAYER_ALIASES
        return PLAYER_ALIASES.get(name.strip().lower(), name.strip())
    except ImportError:
        return name.strip()


def _resolve_team(name: str) -> str:
    """Try to resolve a name to a canonical team name."""
    return TEAM_ALIASES.get(name.strip().lower(), "")


def _extract_venue(query: str) -> str:
    """Try to extract a venue name from the query."""
    # Look for "at <venue>" or "in <venue>"
    m = re.search(r"\b(?:at|in)\s+([\w\s]+?)(?:\s+(?:stadium|ground))?\s*(?:[?.,]|$)", query, re.I)
    if m:
        venue = m.group(1).strip()
        # Filter out common non-venue words
        if venue.lower() not in ("the", "a", "this", "that", "which"):
            return venue

    # Known venue keywords
    venues = [
        "wankhede", "eden gardens", "chinnaswamy", "lords", "oval",
        "mcg", "scg", "gabba", "narendra modi", "arun jaitley",
        "mohali", "rajiv gandhi", "brabourne", "chepauk", "feroz shah kotla",
    ]
    q_lower = query.lower()
    for v in venues:
        if v in q_lower:
            return v.title()

    return ""


# ── Orchestrator main entry point ──────────────────────────────────────────────

async def run(query: str, context: dict[str, Any] | None = None) -> AskResult:
    """
    Full MCP pipeline:
      regex intent → tool selection → parallel execution → context assembly
      → quality gate → single LLM call

    Tracks elapsed wall time so the LLM call never exceeds the remaining
    budget (Railway hard-kills at 60s).
    """
    t0 = time.monotonic()
    context = context or {}
    # Total budget for the MCP pipeline (ask.py wraps us in this timeout too)
    total_budget = settings.tier2_budget_s  # 44s

    # Step 1: Intent classification (regex — 0 tokens)
    intent = classify_intent(query)
    log.info("Intent: %s for query: '%.80s'", intent, query)

    # Step 2: Select tools
    tool_calls = select_tools(query, intent)
    log.info("Selected %d tools: %s", len(tool_calls), [t["tool_name"] for t in tool_calls])

    # Step 2b: Escalation — if no tools found, check if LLM fallback is warranted
    if not tool_calls:
        word_count = len(query.split())
        if word_count >= settings.mcp_llm_fallback_min_words and intent == "general":
            log.info("No regex tools matched — escalating to LLM-free general answer")
        else:
            log.info("No tools matched for short/non-general query — proceeding with empty context")

    # Step 3: Parallel tool execution (budgeted — leave ≥8s for LLM)
    results: list[ToolResult] = []
    if tool_calls:
        tool_budget = min(
            float(settings.mcp_tool_timeout_s),
            _remaining(t0, total_budget, margin=8),
        )
        if tool_budget > 1:
            results = await _execute_tools(tool_calls, tool_budget)
        else:
            log.warning("No time budget for tools — skipping")

    # Step 4: Quality gate
    gate = context_assembler.quality_gate(results)
    log.info("Quality gate: %s (elapsed=%.1fs)", gate, time.monotonic() - t0)

    # Step 5: Context assembly
    assembled_context = context_assembler.assemble(results)

    # Step 6: If quality gate fails and query warrants it, escalate to web search
    if not gate["pass"] and _is_fresh_query(query):
        remaining = _remaining(t0, total_budget, margin=8)
        if remaining > 5:
            log.info("Quality gate failed + fresh query — escalating to web_search (%.0fs left)", remaining)
            search_result = await _execute_single_tool(
                "web_search", {"query": query}, min(remaining, float(settings.mcp_tool_timeout_s)),
            )
            if search_result.ok:
                results.append(search_result)
                assembled_context = context_assembler.assemble(results)
                gate = context_assembler.quality_gate(results)
        else:
            log.info("Quality gate failed but only %.0fs left — skipping web_search", remaining)

    # Step 7: Single LLM call with assembled context (deadline-aware)
    tools_used = [r.tool_name for r in results if r.ok]
    data_sources = list({r.source for r in results if r.ok})

    llm_budget = _remaining(t0, total_budget, margin=2)
    if llm_budget < 3:
        log.warning("Only %.1fs left for LLM call — returning tool context directly", llm_budget)
        answer = assembled_context or "⏱️ Not enough time to generate a full answer. Please try again."
    else:
        log.info("LLM call budget: %.1fs (elapsed: %.1fs)", llm_budget, time.monotonic() - t0)
        answer = await _llm_call(query, assembled_context, intent, context, timeout=llm_budget)

    elapsed = int((time.monotonic() - t0) * 1000)

    # Extract players for response
    players = _extract_players(query)

    return AskResult(
        answer=answer,
        intent=intent,
        players=players,
        mode="mcp",
        data_sources=data_sources,
        latency_ms=elapsed,
        tools_used=tools_used,
    )


def _remaining(t0: float, total_budget: float, margin: float = 2) -> float:
    """Seconds remaining in the budget, with a safety margin."""
    elapsed = time.monotonic() - t0
    return max(0, total_budget - elapsed - margin)


async def _execute_tools(tool_calls: list[dict[str, Any]], per_tool_timeout: float = 10) -> list[ToolResult]:
    """Execute multiple tools in parallel using ThreadPoolExecutor."""
    loop = asyncio.get_running_loop()

    async def _run_one(tc: dict[str, Any]) -> ToolResult:
        # Capture values up-front to avoid closure-over-loop-variable bugs
        tool_name = tc["tool_name"]
        tool_args = tc.get("arguments", {})
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    lambda _n=tool_name, _a=tool_args: client.call_tool(_n, _a),
                ),
                timeout=per_tool_timeout,
            )
        except asyncio.TimeoutError:
            log.warning("Tool %s timed out after %.0fs", tool_name, per_tool_timeout)
            return ToolResult(
                tool_name=tool_name,
                data="",
                error=f"Timed out after {per_tool_timeout:.0f}s",
            )
        except Exception as e:
            log.error("Tool %s error: %s", tool_name, e)
            return ToolResult(
                tool_name=tool_name,
                data="",
                error=str(e),
            )

    tasks = [_run_one(tc) for tc in tool_calls]
    return list(await asyncio.gather(*tasks))


async def _execute_single_tool(name: str, arguments: dict, timeout: float | None = None) -> ToolResult:
    """Execute a single tool (used for escalation)."""
    _timeout = timeout or float(settings.mcp_tool_timeout_s)
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _executor,
                lambda: client.call_tool(name, arguments),
            ),
            timeout=_timeout,
        )
    except asyncio.TimeoutError:
        return ToolResult(tool_name=name, data="", error=f"Timed out after {_timeout:.0f}s")
    except Exception as e:
        return ToolResult(tool_name=name, data="", error=str(e))


async def _llm_call(
    query: str,
    context_block: str,
    intent: str,
    extra_context: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> str:
    """
    Single LLM call with assembled MCP context.
    Uses the same Gemini client as llm_client.py but with a focused prompt.
    """
    from datetime import date as _date

    today = _date.today().strftime("%d %B %Y")
    dynamic_tokens = max_tokens_for(query)
    llm_timeout = timeout or float(settings.tier2_budget_s)

    system = (
        f"You are an expert cricket analyst AI. Today is {today}.\n\n"
        "RULES:\n"
        "1. COMPLETE answers only — never cut off mid-sentence or mid-table.\n"
        "2. TABLES: always include header + separator (|---|) + ALL data rows.\n"
        "3. Use markdown headers (##), bullets, and tables.\n"
        "4. DATA sections below = ground truth — cite them as primary source.\n"
        "5. Numbers over vague claims. No biographies.\n"
        "6. Non-cricket → reply: '🏏 I am a cricket specialist.'\n"
        "7. End with a summary or actionable insight.\n\n"
    )

    prompt_parts = [system]

    if context_block:
        prompt_parts.append(context_block)
        prompt_parts.append("")  # blank line

    prompt_parts.append(f"Question: {query}")
    full_prompt = "\n".join(prompt_parts)
    # Use the Gemini client directly.
    # Pass llm_timeout into _call_gemini so it sets HTTP-level timeouts
    # (asyncio.wait_for cannot cancel sync code in ThreadPoolExecutor).
    loop = asyncio.get_running_loop()
    try:
        answer = await asyncio.wait_for(
            loop.run_in_executor(
                _executor,
                lambda _t=llm_timeout: _call_gemini(full_prompt, dynamic_tokens, timeout=_t),
            ),
            timeout=llm_timeout,
        )
        return answer
    except asyncio.TimeoutError:
        log.warning("LLM call timed out after %.0fs", llm_timeout)
        return (
            "⏱️ The AI took too long to respond. Please try a shorter or simpler question.\n\n"
            "**Tip:** Be specific — e.g., 'Virat Kohli T20 batting stats' instead of a broad question."
        )
    except Exception as e:
        log.error("LLM call failed: %s", e)
        return f"❌ Error generating response: {e}"


def _call_gemini(prompt: str, max_output_tokens: int, timeout: float = 30) -> str:
    """Synchronous Gemini API call — runs in executor.

    ``timeout`` caps each HTTP request *and* the total wall time for retries.
    This is critical because ``asyncio.wait_for`` cannot cancel a running
    ``run_in_executor`` thread — if we don't cap here, the thread keeps
    running long past the asyncio timeout.
    """
    import time as _time

    _deadline = _time.monotonic() + timeout

    from backend.src.services.llm_settings import GEMINI_API_KEY

    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY not set. Please configure it in Railway Variables."

    from google import genai
    from google.genai import types

    # Hard HTTP-level timeout so httpx aborts the request on time.
    # HttpOptions.timeout is in MILLISECONDS (google-genai divides by 1000).
    # Cap per-request at 25s so one hung request doesn't consume the full budget,
    # leaving room to try fallback models.
    per_request_s = min(25, max(8, timeout - 2))
    http_timeout_ms = int(per_request_s * 1000)
    client_instance = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=http_timeout_ms),
    )

    from backend.src.services.llm_client import (
        GEMINI_FALLBACK_MODELS,
        _clean_response,
    )
    from backend.src.services.llm_settings import LLM_MODEL

    models = [LLM_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != LLM_MODEL]

    config = types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        temperature=0.3,
    )

    for model in models:
        if _time.monotonic() >= _deadline:
            log.warning("_call_gemini budget exhausted before trying model %s", model)
            break

        for attempt in range(2):
            if _time.monotonic() >= _deadline:
                break
            try:
                response = client_instance.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                text = ""
                try:
                    text = response.text or ""
                except Exception:
                    pass

                if not text:
                    try:
                        for candidate in (response.candidates or []):
                            content = getattr(candidate, "content", None)
                            if content:
                                for part in (getattr(content, "parts", None) or []):
                                    t = getattr(part, "text", None)
                                    if t:
                                        text += t
                    except Exception:
                        pass

                if text:
                    return _clean_response(text)

            except Exception as e:
                err = str(e)
                remaining = _deadline - _time.monotonic()
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    # Quota exhaustion — all models share the same key, fail fast.
                    # RESOURCE_EXHAUSTED alone is enough; don't require "quota" keyword.
                    if "RESOURCE_EXHAUSTED" in err or "quota" in err.lower() or "exceeded" in err.lower():
                        log.warning("Gemini quota exhausted — aborting all retries")
                        return (
                            "⚠️ The AI service has reached its daily usage limit. "
                            "Please try again later or ask a simpler question."
                        )
                    # Transient rate limit — brief pause then retry
                    if attempt == 0 and remaining > 6:
                        _time.sleep(min(3, remaining - 3))
                        continue
                    break
                elif "503" in err or "UNAVAILABLE" in err or "overloaded" in err.lower():
                    if attempt == 0 and remaining > 6:
                        _time.sleep(min(2, remaining - 4))
                        continue
                    break
                elif "404" in err or "NOT_FOUND" in err:
                    break
                else:
                    log.warning("Gemini %s error: %s", model, err[:200])
                    return f"❌ Gemini error: {err}"

    return "❌ All Gemini models exhausted. Please try again in a few minutes."
