"""
Ask router — sole entry point for POST /api/ask.

Pipeline:
  1. Cache hit        → return immediately (0 LLM cost)
  2. MCP orchestrator → intent → tools → context → 1 LLM call
                        (circuit breaker serves local Cricsheet data on quota)
  3. Timeout / error  → 503 with actionable message

The legacy LangGraph / grounded-search fallback path has been retired.
All intents — including quota fallback — are handled by the MCP orchestrator.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from ..services import llm_cache, token_tracker
from ..core.config import settings
import logging
import asyncio
import time

log = logging.getLogger(__name__)

router = APIRouter()


class AskRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None
    grounded: bool = False   # kept for API compat; MCP handles grounding internally
    use_graph: bool = True   # kept for API compat; always uses MCP pipeline


class AskResponse(BaseModel):
    answer: str
    intent: str = "general"
    players: List[str] = []
    mode: str = "mcp"
    data_sources: List[str] = []
    latency_ms: int = 0
    rag_cache_hit: bool = False
    tools_used: List[str] = []





@router.post("", response_model=AskResponse)
@router.post("/", response_model=AskResponse)
async def ask(req: AskRequest):
    _t0 = time.monotonic()
    ctx = req.context or {}
    fmt = ctx.get("format", "")

    # ── 1. Cache hit ──────────────────────────────────────────────────────
    cached = llm_cache.get(req.prompt, req.grounded, fmt)
    if cached:
        token_tracker.record(cached=True, intent=cached.get("intent", "general"))
        cached["answer"] = f"⚡ *(cached)*\n\n{cached['answer']}"
        cached["latency_ms"] = int((time.monotonic() - _t0) * 1000)
        log.info("ask-cache HIT — returning in %dms", cached["latency_ms"])
        return AskResponse(**cached)

    # ── 2. Guard: MCP must be enabled ────────────────────────────────────
    if not settings.mcp_enabled:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "MCP_DISABLED",
                               "message": "AI pipeline is disabled. Set MCP_ENABLED=true.",
                               "detail": ""}},
        )

    # ── 3. MCP pipeline ───────────────────────────────────────────────────
    try:
        from ..mcp.orchestrator import run as mcp_run

        mcp_result = await asyncio.wait_for(
            mcp_run(req.prompt, ctx),
            timeout=settings.tier2_budget_s + 3,   # +3s slack — internal deadline fires first
        )
    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - _t0) * 1000)
        log.warning("MCP pipeline timed out after %dms", elapsed_ms)
        return JSONResponse(
            status_code=503,
            content={"error": {
                "code": "TIMEOUT",
                "message": "Request timed out — please try a shorter or simpler question.",
                "detail": f"MCP pipeline timed out after {elapsed_ms}ms.",
            }},
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - _t0) * 1000)
        log.exception("MCP pipeline error after %dms: %s", elapsed_ms, exc)
        return JSONResponse(
            status_code=503,
            content={"error": {
                "code": "MCP_ERROR",
                "message": "The AI pipeline encountered an unexpected error.",
                "detail": str(exc),
            }},
        )

    # ── 4. Hard-error sentinel ────────────────────────────────────────────
    if not mcp_result.answer or mcp_result.answer.startswith("❌"):
        elapsed_ms = int((time.monotonic() - _t0) * 1000)
        log.warning("MCP returned empty/error answer after %dms", elapsed_ms)
        return JSONResponse(
            status_code=503,
            content={"error": {
                "code": "MCP_EMPTY",
                "message": mcp_result.answer or "AI could not generate a response.",
                "detail": f"Elapsed {elapsed_ms}ms.",
            }},
        )

    # ── 5. Success — cache + return ───────────────────────────────────────
    resp_dict: Dict[str, Any] = dict(
        answer=mcp_result.answer,
        intent=mcp_result.intent,
        players=mcp_result.players,
        mode=mcp_result.mode,
        data_sources=mcp_result.data_sources,
        latency_ms=mcp_result.latency_ms,
        rag_cache_hit=False,
        tools_used=mcp_result.tools_used or [],
    )

    # Only cache real answers — not quota/timeout notes
    if not mcp_result.answer.startswith(("⚠️", "⏱️")):
        llm_cache.put(req.prompt, req.grounded, fmt, resp_dict)

    token_tracker.record(
        prompt=req.prompt, response=mcp_result.answer,
        intent=mcp_result.intent, grounded=req.grounded,
    )
    log.info(
        "ask OK %dms — intent=%s tools=%s",
        mcp_result.latency_ms, mcp_result.intent, mcp_result.tools_used,
    )
    return AskResponse(**resp_dict)
