"""
Full-stack integration test suite for Cric Insights AI backend.
Run: python -m pytest backend/tests/test_full_app.py -v --tb=short

Covers:
  - Health endpoint
  - /api/ask (405 regression, response shape)
  - /api/players (search, stats)
  - /api/matches (venues, teams, list, recent, h2h, venue stats)
  - /api/insights (POST)
  - SPA catch-all (non-API routes serve index.html)
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from backend.src.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── helpers ───────────────────────────────────────────────────────────────────

def ok(r) -> dict:
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"
    return r.json()


# ── 1. Health ─────────────────────────────────────────────────────────────────

def test_health_api():
    data = ok(client.get("/api/health"))
    assert data["status"] == "ok"

def test_health_shortpath():
    data = ok(client.get("/health"))
    assert data["status"] == "ok"

def test_health_has_uptime():
    data = ok(client.get("/api/health"))
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0

def test_health_content_type():
    r = client.get("/api/health")
    assert "application/json" in r.headers.get("content-type", "")


# ── 2. Ask AI — 405 regression ───────────────────────────────────────────────

ASK_PAYLOAD = {"prompt": "Who has the most T20 sixes?", "use_graph": False}

def test_post_ask_not_405():
    """POST /api/ask must reach the router, NOT return 405 from StaticFiles."""
    r = client.post("/api/ask", json=ASK_PAYLOAD)
    assert r.status_code != 405, "StaticFiles intercepted POST /api/ask!"

def test_post_ask_returns_200_or_5xx():
    r = client.post("/api/ask", json=ASK_PAYLOAD)
    assert r.status_code in (200, 500, 503), f"Unexpected {r.status_code}"

def test_post_ask_response_shape():
    r = client.post("/api/ask", json=ASK_PAYLOAD)
    if r.status_code == 200:
        data = r.json()
        assert "answer" in data
        assert "intent" in data
        assert isinstance(data["players"], list)

def test_post_insights_not_405():
    r = client.post("/api/insights", json={
        "format": "T20", "venue": "MCG",
        "team_a": "India", "team_b": "Australia",
        "squad_a": ["Virat Kohli"], "squad_b": ["Steve Smith"],
    })
    assert r.status_code != 405


# ── 3. Players ────────────────────────────────────────────────────────────────

def test_list_players_default():
    data = ok(client.get("/api/players/"))
    assert "players" in data
    assert isinstance(data["players"], list)

def test_search_players():
    data = ok(client.get("/api/players/?q=kohli&limit=5"))
    assert "players" in data

def test_player_stats_known():
    r = client.get("/api/players/Virat%20Kohli/stats")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json()
        assert "player" in data
        assert "found" in data

def test_player_stats_unknown():
    data = ok(client.get("/api/players/ZZZ_NonExistent_Player_XYZ/stats"))
    assert data["found"] is False

def test_player_stats_format_filter():
    r = client.get("/api/players/Rohit%20Sharma/stats?format=T20")
    assert r.status_code in (200, 404)


def test_player_detect_known():
    """GET /api/players/detect must return a list of Cricsheet names for a sentence with a known player."""
    data = ok(client.get("/api/players/detect?text=What+is+Virat+Kohli+T20+average"))
    assert "players" in data
    assert isinstance(data["players"], list)
    # Virat Kohli → V Kohli is in PLAYER_ALIASES — must be detected
    assert len(data["players"]) > 0, "Expected at least one player detected for 'Virat Kohli'"

def test_player_detect_unknown():
    """GET /api/players/detect with gibberish must return empty list."""
    data = ok(client.get("/api/players/detect?text=zzz+unknown+blah+blah"))
    assert data["players"] == []

def test_player_detect_multiple():
    """Detect should find up to 3 players in a sentence."""
    data = ok(client.get("/api/players/detect?text=Compare+Rohit+Sharma+and+Virat+Kohli+in+T20"))
    assert len(data["players"]) >= 1  # at least one detected


# ── 4. Matches ────────────────────────────────────────────────────────────────

def test_list_venues():
    data = ok(client.get("/api/matches/venues"))
    assert "venues" in data and isinstance(data["venues"], list)

def test_search_venues():
    data = ok(client.get("/api/matches/venues?q=mcg&limit=5"))
    assert isinstance(data["venues"], list)

def test_list_teams():
    data = ok(client.get("/api/matches/teams"))
    assert "teams" in data and len(data["teams"]) > 0

def test_list_matches_default():
    data = ok(client.get("/api/matches/"))
    assert "matches" in data and isinstance(data["matches"], list)

def test_list_matches_limit():
    data = ok(client.get("/api/matches/?limit=5"))
    assert len(data["matches"]) <= 5


# ── 5. Recent matches ─────────────────────────────────────────────────────────

def test_recent_default():
    data = ok(client.get("/api/matches/recent"))
    assert "matches" in data
    assert "source" in data
    assert isinstance(data["live"], bool)

def test_recent_t20():
    data = ok(client.get("/api/matches/recent?format=T20&limit=5"))
    assert len(data["matches"]) <= 5

def test_recent_odi():
    ok(client.get("/api/matches/recent?format=ODI&limit=5"))

def test_recent_test_format():
    ok(client.get("/api/matches/recent?format=Test&limit=5"))

def test_recent_match_shape():
    data = ok(client.get("/api/matches/recent?limit=3"))
    for m in data["matches"]:
        assert "team1" in m and "team2" in m and "winner" in m and "date" in m and "status" in m

def test_recent_source_valid():
    data = ok(client.get("/api/matches/recent"))
    valid_sources = {"cricsheet", "cricapi", "sportmonks", "rapidapi", "CricketData", "Cricbuzz"}
    assert data["source"] in valid_sources, f"Unknown source: {data['source']}"

def test_recent_cricsheet_has_latest_date():
    data = ok(client.get("/api/matches/recent"))
    if data["source"] == "cricsheet":
        assert "latest_date" in data


# ── 6. Venue stats ────────────────────────────────────────────────────────────

def test_venue_found():
    r = client.get("/api/matches/venue/Melbourne%20Cricket%20Ground")
    assert r.status_code == 200
    data = r.json()
    assert "venue" in data and "found" in data

def test_venue_not_found():
    data = ok(client.get("/api/matches/venue/ZZZ_NoSuchVenue_XYZ"))
    assert data["found"] is False

def test_venue_with_format():
    assert client.get("/api/matches/venue/Wankhede%20Stadium?format=T20").status_code == 200


# ── 7. Head-to-head ───────────────────────────────────────────────────────────

def test_h2h_basic():
    data = ok(client.get("/api/matches/h2h?team_a=India&team_b=Australia"))
    assert "team_a" in data and "found" in data

def test_h2h_no_match():
    data = ok(client.get("/api/matches/h2h?team_a=ZZZ&team_b=YYY"))
    assert data["found"] is False

def test_h2h_missing_param():
    assert client.get("/api/matches/h2h?team_a=India").status_code == 422


# ── 8. Insights POST ──────────────────────────────────────────────────────────

INSIGHTS_BASE = {
    "format": "T20", "venue": "Wankhede Stadium",
    "team_a": "India", "team_b": "Australia",
    "squad_a": ["Virat Kohli", "Rohit Sharma", "Jasprit Bumrah"],
    "squad_b": ["Steve Smith", "David Warner", "Pat Cummins"],
}

def test_insights_returns_200():
    assert client.post("/api/insights", json=INSIGHTS_BASE).status_code == 200

def test_insights_shape():
    data = ok(client.post("/api/insights", json=INSIGHTS_BASE))
    assert "batters" in data and "bowlers" in data
    assert isinstance(data["batters"], list) and isinstance(data["bowlers"], list)

def test_insights_empty_squads():
    r = client.post("/api/insights", json={**INSIGHTS_BASE, "squad_a": [], "squad_b": []})
    assert r.status_code == 200


# ── 9. SPA catch-all ──────────────────────────────────────────────────────────

def test_get_root_not_405():
    assert client.get("/").status_code in (200, 404)

def test_get_arbitrary_path():
    assert client.get("/some/random/page").status_code in (200, 404)

def test_api_prefix_not_swallowed():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")

def test_manifest_json():
    assert client.get("/manifest.json").status_code in (200, 404)

def test_sw_js():
    assert client.get("/sw.js").status_code in (200, 404)


# ── 10. Deployment config sanity (catches railway.toml / Dockerfile bugs) ─────

import tomllib, re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]  # backend/tests/../../  == repo root

def test_railway_toml_no_startcommand():
    """startCommand overrides Dockerfile CMD — npm doesn't exist in python:3.12-slim."""
    railway = ROOT_DIR / "railway.toml"
    raw = railway.read_text(encoding="utf-8")
    # Strip // comments (VS Code filepath annotations) before parsing TOML
    cleaned = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("//"))
    cfg = tomllib.loads(cleaned)
    deploy = cfg.get("deploy", {})
    assert "startCommand" not in deploy, (
        f"railway.toml has startCommand='{deploy.get('startCommand')}' "
        "— this overrides Dockerfile CMD. The final image is python:3.12-slim, "
        "npm/node don't exist there."
    )

