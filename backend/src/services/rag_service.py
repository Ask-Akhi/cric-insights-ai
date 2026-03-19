"""
RAG (Retrieval-Augmented Generation) service.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List

from ..routers.players import PLAYER_ALIASES

_ALIAS_KEYS: List[str] = sorted(PLAYER_ALIASES.keys(), key=len, reverse=True)

# Match player names even when followed by possessive 's or 's (e.g. "Kohli's", "Kohlis")
_PLAYER_RE = re.compile(
    r'(?<!\w)(' + '|'.join(re.escape(k) for k in _ALIAS_KEYS) + r")(?:'?s)?(?!\w)",
    re.IGNORECASE,
)

_CRICKET_KEYWORDS = {
    "cricket", "ipl", "t20", "odi", "test match", "wicket", "batting",
    "bowling", "run", "over", "innings", "batter", "bowler", "fielding",
    "six", "four", "century", "fifty", "stumped", "lbw", "caught",
    "squad", "team", "match", "series", "world cup", "pitch", "crease",
    "powerplay", "death over", "spinner", "pacer", "all-rounder",
    "fantasy", "captain", "player", "stats", "average", "strike rate",
    "economy", "yorker", "googly", "wrist spin", "off spin", "leg spin",
    "drs", "umpire", "review", "boundary",
}


def detect_players_in_prompt(prompt: str) -> List[str]:
    found: List[str] = []
    seen: set = set()
    for m in _PLAYER_RE.finditer(prompt):
        alias = m.group(1).lower()  # group(1) = the name without possessive 's
        canonical = PLAYER_ALIASES.get(alias)
        if canonical and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)
    return found


def is_cricket_question(prompt: str) -> bool:
    lower = prompt.lower()
    if any(kw in lower for kw in _CRICKET_KEYWORDS):
        return True
    if _PLAYER_RE.search(prompt):
        return True
    return False


def _format_batter(player: str, data: Dict[str, Any], fmt: str) -> str:
    lines = [f"CRICSHEET BATTER STATS - {player} ({fmt}):"]
    lines.append(
        f"  Matches={data['total_matches']}  Runs={data['total_runs']}  "
        f"Avg={data['average']}  SR={data['strike_rate']}  "
        f"4s={data['fours']}  6s={data['sixes']}"
    )
    if data.get("format_runs"):
        s = ", ".join(f"{r['format']}:{r['runs']}runs/{r['matches']}M" for r in data["format_runs"])
        lines.append(f"  By format: {s}")
    if data.get("runs_per_match"):
        recent = data["runs_per_match"][-5:]
        s = ", ".join(f"{r['runs']}({r['balls']}b)" for r in recent)
        lines.append(f"  Last 5 innings: {s}")
    if data.get("dismissals"):
        s = ", ".join(f"{d['type']}:{d['count']}" for d in data["dismissals"])
        lines.append(f"  Dismissal types: {s}")
    return "\n".join(lines)


def _format_bowler(player: str, data: Dict[str, Any], fmt: str) -> str:
    lines = [f"CRICSHEET BOWLER STATS - {player} ({fmt}):"]
    lines.append(
        f"  Matches={data['total_matches']}  Wickets={data['total_wickets']}  "
        f"Avg={data['average']}  Econ={data['economy']}  SR={data['strike_rate']}"
    )
    if data.get("format_wickets"):
        s = ", ".join(f"{r['format']}:{r['wickets']}W/{r['matches']}M" for r in data["format_wickets"])
        lines.append(f"  By format: {s}")
    if data.get("wickets_per_match"):
        recent = data["wickets_per_match"][-5:]
        s = ", ".join(f"{r['wickets']}W(econ:{r['economy']})" for r in recent)
        lines.append(f"  Last 5 matches: {s}")
    return "\n".join(lines)


def fetch_player_context(player_names: List[str], fmt: str = "T20") -> str:
    if not player_names:
        return ""
    try:
        from ..routers.players import get_player_stats
    except Exception:
        return ""
    blocks: List[str] = []
    for player in player_names[:3]:
        try:
            result = get_player_stats(player_name=player, format=fmt)
            if not result.get("found"):
                continue
            batter = result.get("batter")
            bowler = result.get("bowler")
            if batter:
                blocks.append(_format_batter(player, batter, fmt))
            if bowler:
                blocks.append(_format_bowler(player, bowler, fmt))
        except Exception:
            continue
    return "\n\n".join(blocks)


def build_rag_context(prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(context)
    fmt = str(context.get("format", "T20"))
    enriched["_is_cricket"] = is_cricket_question(prompt)
    players = detect_players_in_prompt(prompt)
    if players:
        stats_text = fetch_player_context(players, fmt=fmt)
        if stats_text:
            enriched["cricsheet_data"] = stats_text
            enriched["detected_players"] = ", ".join(players)
    return enriched
