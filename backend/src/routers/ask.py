from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from ..services.llm_client import get_llm_response_grounded
from ..services.rag_service import build_rag_context, detect_players_in_prompt
# cricket_graph is imported lazily inside the endpoint to avoid blocking startup

router = APIRouter()


class AskRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None
    grounded: bool = False          # grounded search bypasses graph (uses Google Search)
    use_graph: bool = True          # set False to force legacy single-LLM path


class AskResponse(BaseModel):
    answer: str
    intent: str = "general"        # stats | compare | fantasy | predict | general
    players: List[str] = []        # detected player names
    mode: str = "graph"            # graph | direct | fallback


_FALLBACK = (
    "🏏 I'm your **Cricket Insights AI** — powered by LangGraph + Cricsheet data.\n\n"
    "I couldn't generate a response. Please try:\n"
    "- A specific player name (e.g. *Virat Kohli*, *Jasprit Bumrah*)\n"
    "- A cricket topic (fantasy XI, match prediction, venue stats)\n"
    "- Checking that your API key is set in Railway Variables"
)


@router.post("", response_model=AskResponse)
@router.post("/", response_model=AskResponse)
async def ask(req: AskRequest):
    ctx = req.context or {}

    # ── Grounded path: Google Search + Cricsheet data ────────────────────────
    # RAG enrichment runs first so Cricsheet ball-by-ball stats are injected
    # into the context alongside the web search result — best of both sources.
    if req.grounded:
        enriched = build_rag_context(req.prompt, ctx)
        players = detect_players_in_prompt(req.prompt)
        try:
            answer = get_llm_response_grounded(req.prompt, enriched)
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        if not answer or not answer.strip():
            answer = _FALLBACK
        return AskResponse(answer=answer, intent="general", players=players, mode="grounded")

    # ── LangGraph multi-step pipeline ─────────────────────────────────────────
    try:
        from ..services.cricket_graph import run_graph  # lazy import — avoids blocking startup
        result = await run_graph(req.prompt, ctx)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    answer = result.get("answer", "")
    if not answer or not answer.strip():
        answer = _FALLBACK

    return AskResponse(
        answer=answer,
        intent=result.get("intent", "general"),
        players=result.get("players", []),
        mode=result.get("mode", "graph"),
    )
