from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from ..services.llm_client import get_llm_response_grounded
from ..services.rag_service import build_rag_context, detect_players_in_prompt
from ..services import llm_cache, token_tracker
from ..core.config import settings
import logging
import asyncio
import time

log = logging.getLogger(__name__)

# Railway hard-kills connections at 60s — budget ladder:
#   Tier 1 (grounded web search): 44s — web search (10-25s) + LLM generation (5-15s)
#   Tier 2 (LangGraph, no web):   44s — used when Tier 1 times out OR returns an error immediately.
#     When Tier 1 fails fast (error, not timeout), full 44s is available for Tier 2.
#     When Tier 1 times out (44s), only ~14s is left before Railway kills at 60s — Tier 2 is skipped.
#   Non-grounded path: 52s full budget for LangGraph.
_ASK_TIMEOUT          = 52   # non-grounded / LangGraph path
_ASK_TIMEOUT_GROUNDED = 44   # grounded Tier 1
_ASK_TIMEOUT_TIER2    = 44   # Tier 2 budget — full when Tier 1 fails fast, capped by remaining wall time

router = APIRouter()


class AskRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None
    grounded: bool = False
    use_graph: bool = True


class AskResponse(BaseModel):
    answer: str
    intent: str = "general"
    players: List[str] = []
    mode: str = "graph"
    data_sources: List[str] = []
    latency_ms: int = 0
    rag_cache_hit: bool = False


