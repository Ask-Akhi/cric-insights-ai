"""
Ask router — POST /api/ask (blocking) + POST /api/ask/stream (SSE).

Pipeline:
  1. Cache check  (Upstash Redis → in-process LRU fallback)  → return immediately
  2. Agent run    (PydanticAI + PostgreSQL tools)
     Fallback:    old MCP orchestrator when pydantic-ai not installed
  3. Timeout / error → 503 with actionable message

SSE streaming endpoint: POST /api/ask/stream
  Returns text/event-stream; frontend renders tokens as they arrive.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..core.config import settings
from ..services import token_tracker
from ..services.cache import cache as _cache
from ..services import llm_cache as _legacy_cache

log = logging.getLogger(__name__)
router = APIRouter()

_CACHE_TTL = settings.ask_cache_ttl_s   # 1800 s default


class AskRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None
    grounded: bool = False   # kept for API compat
    use_graph: bool = True   # kept for API compat


class AskResponse(BaseModel):
    answer: str
    intent: str = "general"
    players: List[str] = []
    mode: str = "agent"
    data_sources: List[str] = []
    latency_ms: int = 0
    rag_cache_hit: bool = False
    tools_used: List[str] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cache_key(prompt: str, grounded: bool, fmt: str) -> str:
    return f"ask:{grounded}:{fmt}:{prompt}"


async def _get_cached(prompt: str, grounded: bool, fmt: str) -> Optional[dict]:
    hit = await _cache.get(_cache_key(prompt, grounded, fmt))
    if hit is None:
        hit = _legacy_cache.get(prompt, grounded, fmt)
    return hit


async def _write_cache(prompt: str, grounded: bool, fmt: str, resp: dict) -> None:
    await _cache.set(_cache_key(prompt, grounded, fmt), resp, ttl=_CACHE_TTL)
    _legacy_cache.put(prompt, grounded, fmt, resp)


async def _run_pipeline(prompt: str, ctx: dict) -> Any:
    from ..mcp.agent import run as agent_run
    return await agent_run(prompt, ctx)



@router.post("", response_model=AskResponse)
@router.post("/", response_model=AskResponse)
async def ask(req: AskRequest):
    _t0 = time.monotonic()
    ctx = req.context or {}
    fmt = ctx.get("format", "")

    # ── 1. Cache hit ──────────────────────────────────────────────────────
    cached = await _get_cached(req.prompt, req.grounded, fmt)
    if cached:
        token_tracker.record(cached=True, intent=cached.get("intent", "general"))
        cached["answer"] = f"⚡ *(cached)*\n\n{cached['answer']}"
        cached["latency_ms"] = int((time.monotonic() - _t0) * 1000)
        log.info("ask-cache HIT — returning in %dms", cached["latency_ms"])
        return AskResponse(**cached)

    # ── 2. Guard: pipeline must be enabled ───────────────────────────────
    if not settings.mcp_enabled:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "MCP_DISABLED",
                               "message": "AI pipeline is disabled. Set MCP_ENABLED=true.",
                               "detail": ""}},
        )

    # ── 3. Agent pipeline ─────────────────────────────────────────────────
    try:
        result = await asyncio.wait_for(
            _run_pipeline(req.prompt, ctx),
            timeout=settings.tier2_budget_s + 3,
        )
    except asyncio.TimeoutError:
        elapsed_ms = int((time.monotonic() - _t0) * 1000)
        log.warning("Pipeline timed out after %dms", elapsed_ms)
        return JSONResponse(
            status_code=503,
            content={"error": {
                "code": "TIMEOUT",
                "message": "Request timed out — please try a shorter or simpler question.",
                "detail": f"Pipeline timed out after {elapsed_ms}ms.",
            }},
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - _t0) * 1000)
        log.exception("Pipeline error after %dms: %s", elapsed_ms, exc)
        return JSONResponse(
            status_code=503,
            content={"error": {
                "code": "PIPELINE_ERROR",
                "message": "The AI pipeline encountered an unexpected error.",
                "detail": str(exc),
            }},
        )

    # ── 4. Hard-error sentinel ────────────────────────────────────────────
    if not result.answer or result.answer.startswith("❌"):
        elapsed_ms = int((time.monotonic() - _t0) * 1000)
        log.warning("Pipeline returned error answer after %dms", elapsed_ms)
        return JSONResponse(
            status_code=503,
            content={"error": {
                "code": "EMPTY_ANSWER",
                "message": result.answer or "AI could not generate a response.",
                "detail": f"Elapsed {elapsed_ms}ms.",
            }},
        )

    # ── 5. Success — cache + return ───────────────────────────────────────
    resp_dict: Dict[str, Any] = dict(
        answer        = result.answer,
        intent        = getattr(result, "intent", "general"),
        players       = getattr(result, "players", []),
        mode          = getattr(result, "mode", "agent"),
        data_sources  = getattr(result, "data_sources", []),
        latency_ms    = getattr(result, "latency_ms",
                                int((time.monotonic() - _t0) * 1000)),
        rag_cache_hit = False,
        tools_used    = getattr(result, "tools_used", []),
    )

    if not result.answer.startswith(("⚠️", "⏱️")):
        await _write_cache(req.prompt, req.grounded, fmt, resp_dict)

    token_tracker.record(
        prompt=req.prompt, response=result.answer,
        intent=resp_dict["intent"], grounded=req.grounded,
    )
    log.info("ask OK %dms — intent=%s tools=%s mode=%s",
             resp_dict["latency_ms"], resp_dict["intent"],
             resp_dict["tools_used"], resp_dict["mode"])
    return AskResponse(**resp_dict)


# ── POST /api/ask/stream  (SSE — tokens streamed as generated) ────────────────

@router.post("/stream")
async def ask_stream(req: AskRequest):
    """
    Server-Sent Events endpoint.

    Yields:
      data: {"chunk": "..."}\\n\\n   — partial token
      data: [DONE]\\n\\n             — stream complete
      data: {"error": "..."}\\n\\n  — on failure

    TypeScript fetch example:
      const res = await fetch("/api/ask/stream", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ prompt }),
      });
      const reader = res.body!.getReader();
      const dec    = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of dec.decode(value).split("\\n")) {
          if (!line.startsWith("data:")) continue;
          const d = line.slice(5).trim();
          if (d === "[DONE]") return;
          setAnswer(p => p + JSON.parse(d).chunk);
        }
      }
    """
    ctx = req.context or {}
    fmt = ctx.get("format", "")

    async def event_stream() -> AsyncIterator[str]:
        # 1. Cache hit
        cached = await _get_cached(req.prompt, req.grounded, fmt)
        if cached:
            log.info("ask-stream cache HIT")
            yield f"data: {json.dumps({'chunk': '⚡ *(cached)*\n\n'})}\n\n"
            yield f"data: {json.dumps({'chunk': cached['answer']})}\n\n"
            yield "data: [DONE]\n\n"
            return

        if not settings.mcp_enabled:
            yield f"data: {json.dumps({'error': 'AI pipeline disabled'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 2. Stream from agent
        from ..mcp.agent import stream as agent_stream

        full_chunks: list[str] = []
        try:
            async for chunk in agent_stream(req.prompt, ctx):
                full_chunks.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception as exc:
            log.exception("Stream error: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        yield "data: [DONE]\n\n"

        # 3. Cache the full answer for future identical queries
        full_answer = "".join(full_chunks)
        if full_answer and not full_answer.startswith(("⚠️", "❌")):
            cached_resp: Dict[str, Any] = dict(
                answer        = full_answer,
                intent        = "general",
                players       = [],
                mode          = "agent_stream",
                data_sources  = ["Cricsheet"],
                latency_ms    = 0,
                rag_cache_hit = False,
                tools_used    = [],
            )
            await _write_cache(req.prompt, req.grounded, fmt, cached_resp)

    return StreamingResponse(
        event_stream(),
        media_type = "text/event-stream",
        headers    = {
            "X-Accel-Buffering": "no",   # prevent Render/Nginx from buffering the stream
            "Cache-Control":     "no-cache",
        },
    )

