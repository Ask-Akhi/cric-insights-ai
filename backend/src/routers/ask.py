from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
from ..services.llm_client import get_llm_response, get_llm_response_grounded

router = APIRouter()

class AskRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = {}
    grounded: bool = True

@router.post("")
@router.post("/")
def ask(req: AskRequest):
    ctx = req.context or {}
    try:
        if req.grounded:
            answer = get_llm_response_grounded(req.prompt, ctx)
        else:
            answer = get_llm_response(req.prompt, ctx)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"answer": answer}
