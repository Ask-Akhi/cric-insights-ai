# -*- coding: utf-8 -*-
"""
PydanticAI Agent — replaces orchestrator.py.

Architecture:
  - PydanticAI manages the tool-calling loop (up to MAX_STEPS hops)
  - Each tool calls either PostgreSQL (fast, memory-safe) or falls back
    to the existing MCP server handlers (when DB is not yet configured)
  - Circuit breaker wraps the entire agent.run() call
  - Fully async + streaming-ready via agent.run_stream()

DB-mode vs Polars-mode:
  - If DATABASE_URL is set and pool is available → SQL queries
  - If not → falls back to existing MCP cricsheet_server handlers
    (zero breaking change during migration)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, TYPE_CHECKING

log = logging.getLogger("mcp.agent")

MAX_STEPS = 5   # max LLM ↔ tool round-trips per request

# Type-only import — keeps startup fast but makes RunContext resolvable by
# get_type_hints() when pydantic-ai evaluates the tool signatures at register time.
if TYPE_CHECKING:
    from pydantic_ai import RunContext
else:
    try:
        from pydantic_ai import RunContext  # type: ignore
    except ImportError:
        RunContext = Any  # type: ignore

# ── Lazy import guard ─────────────────────────────────────────────────────────
_pydantic_ai_available: Optional[bool] = None


def _check_pydantic_ai() -> bool:
    global _pydantic_ai_available
    if _pydantic_ai_available is None:
        try:
            import pydantic_ai  # noqa: F401
            _pydantic_ai_available = True
        except ImportError:
            _pydantic_ai_available = False
            log.info(
                "pydantic-ai not installed — agent.py will delegate to orchestrator.py. "
                "Install with: pip install pydantic-ai"
            )
    return _pydantic_ai_available


# ── Result model (mirrors AskResult for ask.py compatibility) ─────────────────
@dataclass
class AgentResult:
    answer: str
    intent: str = "general"
    players: list[str] = field(default_factory=list)
    mode: str = "agent"
    data_sources: list[str] = field(default_factory=list)
    latency_ms: int = 0
    rag_cache_hit: bool = False
    tools_used: list[str] = field(default_factory=list)
    error: Optional[str] = None


# ── Dependency container (injected into every tool) ───────────────────────────
@dataclass
class CricketDeps:
    db_pool: Any = None          # asyncpg pool or None (Polars fallback)
    session_id: str = "default"


# ── Build the agent (lazy — only once, module-level singleton) ────────────────
_agent = None


def _build_agent():
    """Build and cache the PydanticAI agent with all cricket tools."""
    global _agent
    if _agent is not None:
        return _agent

    from pydantic_ai import Agent, RunContext
    from ..core.config import settings

    # ── Model selection ───────────────────────────────────────────────────────
    # pydantic-ai 1.x: API keys are passed via provider objects, not api_key=
    if settings.llm_provider == "openai" and settings.openai_api_key:
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider
        model = OpenAIModel(
            settings.llm_model or "gpt-4o-mini",
            provider=OpenAIProvider(api_key=settings.openai_api_key),
        )
    else:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider
        model = GoogleModel(
            settings.llm_model or "gemini-2.5-flash",
            provider=GoogleProvider(api_key=settings.gemini_api_key),
        )    # -- System prompt -------------------------------------------------------
    SYSTEM = """You are Cricket Insights AI - an elite cricket analyst and match predictor.

DATA SOURCES (in priority order):
  1. VERIFIED CRICSHEET DATA block in the user prompt (ball-by-ball ground truth).
  2. Tool calls: head_to_head, player_stats, recent_form, top_players, venue_stats, semantic_search, live_score.
  3. Web/grounded search (only when user enables it) - use for very recent news,
     injuries, playing XI, toss, pitch report.