def test_railway_toml_builder_is_dockerfile():
    railway = ROOT_DIR / "railway.toml"
    raw = railway.read_text(encoding="utf-8")
    cleaned = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("//"))
    cfg = tomllib.loads(cleaned)
    assert cfg.get("build", {}).get("builder", "").lower() == "dockerfile"

def test_railway_toml_healthcheck_path():
    railway = ROOT_DIR / "railway.toml"
    raw = railway.read_text(encoding="utf-8")
    cleaned = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("//"))
    cfg = tomllib.loads(cleaned)
    assert cfg.get("deploy", {}).get("healthcheckPath") == "/api/health"

def test_dockerfile_cmd_uses_uvicorn():
    """Dockerfile CMD must be uvicorn, not npm or node."""
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    cmd_lines = [l.strip() for l in dockerfile.splitlines() if l.strip().startswith("CMD")]
    assert cmd_lines, "No CMD found in Dockerfile"
    last_cmd = cmd_lines[-1]
    assert "uvicorn" in last_cmd, f"CMD doesn't use uvicorn: {last_cmd}"
    assert "npm" not in last_cmd, f"CMD uses npm (no npm in python:3.12-slim): {last_cmd}"

def test_dockerfile_cmd_binds_all_interfaces():
    """CMD must bind to 0.0.0.0, not 127.0.0.1 (localhost unreachable in Railway)."""
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    cmd_lines = [l.strip() for l in dockerfile.splitlines() if l.strip().startswith("CMD")]
    assert cmd_lines
    last_cmd = cmd_lines[-1]
    assert "0.0.0.0" in last_cmd, f"CMD binds to wrong interface: {last_cmd}"

def test_dockerfile_final_stage_is_python():
    """Final FROM must be python — npm doesn't exist in a python image."""
    dockerfile = (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")
    from_lines = [
        l.strip() for l in dockerfile.splitlines()
        if l.strip().upper().startswith("FROM") and " AS " not in l.upper()
    ]
    assert from_lines, "No final FROM stage found"
    assert "python" in from_lines[-1].lower(), (
        f"Final stage is not python: {from_lines[-1]}"
    )

def test_requirements_no_pytest_in_prod():
    """pytest must not be in prod requirements.txt — wastes image space."""
    reqs = (ROOT_DIR / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
    assert not re.search(r"^pytest(\s|=|$)", reqs, re.MULTILINE), (
        "pytest found in backend/requirements.txt — move it to requirements-dev.txt"
    )

def test_requirements_no_pyarrow_pinned_high():
    """pyarrow>=18 with polars causes OOM at import on 512 MB Railway containers."""
    reqs = (ROOT_DIR / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()
    match = re.search(r"pyarrow==(\d+)", reqs)
    if match:
        major = int(match.group(1))
        assert major < 18, f"pyarrow=={major} causes OOM with polars on Railway Hobby (512 MB)"
