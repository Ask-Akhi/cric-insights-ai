from fastapi import APIRouter, Query
import polars as pl
from ..providers.cricsheet_provider import CricsheetProvider

router = APIRouter()

_provider: CricsheetProvider | None = None

def _get_provider() -> CricsheetProvider:
    global _provider
    if _provider is None:
        _provider = CricsheetProvider()
        _provider.load()
    return _provider

# ── Common full-name → Cricsheet initials aliases ────────────────────────────
# Cricsheet uses "<Initials> <Surname>" format (e.g. "RG Sharma", "V Kohli")
PLAYER_ALIASES: dict[str, str] = {
    # India
    "rohit sharma":        "RG Sharma",
    "virat kohli":         "V Kohli",
    "ms dhoni":            "MS Dhoni",
    "jasprit bumrah":      "JJ Bumrah",
    "shubman gill":        "S Gill",
    "hardik pandya":       "HH Pandya",
    "kl rahul":            "KL Rahul",
    "ravindra jadeja":     "RA Jadeja",
    "ravichandran ashwin": "R Ashwin",
    "suryakumar yadav":    "SA Yadav",
    "yuvraj singh":        "Yuvraj Singh",
    "sachin tendulkar":    "SR Tendulkar",
    "sourav ganguly":      "SC Ganguly",
    "rahul dravid":        "R Dravid",
    "zaheer khan":         "Z Khan",
    "mohammad shami":      "Mohammed Shami",
    "rishabh pant":        "RR Pant",
    "shreyas iyer":        "SS Iyer",    "ishan kishan":        "Ishan Kishan",
    "axar patel":          "AR Patel",
    "deepak chahar":       "DL Chahar",
    "kuldeep yadav":       "Kuldeep Yadav",
    "yuzvendra chahal":    "YS Chahal",
    # Australia
    "steve smith":         "SPD Smith",
    "david warner":        "DA Warner",
    "pat cummins":         "PJ Cummins",
    "mitchell starc":      "MA Starc",
    "josh hazlewood":      "JR Hazlewood",
    "glen maxwell":        "GJ Maxwell",
    "glenn maxwell":       "GJ Maxwell",
    "travis head":         "TM Head",
    "marnus labuschagne":  "M Labuschagne",
    "adam zampa":          "A Zampa",
    # England
    "joe root":            "JE Root",
    "ben stokes":          "BA Stokes",
    "jos buttler":         "JC Buttler",
    "jofra archer":        "JC Archer",
    "mark wood":           "MA Wood",
    "johnny bairstow":     "JM Bairstow",
    "jonny bairstow":      "JM Bairstow",
    "harry brook":         "HC Brook",
    "james anderson":      "JM Anderson",
    "stuart broad":        "SCJ Broad",
    # New Zealand
    "kane williamson":     "KS Williamson",
    "ross taylor":         "LRPL Taylor",
    "trent boult":         "TA Boult",
    "tim southee":         "TG Southee",
    # Pakistan
    "babar azam":          "Babar Azam",
    "shaheen afridi":      "Shaheen Shah Afridi",
    "shaheen shah afridi": "Shaheen Shah Afridi",
    "mohammad rizwan":     "Mohammad Rizwan",
    "shadab khan":         "Shadab Khan",
    # South Africa
    "ab de villiers":      "AB de Villiers",
    "quinton de kock":     "Q de Kock",
    "kagiso rabada":       "K Rabada",
    "dale steyn":          "DW Steyn",
    "faf du plessis":      "F du Plessis",
    "aiden markram":       "AK Markram",
    # West Indies
    "chris gayle":         "CH Gayle",
    "kieron pollard":      "KA Pollard",
    "andre russell":       "AD Russell",
    "nicholas pooran":     "N Pooran",
    # Sri Lanka
    "kumar sangakkara":    "KC Sangakkara",
    "mahela jayawardene":  "DPMD Jayawardene",
    "lasith malinga":      "SL Malinga",
    "angelo mathews":      "AD Mathews",
    "wanindu hasaranga":   "AS Hasaranga",
    # Bangladesh
    "shakib al hasan":     "Shakib Al Hasan",
    "mushfiqur rahim":     "Mushfiqur Rahim",
    "tamim iqbal":         "Tamim Iqbal",
    "mustafizur rahman":   "Mustafizur Rahman",
    # Afghanistan
    "rashid khan":         "Rashid Khan",
    "mohammad nabi":       "Mohammad Nabi",
    "mujeeb ur rahman":    "Mujeeb Ur Rahman",
}