GENERAL RULES:
1. If VERIFIED CRICSHEET DATA is present, use it FIRST and cite its numbers.
2. Otherwise, call at least one tool before answering.
3. Use head_to_head for "Team A vs Team B" queries.
4. Use player_stats(last_n_years=N, format=..., season=...) for player queries.
5. Use recent_form for "how has [team] been playing lately".
6. Use top_players for leaderboards.
7. Use venue_stats for venue/pitch analysis.
8. Use semantic_search for narrative queries or when other tools return nothing.
9. Use live_score only for live/ongoing match queries.
10. If no data is found, say so honestly - do NOT hallucinate stats.
11. Always cite specific numbers. Show a markdown table when returning multiple rows.

========================================================================
MATCH PREDICTION CONTRACT (when asked to predict a winner)
========================================================================
Output STRICT markdown in this order:

### 🏆 Predicted Winner: <Team> (confidence: NN%)

### 📊 Top 3 Factors (weighted)
Use format-aware ensemble weights:
  - T20: matchup 35% + recent form 30% + venue 20% + pressure/death overs 15%
  - ODI: recent form 30% + consistency 25% + venue 20% + matchup 25%
  - Test: technique/temperament 30% + conditions (pitch/weather) 30% + form 25% + matchup 15%

| # | Factor | Weight | Evidence (cite numbers) |
|---|--------|--------|-------------------------|
| 1 | ...    | 35%    | ...                     |

### 🥊 3 Key Matchups
- Batter X vs Bowler Y - why it matters (SR, avg, dismissals).

### ⭐ Key Players
- **Team A**: 2-3 names with role + recent numbers.
- **Team B**: 2-3 names with role + recent numbers.

### 💎 3 Hidden Gems (under-the-radar picks)
- Players with strong underlying numbers but low public attention - cite the stat.

### ⚠️ Risk Factor
One line on what could flip this prediction (injury doubt, toss, weather).

### 🎯 Confidence Layer
Score 0-100. Break down:
  - Data volume (have we got >=20 matches of signal?)
  - Recency (are stats from last 12 months?)
  - Variance (is form stable or erratic?)

SMALL-SAMPLE RULE: If player H2H or venue sample is <10 innings/matches,
cap contribution to 30% of its normal weight and flag it explicitly.

