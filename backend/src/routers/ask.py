from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
from ..services.llm_client import get_llm_response, get_llm_response_grounded
from ..services.rag_service import build_rag_context

router = APIRouter()

class AskRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = {}
    grounded: bool = True

@router.post("")
@router.post("/")
def ask(req: AskRequest):
    ctx = req.context or {}

    # ── RAG enrichment: detect players, inject Cricsheet stats ──────────────
    enriched_ctx = build_rag_context(req.prompt, ctx)

    # ── Non-cricket guard ────────────────────────────────────────────────────
    # Still call the LLM — it will handle the response gracefully per our
    # system prompt instructions. The _is_cricket flag is just metadata.

    try:
        if req.grounded:
            answer = get_llm_response_grounded(req.prompt, enriched_ctx)
        else:
            answer = get_llm_response(req.prompt, enriched_ctx)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # ── Never return null ────────────────────────────────────────────────────
    if not answer or answer.strip() == "":
        answer = (
            "🏏 I'm your Cricket Insights AI assistant. I specialise in cricket stats, "
            "match analysis, fantasy teams, and player insights using verified Cricsheet data.\n\n"
            "I couldn't find a specific answer to your question. This could be because:\n"
            "- The player or topic isn't in my cricket database\n"
            "- The question may be outside cricket\n\n"
            "Try asking about a known cricketer (e.g. Virat Kohli, Rohit Sharma, Jasprit Bumrah) "
            "or a cricket topic like match predictions, fantasy XI, or venue stats."
        )

    return {"answer": answer}