def _resolve_player_name(name: str) -> str:
    """Map full name → Cricsheet name if known, otherwise return as-is."""
    return PLAYER_ALIASES.get(name.strip().lower(), name.strip())


@router.get("/detect")
def detect_players_in_text(text: str = Query(..., description="Free-text sentence to scan for player names")):
    """
    Lightweight O(n) scan of PLAYER_ALIASES keys against a free-text sentence.
    Returns up to 3 detected Cricsheet player names — no Cricsheet I/O needed.
    Used by the frontend AskAI to auto-load stat charts as the user types.
    """
    lower = text.lower()
    found: list[str] = []
    for alias, cricsheet_name in PLAYER_ALIASES.items():
        if alias in lower and cricsheet_name not in found:
            found.append(cricsheet_name)
        if len(found) == 3:
            break
    return {"players": found, "count": len(found)}


@router.get("/")
def list_players(q: str | None = None, limit: int = 100):
    provider = _get_provider()
    # If the query matches a known alias, also search for the Cricsheet name
    resolved_q = _resolve_player_name(q) if q else None
    players = provider.list_players(q=resolved_q or q, limit=limit)
    # If resolved name differs and returned nothing, fall back to original query
    if not players and resolved_q and resolved_q != q:
        players = provider.list_players(q=q, limit=limit)
    return {"players": players, "query": q, "count": len(players)}

