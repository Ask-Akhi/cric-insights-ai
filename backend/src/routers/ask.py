from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from ..services.llm_client import get_llm_response, get_llm_response_grounded
from ..services.rag_service import build_rag_context, detect_players_in_prompt
import logging
import asyncio

log = logging.getLogger(__name__)

# Railway hard-kills connections at 60s — give ourselves 55s before that
_ASK_TIMEOUT = 55

# cricket_graph is imported lazily inside the endpoint to avoid blocking startup
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
    data_sources: List[str] = []   # ["Cricsheet RAG", "Google Search", "Gemini training data"]


_FALLBACK = (
    "🏏 I'm your **Cricket Insights AI** — powered by LangGraph + Cricsheet data.\n\n"
    "I couldn't generate a response. Please try:\n"
    "- A specific player name (e.g. *Virat Kohli*, *Jasprit Bumrah*)\n"
    "- A cricket topic (fantasy XI, match prediction, venue stats)\n"
    "- Checking that your API key is set in Railway Variables"
)


def _has_rag_data(enriched: Dict[str, Any]) -> bool:
    """True if Cricsheet RAG found any local ball-by-ball data for this query."""
    return bool(enriched.get("cricsheet_data", "").strip())


@router.post("", response_model=AskResponse)
@router.post("/", response_model=AskResponse)
async def ask(req: AskRequest):
    ctx = req.context or {}

    # ── ALWAYS run RAG first ─────────────────────────────────────────────────
    # Injects Cricsheet ball-by-ball stats, player averages, H2H, venue records,
    # and fantasy prediction data into the context for ALL LLM calls below.
    enriched = build_rag_context(req.prompt, ctx)
    players = detect_players_in_prompt(req.prompt)
    has_rag = _has_rag_data(enriched)
    data_sources: List[str] = []
    if has_rag:
        data_sources.append("Cricsheet RAG")
        log.info(f"RAG: found local data for '{req.prompt[:60]}'")
    else:
        log.info(f"RAG: no local Cricsheet data for '{req.prompt[:60]}'")    # ── GROUNDED path ────────────────────────────────────────────────────────
    if req.grounded:
        answer = ""        # Tier 1: RAG context + Google Search grounding
        # → Best answer: verified Cricsheet stats + live web data
        # Wrapped in asyncio.wait_for so Railway's 60s hard-kill never fires first.
        # Use get_running_loop() — get_event_loop() is deprecated in Python 3.10+
        try:
            loop = asyncio.get_running_loop()
            answer = await asyncio.wait_for(
                loop.run_in_executor(
                    None, get_llm_response_grounded, req.prompt, enriched
                ),
                timeout=_ASK_TIMEOUT,
            )
            if answer and answer.strip() and not answer.startswith("❌"):
                data_sources.append("Google Search")
                log.info("Grounded Tier 1: OK")
            else:
                log.warning(f"Grounded Tier 1 empty/error ({answer!r:.80}) — trying Tier 2")
                answer = ""
        except asyncio.TimeoutError:
            log.warning("Grounded Tier 1 timed out — trying Tier 2")
            answer = ""
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            log.warning(f"Grounded Tier 1 exception: {e} — trying Tier 2")
            answer = ""

        # Tier 2: RAG context + Gemini training data (no web search)
        # → Still accurate for historical players; RAG injects any local Cricsheet stats        if not answer:
            log.info("Grounded Tier 2: RAG + non-grounded Gemini training data")
            try:
                answer = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, get_llm_response, req.prompt, enriched
                    ),
                    timeout=_ASK_TIMEOUT,
                )
                if answer and answer.strip() and not answer.startswith("❌"):
                    if has_rag:
                        note = "\n\n---\n> ℹ️ *Web search unavailable — using Cricsheet local data + Gemini training knowledge.*"
                    else:
                        note = "\n\n---\n> ℹ️ *Web search unavailable and no local Cricsheet data found for these players — using Gemini training knowledge only.*"
                    answer = answer + note
                    data_sources.append("Gemini training data")
                    log.info("Grounded Tier 2: OK")
                else:
                    log.warning(f"Grounded Tier 2 empty/error: {answer!r:.80}")
                    answer = ""
            except asyncio.TimeoutError:
                log.warning("Grounded Tier 2 timed out — returning 504")
                raise HTTPException(
                    status_code=504,
                    detail="Request timed out — the AI took too long. Please try a shorter or simpler question.",
                )
            except Exception as e:
                log.warning(f"Grounded Tier 2 failed: {e}")
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
        )

    # ── LangGraph multi-step pipeline (non-grounded) ─────────────────────────
    # Pass the RAG-enriched context so graph nodes have local Cricsheet stats too.
    try:
        from ..services.cricket_graph import run_graph
        result = await asyncio.wait_for(
            run_graph(req.prompt, enriched),
            timeout=_ASK_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.warning(f"LangGraph timed out for prompt: '{req.prompt[:60]}'")
        raise HTTPException(
            status_code=504,
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
    )
