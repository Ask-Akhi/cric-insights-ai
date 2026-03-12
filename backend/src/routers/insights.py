from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from dataclasses import asdict

from ..providers.cricsheet_provider import CricsheetProvider
from ..services.stats_service import StatsService
from ..services.expected_service import ExpectedService

router = APIRouter()

# Initialize provider and services once per process
_provider = CricsheetProvider()
_provider.load()
_stats = StatsService(_provider)
_expected = ExpectedService(_provider)

class InsightsRequest(BaseModel):
    format: str
    venue: str
    team_a: str
    team_b: str
    squad_a: List[str]
    squad_b: List[str]

@router.get("")
@router.get("/")
def insights_get():
    return {"detail": "Use POST to generate insights"}

@router.post("")
@router.post("/")
def generate_insights(req: InsightsRequest):
    batters: List[Dict[str, Any]] = []
    bowlers: List[Dict[str, Any]] = []

    # Compute batter and bowler insights for all provided players
    for player in list(dict.fromkeys(req.squad_a + req.squad_b)):
        b = _stats.compute_batter(player_name=player, venue=req.venue, opponent=None)
        e_b = _expected.estimate_batter(player_name=player, venue=req.venue, opponent=None)
        batters.append({"player": player, "stats": asdict(b), "expected": asdict(e_b)})

        w = _stats.compute_bowler(player_name=player, venue=req.venue, opponent=None)
        e_w = _expected.estimate_bowler(player_name=player, venue=req.venue, opponent=None)
        bowlers.append({"player": player, "stats": asdict(w), "expected": asdict(e_w)})

    return {"batters": batters, "bowlers": bowlers}
