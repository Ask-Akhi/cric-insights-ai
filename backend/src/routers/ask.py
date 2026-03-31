from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from ..services.llm_client import get_llm_response, get_llm_response_grounded
from ..services.rag_service import build_rag_context, detect_players_in_prompt
import logging
import asyncio
import time

log = logging.getLogger(__name__)

# Railway hard-kills connections at 60s — give ourselves 52s before that.
# Grounded (web search) path gets 45s, Tier 2 fallback gets 30s.
_ASK_TIMEOUT          = 52   # non-grounded / graph path
_ASK_TIMEOUT_GROUNDED = 45   # grounded Tier 1 (web search call)
_ASK_TIMEOUT_TIER2    = 30   # grounded Tier 2 fallback (no web, just LLM)

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
                log.info("Grounded Tier 1: OK")
            else:
                log.warning("Grounded Tier 1 empty/error — trying Tier 2")
                answer = ""
        except asyncio.TimeoutError:
            log.warning("Grounded Tier 1 timed out after %ds — trying Tier 2", _ASK_TIMEOUT_GROUNDED)
            answer = ""
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            log.warning("Grounded Tier 1 exception: %s — trying Tier 2", e)
            answer = ""

        # Tier 2: RAG + Gemini training data (no web search, faster)
        if not answer:
            log.info("Grounded Tier 2: RAG + Gemini training data (no web search)")
            try:
                loop = asyncio.get_running_loop()
                answer = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, get_llm_response, req.prompt, enriched
                    ),
                    timeout=_ASK_TIMEOUT_TIER2,
                )
                if answer and answer.strip() and not answer.startswith("❌"):
                    note = (
                        "\n\n---\n> ℹ️ *Web search unavailable — using Cricsheet local data + Gemini training knowledge.*"
                        if has_rag else
                        "\n\n---\n> ℹ️ *Web search unavailable and no local Cricsheet data found — using Gemini training knowledge only.*"
                    )
                    answer = answer + note
                    data_sources.append("Gemini training data")
                    log.info("Grounded Tier 2: OK")
                else:
                    log.warning("Grounded Tier 2 empty/error")
                    answer = ""
            except asyncio.TimeoutError:
                log.warning("Grounded Tier 2 timed out")
                raise HTTPException(
                    status_code=503,
                    detail="Request timed out — the AI took too long. Please try a shorter or simpler question.",
                )
            except Exception as e:
                log.warning("Grounded Tier 2 failed: %s", e)
                answer = ""

        # Tier 3: Never show a blank screen
        if not answer:
            answer = _FALLBACK

        return AskResponse(
            answer=answer,
            intent="general",
            players=players,
            mode="grounded",
            data_sources=data_sources,
            latency_ms=int((time.monotonic() - _t0) * 1000),
            rag_cache_hit=rag_cache_hit,
        )

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

    return AskResponse(
        answer=answer,
        intent=result.get("intent", "general"),
        players=result.get("players", []),
        mode=result.get("mode", "graph"),
        data_sources=data_sources,
        latency_ms=int((time.monotonic() - _t0) * 1000),
        rag_cache_hit=rag_cache_hit,
    )