@router.get("/{player_name}/stats")
def get_player_stats(player_name: str, format: str | None = Query(None)):
    """Return structured chart-ready stats for a player, optionally filtered by format."""
    provider = _get_provider()
    # Resolve common full names → Cricsheet initials (e.g. "Rohit Sharma" → "RG Sharma")
    resolved_name = _resolve_player_name(player_name)
    df = provider.get_player_events(resolved_name)

    if df.is_empty():
        return {"player": resolved_name, "found": False, "batter": None, "bowler": None}

    # Optionally narrow to a specific format.
    # T20 → matches T20 and T20I; ODI → ODI and ODI Women; Test → Test only.
    if format:
        fmt_map: dict[str, list[str]] = {
            "T20":  ["T20", "T20I"],
            "ODI":  ["ODI", "ODI Women"],
            "Test": ["Test", "Test Women"],
        }
        allowed = fmt_map.get(format, [format])
        df = df.filter(pl.col("format").is_in(allowed))
        if df.is_empty():
            return {"player": resolved_name, "found": True, "batter": None, "bowler": None, "format": format}

    # Resolve the canonical name from actual data (handles fuzzy-match fallback).
    candidate_batters = df.filter(
        pl.col("batter").str.to_lowercase().str.contains(resolved_name.lower())
    ).get_column("batter").drop_nulls().to_list()
    canonical = max(set(candidate_batters), key=candidate_batters.count) if candidate_batters else resolved_name
    # If no batter rows, try the bowler column
    if not candidate_batters:
        candidate_bowlers = df.filter(
            pl.col("bowler").str.to_lowercase().str.contains(resolved_name.lower())
        ).get_column("bowler").drop_nulls().to_list()
        canonical = max(set(candidate_bowlers), key=candidate_bowlers.count) if candidate_bowlers else resolved_name

    # ── Batter stats ────────────────────────────────────────────
    bat = df.filter(pl.col("batter") == canonical)
    batter_data = None
    if bat.height > 0:
        # Runs per match (last 20)
        rpm = (
            bat.group_by(["match_id", "start_date"])
            .agg(
                pl.col("runs_off_bat").sum().alias("runs"),
                pl.len().alias("balls"),
            )
            .sort("start_date")
            .tail(20)
        )
        runs_per_match = [
            {"match": str(r["start_date"])[:10], "runs": int(r["runs"]), "balls": int(r["balls"])}
            for r in rpm.iter_rows(named=True)
        ]
        # Runs by format
        by_format = (
            bat.group_by("format")
            .agg(
                pl.col("runs_off_bat").sum().alias("runs"),
                pl.col("match_id").n_unique().alias("matches"),
            )
        )
        format_runs = [
            {"format": r["format"], "runs": int(r["runs"]), "matches": int(r["matches"])}
            for r in by_format.iter_rows(named=True)
        ]
        # Dismissal types
        dismissed = df.filter(pl.col("player_dismissed") == canonical)
        dismissal_counts = (
            dismissed.group_by("wicket_type").len()
            if dismissed.height > 0 else pl.DataFrame({"wicket_type": [], "len": []})
        )
        dismissals = [
            {"type": r["wicket_type"] or "unknown", "count": int(r["len"])}
            for r in dismissal_counts.iter_rows(named=True)
            if r["wicket_type"]
        ]
        # Summary
        total_runs = int(bat.select(pl.col("runs_off_bat").sum()).item() or 0)
        total_balls = bat.height
        total_matches = bat.select(pl.col("match_id").n_unique()).item()
        fours = bat.filter(pl.col("runs_off_bat") == 4).height
        sixes = bat.filter(pl.col("runs_off_bat") == 6).height

        batter_data = {
            "total_runs": total_runs,
            "total_balls": total_balls,
            "total_matches": int(total_matches),
            "strike_rate": round(total_runs / total_balls * 100, 1) if total_balls > 0 else 0,
            "average": round(total_runs / max(dismissed.height, 1), 1),
            "fours": fours,
            "sixes": sixes,
            "runs_per_match": runs_per_match,
            "format_runs": format_runs,
            "dismissals": dismissals,
        }

    # ── Bowler stats ────────────────────────────────────────────
    bowl = df.filter(pl.col("bowler") == canonical)
    bowler_data = None
    if bowl.height > 0:
        # Exclude run outs — those are not credited to the bowler
        wickets = bowl.filter(
            pl.col("player_dismissed").is_not_null()
            & pl.col("wicket_type").is_not_null()
            & ~pl.col("wicket_type").is_in(["run out", "retired hurt", "retired out", "obstructing the field"])
        )

        # Wickets per match (last 20)
        wpm = (
            bowl.group_by(["match_id", "start_date"])
            .agg(
                pl.col("player_dismissed").filter(
                    pl.col("player_dismissed").is_not_null()
                    & pl.col("wicket_type").is_not_null()
                    & ~pl.col("wicket_type").is_in(["run out", "retired hurt", "retired out", "obstructing the field"])
                ).len().alias("wickets"),
                pl.col("runs_off_bat").sum().alias("runs_conceded"),
                pl.len().alias("balls"),
            )
            .sort("start_date")
            .tail(20)
        )
        wickets_per_match = [
            {
                "match": str(r["start_date"])[:10],
                "wickets": int(r["wickets"]),
                "economy": round(r["runs_conceded"] / (r["balls"] / 6), 1) if r["balls"] > 0 else 0,
            }
            for r in wpm.iter_rows(named=True)
        ]

        # Wickets by format
        by_format_w = (
            bowl.group_by("format")
            .agg(
                pl.col("player_dismissed").filter(
                    pl.col("player_dismissed").is_not_null()
                    & pl.col("wicket_type").is_not_null()
                    & ~pl.col("wicket_type").is_in(["run out", "retired hurt", "retired out", "obstructing the field"])
                ).len().alias("wickets"),
                pl.col("match_id").n_unique().alias("matches"),
            )
        )
        format_wickets = [
            {"format": r["format"], "wickets": int(r["wickets"]), "matches": int(r["matches"])}
            for r in by_format_w.iter_rows(named=True)
        ]
        total_wickets = wickets.height
        total_runs_c = int(bowl.select(pl.col("runs_off_bat").sum()).item() or 0)
        total_balls_b = bowl.height
        overs = total_balls_b / 6

        bowler_data = {
            "total_wickets": total_wickets,
            "total_balls": total_balls_b,
            "total_matches": int(bowl.select(pl.col("match_id").n_unique()).item()),
            "economy": round(total_runs_c / overs, 2) if overs > 0 else 0,
            "average": round(total_runs_c / max(total_wickets, 1), 1),
            "strike_rate": round(total_balls_b / max(total_wickets, 1), 1),
            "wickets_per_match": wickets_per_match,
            "format_wickets": format_wickets,
        }

    return {"player": canonical, "found": True, "batter": batter_data, "bowler": bowler_data}
