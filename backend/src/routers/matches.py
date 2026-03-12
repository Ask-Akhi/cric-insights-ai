from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class MatchInput(BaseModel):
    format: str
    venue: str
    date: str
    team_a: str
    team_b: str
    squad_a: list[str]
    squad_b: list[str]

@router.post("/")
def create_match(match: MatchInput):
    return {"received": match.model_dump()}