def _api_error(status: int, code: str, message: str, detail: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


_FALLBACK = (
    "🏏 I'm your **Cricket Insights AI** — powered by LangGraph + Cricsheet data.\n\n"
    "I couldn't generate a response. Please try:\n"
    "- A specific player name (e.g. *Virat Kohli*, *Jasprit Bumrah*)\n"
    "- A cricket topic (fantasy XI, match prediction, venue stats)\n"
    "- Checking that your API key is set in Railway Variables"
)


def _has_rag_data(enriched: Dict[str, Any]) -> bool:
    return bool(enriched.get("cricsheet_data", "").strip())


@router.post("", response_model=AskResponse)
@router.post("/", response_model=AskResponse)
async def ask(req: AskRequest):
    _t0 = time.monotonic()
    ctx = req.context or {}
    fmt = ctx.get("format", "")

    # ── Ask-level cache — biggest single cost saver ───────────────────────
    cached = llm_cache.get(req.prompt, req.grounded, fmt)
    if cached:
        token_tracker.record(cached=True, intent=cached.get("intent", "general"))
        cached["answer"] = f"⚡ *(cached)*\n\n{cached['answer']}"
        cached["latency_ms"] = int((time.monotonic() - _t0) * 1000)
        log.info("ask-cache HIT — returning in %dms", cached["latency_ms"])
        return AskResponse(**cached)

    # ── MCP path (primary) ──────────────────────────────────────────────
    if settings.mcp_enabled:
        try:
            from ..mcp.orchestrator import run as mcp_run

            mcp_result = await asyncio.wait_for(
                mcp_run(req.prompt, ctx),
                timeout=settings.tier2_budget_s,
            )
            if mcp_result.answer and not mcp_result.answer.startswith("❌"):
                resp_dict = dict(
                    answer=mcp_result.answer,
                    intent=mcp_result.intent,
                    players=mcp_result.players,
                    mode=mcp_result.mode,
                    data_sources=mcp_result.data_sources,
                    latency_ms=mcp_result.latency_ms,
                    rag_cache_hit=False,
                )
                llm_cache.put(req.prompt, req.grounded, fmt, resp_dict)
                token_tracker.record(
                    prompt=req.prompt, response=mcp_result.answer,
                    intent=mcp_result.intent, grounded=req.grounded,
                )
                log.info(
                    "MCP path OK in %dms — tools=%s, intent=%s",
                    mcp_result.latency_ms, mcp_result.tools_used, mcp_result.intent,
                )
                return AskResponse(**resp_dict)
            else:
                log.info("MCP path returned empty/error — falling through to legacy path")
        except asyncio.TimeoutError:
            log.warning("MCP path timed out after %ds — falling through to legacy path", settings.tier2_budget_s)
        except Exception as e:
            log.warning("MCP path failed: %s — falling through to legacy path", e)

    # ── Legacy path (RAG → grounded → LangGraph) ─────────────────────────
    # Always run RAG first
    enriched = build_rag_context(req.prompt, ctx)
    players = detect_players_in_prompt(req.prompt)
    has_rag = _has_rag_data(enriched)
    rag_cache_hit = bool(enriched.get("_rag_cache_hit"))
    data_sources: List[str] = []
    if has_rag:
        data_sources.append("Cricsheet RAG")
        log.info(
            "RAG: found local data for '%s' (cache_hit=%s, blocks=%s)",
            req.prompt[:60], rag_cache_hit, enriched.get("_reranked_blocks", "?"),
        )
    else:
        log.info("RAG: no local Cricsheet data for '%s'", req.prompt[:60])

    # Grounded path (web search)
    if req.grounded:
        answer = ""

        # Tier 1: Google Search grounding + RAG context
        try:
            loop = asyncio.get_running_loop()
            answer = await asyncio.wait_for(
                loop.run_in_executor(
                    None, get_llm_response_grounded, req.prompt, enriched
                ),
                timeout=_ASK_TIMEOUT_GROUNDED,
            )
            if answer and answer.strip() and not answer.startswith("❌"):
                data_sources.append("Google Search")
                log.info("Grounded Tier 1: OK (%.1fs)", time.monotonic() - _t0)
            else:
                log.warning("Grounded Tier 1 empty/error (%.1fs): %.120s — trying Tier 2",
                            time.monotonic() - _t0, answer)
                answer = ""
        except asyncio.TimeoutError:
            log.warning("Grounded Tier 1 timed out after %ds — trying Tier 2", _ASK_TIMEOUT_GROUNDED)
            answer = ""
        except ValueError as e:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "GROUNDED_ERROR",
                        "message": str(e),
                        "detail": "Google Search grounding failed.",
                        "retry_with_graph": True,
                    }
                },
            )
        except Exception as e:
            log.warning("Grounded Tier 1 exception: %s — trying Tier 2", e)
            answer = ""

        # Tier 2: LangGraph (no web search, uses pre-built RAG — 8-15s)
        if not answer:
            # Use the smaller of _ASK_TIMEOUT_TIER2 and whatever wall-time budget remains
            # before Railway's 60s kill. Leave 3s margin.
            elapsed_so_far = time.monotonic() - _t0
            tier2_budget = min(_ASK_TIMEOUT_TIER2, max(5.0, 57.0 - elapsed_so_far))
            log.info("Grounded Tier 2: LangGraph fallback (%.1fs elapsed, %.0fs budget)",
                     elapsed_so_far, tier2_budget)
            try:
                from ..services.cricket_graph import run_graph
                tier2_result = await asyncio.wait_for(
                    run_graph(req.prompt, enriched),
                    timeout=tier2_budget,
                )
                answer = tier2_result.get("answer", "")
                if answer and answer.strip() and not answer.startswith("❌"):
                    note = (
                        "\n\n---\n> ℹ️ *Web search unavailable — answer uses Cricsheet local data + Gemini knowledge.*"
                        if has_rag else
                        "\n\n---\n> ℹ️ *Web search unavailable and no local Cricsheet data found — using Gemini knowledge only.*"
                    )
                    answer = answer + note
                    data_sources.extend(
                        s for s in ["LangGraph", "Cricsheet RAG"] if s not in data_sources
                    )
                    log.info("Grounded Tier 2: OK (mode=%s)", tier2_result.get("mode"))
                else:
                    log.warning("Grounded Tier 2 empty/error")
                    answer = ""
            except asyncio.TimeoutError:
                log.warning("Grounded Tier 2 timed out after %.0fs", tier2_budget)
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "TIMEOUT",
                            "message": "Request timed out — the AI took too long. Please try a shorter or simpler question.",
                            "detail": "Both grounded search and LangGraph fallback timed out.",
                            "retry_with_graph": True,
                        }
                    },
                )
            except Exception as e:
                log.warning("Grounded Tier 2 failed: %s", e)
                answer = ""

        # Tier 3: Never show a blank screen
        if not answer:
            answer = _FALLBACK

        # mode="fallback" when web search didn't contribute (Tier 2 was used)
        response_mode = "grounded" if "Google Search" in data_sources else "fallback"

        resp_dict = dict(
            answer=answer,
            intent="general",
            players=players,
            mode=response_mode,
            data_sources=data_sources,
            latency_ms=int((time.monotonic() - _t0) * 1000),
            rag_cache_hit=rag_cache_hit,
        )
        # Cache successful responses (skip fallback text)
        if answer and answer != _FALLBACK:
            llm_cache.put(req.prompt, req.grounded, fmt, resp_dict)
        token_tracker.record(
            prompt=req.prompt, response=answer,
            intent="general", grounded=True,
        )
        return AskResponse(**resp_dict)

    # LangGraph multi-step pipeline (non-grounded)
    try:
        from ..services.cricket_graph import run_graph
        result = await asyncio.wait_for(
            run_graph(req.prompt, enriched),
            timeout=_ASK_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.warning("LangGraph timed out for prompt: '%s'", req.prompt[:60])
        raise HTTPException(
            status_code=503,
            detail="Request timed out — the AI took too long. Please try a shorter or simpler question.",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    answer = result.get("answer", "")
    if not answer or not answer.strip():
        answer = _FALLBACK

    if has_rag:
        data_sources.append("Cricsheet RAG")
    data_sources.append("LangGraph")

    resp_dict = dict(
        answer=answer,
        intent=result.get("intent", "general"),
        players=result.get("players", []),
        mode=result.get("mode", "graph"),
        data_sources=data_sources,
        latency_ms=int((time.monotonic() - _t0) * 1000),
        rag_cache_hit=rag_cache_hit,
    )
    # Cache successful responses
    if answer and answer != _FALLBACK:
        llm_cache.put(req.prompt, req.grounded, fmt, resp_dict)
    token_tracker.record(
        prompt=req.prompt, response=answer,
        intent=result.get("intent", "general"), grounded=False,
    )
    return AskResponse(**resp_dict)
