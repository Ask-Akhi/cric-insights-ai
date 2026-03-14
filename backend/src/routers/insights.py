from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from dataclasses import asdict

from ..providers.cricsheet_provider import CricsheetProvider
from ..services.stats_service import StatsService
from ..services.expected_service import ExpectedService

router = APIRouter()

# Lazy-initialised — do NOT load at import time (crashes Railway before $PORT is bound)
_provider: CricsheetProvider | None = None
_stats: StatsService | None = None
_expected: ExpectedService | None = None

def _get_services():
    global _provider, _stats, _expected
    if _provider is None:
        try:
            _provider = CricsheetProvider()
            _provider.load()
            _stats = StatsService(_provider)
            _expected = ExpectedService(_provider)
        except Exception as e:
            # Log but don't crash — endpoints will return empty results
            import logging
            logging.getLogger(__name__).warning(f"CricsheetProvider failed to load: {e}")
            _provider = CricsheetProvider()   # unloaded stub
            _stats = StatsService(_provider)
            _expected = ExpectedService(_provider)
    return _stats, _expected

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
    stats, expected = _get_services()
    batters: List[Dict[str, Any]] = []
    bowlers: List[Dict[str, Any]] = []

    # Compute batter and bowler insights for all provided players
    for player in list(dict.fromkeys(req.squad_a + req.squad_b)):
        b = stats.compute_batter(player_name=player, venue=req.venue, opponent=None)
        e_b = expected.estimate_batter(player_name=player, venue=req.venue, opponent=None)
        batters.append({"player": player, "stats": asdict(b), "expected": asdict(e_b)})

        w = stats.compute_bowler(player_name=player, venue=req.venue, opponent=None)
        e_w = expected.estimate_bowler(player_name=player, venue=req.venue, opponent=None)
        bowlers.append({"player": player, "stats": asdict(w), "expected": asdict(e_w)})

    return {"batters": batters, "bowlers": bowlers}