Be concise, specific, and numbers-first. Never invent stats.
"""
    _agent = Agent(
        model,
        deps_type=CricketDeps,
        output_type=str,
        system_prompt=SYSTEM,
    )

    # ── Tool registrations ────────────────────────────────────────────────────
    @_agent.tool
    async def head_to_head(
        ctx: RunContext[CricketDeps],
        team_a: str,
        team_b: str,
        format: str = "",
        last_n: int = 10,
    ) -> str:
        """Get head-to-head win/loss record and recent results between two cricket teams."""
        if ctx.deps.db_pool:
            from ..db.queries import query_head_to_head
            data = await query_head_to_head(ctx.deps.db_pool, team_a, team_b, format)
            if data.get("matches"):
                return _format_h2h(data, team_a, team_b)        # Polars fallback
        return await _polars_fallback("head_to_head", {
            "team_a": team_a, "team_b": team_b,            "format": format, "last_n": last_n,
        })

    @_agent.tool
    async def player_stats(
        ctx: RunContext[CricketDeps],
        player: str,
        season: str = "all",
        format: str = "",
        last_n_years: int = 0,
    ) -> str:
        """
        Get batting and bowling statistics for a cricket player.
        - season: exact season e.g. "2023", or "all" for career
        - last_n_years: e.g. 2 means stats from the last 2 seasons only
        - format: e.g. "T20", "ODI", "Test"
        """
        import datetime
        since_year = None
        if last_n_years > 0:
            since_year = datetime.date.today().year - last_n_years + 1

        if ctx.deps.db_pool:
            from ..db.queries import query_player_stats
            rows = await query_player_stats(
                ctx.deps.db_pool, player, season, format, since_year=since_year
            )
            if rows:
                return _format_player_stats(player, rows)

        return await _polars_fallback("player_stats", {
            "player": player, "season": season, "format": format,
        })

    @_agent.tool
    async def recent_form(
        ctx: RunContext[CricketDeps],
        team: str,
        last_n: int = 5,
        format: str = "",
    ) -> str:
        """Get the recent match results and form for a cricket team."""
        if ctx.deps.db_pool:
            from ..db.queries import query_recent_form
            rows = await query_recent_form(ctx.deps.db_pool, team, last_n, format)
            if rows:
                return _format_recent_form(team, rows)

        return await _polars_fallback("recent_form", {            "team": team, "last_n": last_n, "format": format,
        })

    @_agent.tool
    async def top_players(
        ctx: RunContext[CricketDeps],
        category: str = "batting",
        format: str = "IPL",
        season: str = "all",
        limit: int = 10,
    ) -> str:
        """Get top batting or bowling leaderboard for a format/season."""
        if ctx.deps.db_pool:
            if category.lower() == "bowling":
                from ..db.queries import query_top_bowlers
                rows = await query_top_bowlers(ctx.deps.db_pool, format, season, limit)
                return _format_leaderboard("Bowling", rows,
                                           ["player", "team", "wickets", "economy",
                                            "bowling_avg", "bowl_matches"])
            else:
                from ..db.queries import query_top_batters
                rows = await query_top_batters(ctx.deps.db_pool, format, season, limit)
                return _format_leaderboard("Batting", rows,
                                           ["player", "team", "runs", "avg",
                                            "strike_rate", "bat_matches"])

        return await _polars_fallback("top_players", {
            "category": category, "format": format,
            "season": season, "limit": limit,
        })

    @_agent.tool
    async def venue_stats(
        ctx: RunContext[CricketDeps],
        venue: str,
        format: str = "",
        last_n: int = 20,
    ) -> str:
        """Get venue stats: recent results, winner distribution, format breakdown."""
        if ctx.deps.db_pool:
            from ..db.queries import query_venue_stats
            data = await query_venue_stats(ctx.deps.db_pool, venue, format, last_n)
            if data.get("total_matches", 0) > 0:
                return _format_venue_stats(data)
        return f"No venue data found for '{venue}'."

    @_agent.tool
    async def semantic_search(
        ctx: RunContext[CricketDeps],
        query: str,
        limit: int = 5,
    ) -> str:
        """
        Search match summaries and cricket history using natural language.
        Use this for complex queries or when other tools return no data.
        """
        if ctx.deps.db_pool:
            # Try embedding-based search first
            embedding = await _embed_query(query)
            if embedding:
                from ..db.queries import query_semantic_search
                rows = await query_semantic_search(ctx.deps.db_pool, embedding, limit)
                if rows:
                    return "\n\n".join(
                        f"**{r['team_a']} vs {r['team_b']}** ({r['date']}): {r['summary']}"
                        for r in rows
                    )
            # Fallback to full-text search
            from ..db.queries import query_match_summary_text
            rows = await query_match_summary_text(ctx.deps.db_pool, query, limit)
            if rows:
                return "\n\n".join(
                    f"**{r['team_a']} vs {r['team_b']}** ({r['date']}): {r['summary']}"
                    for r in rows
                )
        return "No matching match records found."

    @_agent.tool
    async def live_score(
        ctx: RunContext[CricketDeps],
        format: str = "",
        limit: int = 5,
    ) -> str:
        """Get current live cricket match scores and ongoing match status."""
        try:
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            from ..mcp.servers.live_server import TOOLS as live_tools

            handler = next((t["handler"] for t in live_tools
                            if t["name"] == "live_scores"), None)
            if handler is None:
                return "Live scores tool not available."

            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as ex:
                result = await loop.run_in_executor(
                    ex, lambda: handler(format=format, limit=limit)
                )
            return result or "No live matches at this time."
        except Exception as exc:
            log.warning("live_score tool error: %s", exc)
            return f"Live scores unavailable: {exc}"

    log.info("PydanticAI cricket agent built ✅")
    return _agent


# ── Polars fallback ───────────────────────────────────────────────────────────

async def _polars_fallback(tool_name: str, args: dict) -> str:
    """
    Fall back to the existing MCP cricsheet_server handlers.
    Used when DATABASE_URL is not configured (Polars mode).
    """
    try:
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from ..mcp.servers import cricsheet_server

        handler = next(
            (t["handler"] for t in cricsheet_server.TOOLS if t["name"] == tool_name),
            None,
        )
        if handler is None:
            return f"Tool '{tool_name}' not found in Polars fallback."

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as ex:
            result = await loop.run_in_executor(ex, lambda: handler(**args))
        return result or "No data returned."
    except Exception as exc:
        log.warning("Polars fallback for %s failed: %s", tool_name, exc)
        return f"Data unavailable for {tool_name}: {exc}"


# ── Embedding helper ──────────────────────────────────────────────────────────

async def _embed_query(query: str) -> list[float] | None:
    """Generate embedding for semantic search. Returns None on failure."""
    import os
    try:
        if os.getenv("OPENAI_API_KEY"):
            from openai import AsyncOpenAI
            client = AsyncOpenAI()
            r = await client.embeddings.create(
                model="text-embedding-3-small", input=query
            )
            return r.data[0].embedding
        elif os.getenv("GEMINI_API_KEY"):
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            result = genai.embed_content(
                model="models/embedding-001",
                content=query,
                task_type="retrieval_query",
            )
            return result["embedding"]
    except Exception as exc:
        log.debug("Embedding failed: %s", exc)
    return None


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_h2h(data: dict, team_a: str, team_b: str) -> str:
    lines = [f"## Head-to-Head: {team_a} vs {team_b}\n"]
    for m in data.get("matches", []):
        ta_wins = m.get("team_a_wins", 0)
        tb_wins = m.get("team_b_wins", 0)
        total   = m.get("total_matches", 0)
        fmt     = m.get("format", "")
        lines.append(
            f"**{fmt}**: {m.get('team_a', team_a)} {ta_wins}W — "
            f"{tb_wins}W {m.get('team_b', team_b)} "
            f"({total} matches, last: {m.get('last_played', 'N/A')})"
        )
        for r in (m.get("recent_results") or [])[:5]:
            lines.append(f"  - {r.get('date', '')}: Winner — {r.get('winner', 'N/A')}")
    return "\n".join(lines) or "No head-to-head data found."


def _format_player_stats(player: str, rows: list[dict]) -> str:
    lines = [f"## Player Stats: {player}\n"]
    # Table header
    lines.append("| Season | Format | Team | Matches | Runs | Avg | SR | 4s | 6s | Wkts | Econ |")
    lines.append("|--------|--------|------|---------|------|-----|----|----|----|------|------|")
    for r in rows[:15]:
        lines.append(
            f"| {r.get('season','?')} | {r.get('format','?')} | {r.get('team','?')} "
            f"| {r.get('bat_matches',0)} | {r.get('runs',0)} "
            f"| {r.get('avg') or '-'} | {r.get('strike_rate') or '-'} "
            f"| {r.get('fours',0)} | {r.get('sixes',0)} "
            f"| {r.get('wickets',0)} | {r.get('economy') or '-'} |"
        )
    # Aggregate summary across all returned rows
    if len(rows) > 1:
        total_runs = sum(r.get("runs", 0) or 0 for r in rows)
        total_matches = sum(r.get("bat_matches", 0) or 0 for r in rows)
        total_wkts = sum(r.get("wickets", 0) or 0 for r in rows)
        avgs = [r["avg"] for r in rows if r.get("avg")]
        agg_avg = round(sum(avgs) / len(avgs), 2) if avgs else "-"
        srs = [r["strike_rate"] for r in rows if r.get("strike_rate")]
        agg_sr = round(sum(srs) / len(srs), 2) if srs else "-"
        lines.append(f"\n**Aggregate across {len(rows)} season(s):** "
                     f"{total_matches} matches, {total_runs} runs, "
                     f"Avg {agg_avg}, SR {agg_sr}, {total_wkts} wickets")
    return "\n".join(lines)


def _format_recent_form(team: str, rows: list[dict]) -> str:
    lines = [f"## Recent Form: {team}\n"]
    for r in rows:
        icon = "✅" if r.get("result") == "won" else ("❌" if r.get("result") == "lost" else "➖")
        lines.append(
            f"{icon} {r.get('date', '')} vs {r.get('opponent', 'N/A')} "
            f"({r.get('format', '')}) — {r.get('result', 'N/A')}"
            + (f" — {r['margin']}" if r.get("margin") else "")
        )
    return "\n".join(lines)


def _format_leaderboard(category: str, rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return f"No {category} leaderboard data found."
    lines = [f"## Top {category} Players\n"]
    header = " | ".join(c.replace("_", " ").title() for c in cols)
    lines.append(f"| {header} |")
    lines.append("|" + "---|" * len(cols))
    for r in rows:
        cells = " | ".join(str(r.get(c, "-")) for c in cols)
        lines.append(f"| {cells} |")
    return "\n".join(lines)


def _format_venue_stats(data: dict) -> str:
    lines = [f"## Venue Stats: {data.get('venue', 'Unknown')}\n"]
    lines.append(f"**Total matches in data:** {data.get('total_matches', 0)}")
    fmt_bd = data.get("format_breakdown", {})
    if fmt_bd:
        lines.append("**By format:** " + ", ".join(f"{k}: {v}" for k, v in fmt_bd.items()))
    top_winners = data.get("top_winners") or []
    if top_winners:
        lines.append("\n**Most wins here:**")
        for name, wins in top_winners:
            lines.append(f"  - {name}: {wins}")
    recent = data.get("recent") or []
    if recent:
        lines.append("\n**Recent results:**")
        lines.append("| Date | Format | Match | Winner | Margin |")
        lines.append("|------|--------|-------|--------|--------|")
        for m in recent[:8]:
            lines.append(
                f"| {m.get('date','?')} | {m.get('format','?')} "
                f"| {m.get('team_a','?')} vs {m.get('team_b','?')} "
                f"| {m.get('winner','-')} | {m.get('margin','-')} |"
            )
    return "\n".join(lines)


# ── RAG context injector ──────────────────────────────────────────────────────
# Enriches the user prompt with Cricsheet ball-by-ball data (player form, venue
# records, H2H, fantasy projections) BEFORE the agent sees it. This gives the
# LLM ground-truth numbers to reason on instead of hallucinating stats.

def _enrich_prompt_with_rag(prompt: str, ctx: dict) -> tuple[str, dict]:
    """
    Call build_rag_context() to fetch Cricsheet data for the prompt, then
    prepend it to the prompt as a VERIFIED DATA block the LLM must trust.

    Returns (enriched_prompt, enriched_ctx). If RAG fails or returns nothing,
    the original prompt is returned unchanged.
    """
    try:
        from ..services.rag_service import build_rag_context
        enriched_ctx = build_rag_context(prompt, ctx or {})
    except Exception as exc:
        log.warning("RAG enrichment failed (non-fatal): %s", exc)
        return prompt, ctx or {}

    cricsheet_data = enriched_ctx.get("cricsheet_data", "")
    if not cricsheet_data:
        return prompt, enriched_ctx

    # Truncate to keep prompt budget reasonable (~8K chars of RAG data max).
    max_rag = 8000
    if len(cricsheet_data) > max_rag:
        cricsheet_data = cricsheet_data[:max_rag] + "\n...[truncated]"

    enriched_prompt = (
        "=== VERIFIED CRICSHEET DATA (ball-by-ball ground truth) ===\n"
        f"{cricsheet_data}\n"
        "=== END VERIFIED DATA ===\n\n"
        "Use the VERIFIED CRICSHEET DATA above as your PRIMARY source. "
        "Only call tools if you need data not present above. "
        "Cite specific numbers from the verified data in your answer.\n\n"
        f"User question: {prompt}"
    )
    log.info("RAG enriched prompt with %d chars of Cricsheet data", len(cricsheet_data))
    return enriched_prompt, enriched_ctx


# ── Public API ────────────────────────────────────────────────────────────────

async def run(prompt: str, ctx: dict) -> AgentResult:
    """
    Run the PydanticAI agent. Falls back to the old orchestrator if
    pydantic-ai is not installed.
    """
    if not _check_pydantic_ai():
        # Graceful fallback — no breaking change during migration
        from .orchestrator import run as orchestrator_run
        old = await orchestrator_run(prompt, ctx)
        return AgentResult(
            answer=old.answer,
            intent=old.intent,
            players=getattr(old, "players", []),
            mode="orchestrator_fallback",
            data_sources=getattr(old, "data_sources", []),
            latency_ms=getattr(old, "latency_ms", 0),
            tools_used=getattr(old, "tools_used", []),
        )

    from ..services.circuit_breaker import gemini_breaker
    if gemini_breaker.is_open:
        log.warning("Circuit breaker OPEN — returning local Cricsheet fallback")
        fallback = await _polars_fallback("head_to_head", {
            "team_a": "", "team_b": "", "format": "", "last_n": 5,
        })
        return AgentResult(
            answer=(
                "⚠️ AI quota exhausted — here's what local data says:\n\n" + fallback
            ),            mode="circuit_breaker",
            intent="general",
        )
    t0 = time.monotonic()

    try:
        from ..db.connection import get_pool
        pool = await get_pool()
        agent = _build_agent()
        deps  = CricketDeps(
            db_pool=pool,
            session_id=ctx.get("session_id", "default"),
        )
        # Inject Cricsheet RAG data into the prompt so the LLM grounds on
        # real numbers (player form, venue, H2H, fantasy projections).
        enriched_prompt, _ = _enrich_prompt_with_rag(prompt, ctx)
        result = await agent.run(enriched_prompt, deps=deps)

        answer     = result.output if isinstance(result.output, str) else str(result.output)
        tools_used = _extract_tools_used(result)

        # Record success to circuit breaker
        if hasattr(gemini_breaker, "record_success"):
            gemini_breaker.record_success()

        return AgentResult(
            answer=answer,
            intent=_infer_intent(tools_used),
            mode="agent",
            data_sources=_infer_sources(pool),
            latency_ms=int((time.monotonic() - t0) * 1000),
            tools_used=tools_used,
        )

    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        err_str = str(exc).lower()

        if any(x in err_str for x in ("quota", "rate limit", "429", "resource_exhausted")):
            gemini_breaker.trip()
            log.warning("LLM quota exhausted — tripping circuit breaker")
            return AgentResult(
                answer="⚠️ AI quota exhausted. Please try again later.",
                mode="circuit_breaker",
                intent="general",
                latency_ms=elapsed,
                error=str(exc),
            )

        log.exception("Agent error after %dms: %s", elapsed, exc)
        return AgentResult(
            answer=f"❌ Agent error: {exc}",
            mode="error",
            intent="general",
            latency_ms=elapsed,
            error=str(exc),
        )


async def stream(prompt: str, ctx: dict) -> AsyncIterator[str]:
    """
    Stream the agent response token by token.
    Used by the SSE /api/ask/stream endpoint.
    Yields string chunks as they arrive from the LLM.
    """
    if not _check_pydantic_ai():
        # Fallback: run non-streaming and yield the full answer at once
        result = await run(prompt, ctx)
        yield result.answer
        return

    from ..db.connection import get_pool
    from ..services.circuit_breaker import gemini_breaker
    if gemini_breaker.is_open:
        yield "⚠️ AI quota exhausted — please try again later."
        return

    try:
        pool  = await get_pool()
        agent = _build_agent()
        deps  = CricketDeps(
            db_pool=pool,
            session_id=ctx.get("session_id", "default"),
        )
        # Inject Cricsheet RAG data so the streaming LLM grounds on real numbers.
        enriched_prompt, _ = _enrich_prompt_with_rag(prompt, ctx)
        async with agent.run_stream(enriched_prompt, deps=deps) as streamed:
            async for chunk in streamed.stream_text(delta=True):
                yield chunk

        if hasattr(gemini_breaker, "record_success"):
            gemini_breaker.record_success()

    except Exception as exc:
        import re as _re
        raw_err = str(exc)
        err_str = raw_err.lower()
        # Sanitize before any logging or surfacing — Google embeds the key in 403 bodies
        safe_err = _re.sub(r"api_key:[A-Za-z0-9_\-]+", "api_key:[REDACTED]", raw_err)
        safe_err = _re.sub(r"'[A-Za-z0-9_\-]{20,}'", "'[REDACTED]'", safe_err)

        # On 503/overload/quota: try Groq fallback via non-streaming llm_client
        # (yields the full answer at once instead of streaming chunks).
        is_overload = any(x in err_str for x in ("503", "unavailable", "overloaded", "high demand"))
        is_quota    = any(x in err_str for x in ("quota", "rate limit", "429", "resource_exhausted"))

        if is_overload or is_quota:
            if is_quota:
                gemini_breaker.trip()
            log.warning("Stream error (%s) - trying Groq fallback", "quota" if is_quota else "503")
            try:
                from ..services.llm_client import _groq_response, GROQ_API_KEY
                if GROQ_API_KEY:
                    groq_answer = _groq_response(prompt, ctx or {})
                    if groq_answer and not groq_answer.startswith("❌"):
                        yield groq_answer + "\n\n*(answered by Groq fallback - Gemini was overloaded)*"
                        return
            except Exception as groq_exc:
                log.warning("Groq fallback also failed: %s", str(groq_exc)[:200])
            # Groq unavailable or failed
            if is_quota:
                yield "⚠️ AI quota exhausted. Please try again later."
            else:
                yield "⚠️ Gemini is currently overloaded and no fallback is configured. Please try again in 30 seconds."
        elif any(x in err_str for x in ("403", "permission_denied", "consumer_suspended")):
            log.error("Stream error (key suspended/invalid): %s", safe_err[:200])
            yield "⚠️ The AI service API key has been suspended or is invalid. Please update the GEMINI_API_KEY in the server environment."
        else:
            log.exception("Stream error: %s", safe_err[:200])
            yield f"❌ Error: {safe_err[:300]}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_tools_used(result) -> list[str]:
    """Extract tool names from PydanticAI AgentRunResult messages."""
    tools: list[str] = []
    try:
        from pydantic_ai.messages import ToolCallPart
        for msg in result.all_messages():
            if hasattr(msg, "parts"):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        tools.append(part.tool_name)
    except Exception:
        pass
    return list(dict.fromkeys(tools))   # deduplicate preserving order


def _infer_intent(tools_used: list[str]) -> str:
    if "live_score" in tools_used:
        return "live"
    if "head_to_head" in tools_used:
        return "head_to_head"
    if "top_players" in tools_used:
        return "ranking"
    if "player_stats" in tools_used:
        return "batting_stats"
    if "recent_form" in tools_used:
        return "form"
    if "semantic_search" in tools_used:
        return "general"
    return "general"


def _infer_sources(pool) -> list[str]:
    sources = ["Cricsheet"]
    if pool:
        sources.append("PostgreSQL")
    return sources
