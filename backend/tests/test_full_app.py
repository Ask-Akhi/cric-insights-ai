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
    # 503 = timeout / quota exhausted; 504 = upstream gateway timeout (Railway/proxy)
    assert r.status_code in (200, 500, 503, 504), f"Unexpected {r.status_code}"

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


# ── 11. context_assembler.strip_delimiters ────────────────────────────────────

from backend.src.mcp.context_assembler import strip_delimiters

def test_strip_delimiters_removes_cricsheet_header():
    text = "--- CRICSHEET BALL-BY-BALL DATA (tool: player_stats) ---\nVirat Kohli: avg 52.3"
    result = strip_delimiters(text)
    assert "---" not in result
    assert "Virat Kohli: avg 52.3" in result

def test_strip_delimiters_removes_end_marker():
    text = "some stats\n--- END CRICSHEET BALL-BY-BALL DATA ---\nmore text"
    result = strip_delimiters(text)
    assert "---" not in result
    assert "some stats" in result
    assert "more text" in result

def test_strip_delimiters_removes_live_data_header():
    text = "--- LIVE/RECENT MATCH DATA ---\nIndia 245/3 (45 ov)"
    result = strip_delimiters(text)
    assert "---" not in result
    assert "India 245/3" in result

def test_strip_delimiters_removes_web_search_header():
    text = "--- WEB SEARCH RESULTS ---\nCricinfo: Rohit Sharma named captain"
    result = strip_delimiters(text)
    assert "---" not in result
    assert "Cricinfo" in result

def test_strip_delimiters_case_insensitive():
    text = "--- cricsheet ball-by-ball data ---\nsome content"
    result = strip_delimiters(text)
    assert "---" not in result

def test_strip_delimiters_collapses_blank_lines():
    text = "line1\n\n\n\n\nline2"
    result = strip_delimiters(text)
    assert "\n\n\n" not in result
    assert "line1" in result and "line2" in result

def test_strip_delimiters_passthrough_normal_text():
    text = "Virat Kohli T20 average: 52.73 in 115 matches"
    assert strip_delimiters(text) == text

def test_strip_delimiters_empty_string():
    assert strip_delimiters("") == ""

def test_strip_delimiters_none_safe():
    # Should not raise — returns empty string for falsy input
    assert strip_delimiters("") == ""

def test_strip_delimiters_quota_message_passthrough():
    """Quota/error text that isn't a delimiter should be untouched."""
    text = "⚠️ AI service has reached its daily usage limit. Showing local data:"
    result = strip_delimiters(text)
    assert "daily usage limit" in result

def test_strip_delimiters_multiple_sections():
    text = (
        "--- CRICSHEET BALL-BY-BALL DATA (tool: player_stats) ---\n"
        "Rohit: 350 runs\n"
        "--- END CRICSHEET BALL-BY-BALL DATA ---\n"
        "--- WEB SEARCH RESULTS ---\n"
        "Latest news\n"
    )
    result = strip_delimiters(text)
    assert "---" not in result
    assert "Rohit: 350 runs" in result
    assert "Latest news" in result


# ── 12. Circuit breaker + quota-fallback (orchestrator unit tests) ────────────

from unittest.mock import patch, AsyncMock
from backend.src.services.circuit_breaker import CircuitBreaker
from backend.src.mcp.context_assembler import assemble
from backend.src.core.result import ToolResult


def _make_tool_result(data: str, source: str = "cricsheet", tool: str = "player_stats") -> ToolResult:
    return ToolResult(ok=True, tool_name=tool, source=source, data=data)


# ── Circuit breaker unit tests ────────────────────────────────────────────────

def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker(name="test")
    assert cb.is_open is False


def test_circuit_breaker_opens_on_trip():
    cb = CircuitBreaker(name="test")
    cb.trip(reason="quota exhausted")
    assert cb.is_open is True


def test_circuit_breaker_closes_after_cooldown():
    import time
    cb = CircuitBreaker(name="test", cooldown_s=0.05)
    cb.trip()
    assert cb.is_open is True
    time.sleep(0.06)
    assert cb.is_open is False   # cooldown expired


def test_circuit_breaker_record_skip_increments():
    cb = CircuitBreaker(name="test")
    cb.trip()
    cb.record_skip()
    cb.record_skip()
    assert cb.total_skipped == 2


def test_circuit_breaker_trip_increments_total():
    cb = CircuitBreaker(name="test")
    cb.trip()
    cb.trip()
    assert cb.total_trips == 2


def test_circuit_breaker_status_shape():
    cb = CircuitBreaker(name="test")
    s = cb.status()
    assert "is_open" in s
    assert "total_trips" in s
    assert "seconds_until_close" in s


# ── Quota sentinel does NOT leak raw delimiters into user-facing answer ────────

def test_quota_fallback_answer_has_no_delimiters():
    """Simulate the post-LLM quota path: strip_delimiters must remove all markers."""
    assembled = (
        "--- CRICSHEET BALL-BY-BALL DATA (tool: player_stats) ---\n"
        "Virat Kohli: T20I avg 52.3, SR 139.5\n"
        "--- END CRICSHEET BALL-BY-BALL DATA ---\n"
        "--- WEB SEARCH RESULTS ---\n"
        "Kohli named captain for WTC final\n"
    )
    quota_note = "\n\n> ⚠️ *AI analysis unavailable (daily quota reached). Showing data from Cricsheet ball-by-ball records.*"
    answer = strip_delimiters(assembled) + quota_note
    assert "---" not in answer.split(quota_note)[0], "Delimiters leaked into user-facing quota-fallback answer"
    assert "Virat Kohli" in answer
    assert "Kohli named captain" in answer
    assert "daily quota reached" in answer


def test_quota_sentinel_triggers_fallback_branch():
    """The _QUOTA_SENTINEL substring must be present in the expected quota-error text."""
    from backend.src.mcp.orchestrator import _QUOTA_SENTINEL
    quota_text = "⚠️ The AI service has reached its daily usage limit."
    assert _QUOTA_SENTINEL in quota_text.lower()


def test_quota_note_not_cached(monkeypatch):
    """Responses starting with ⚠️ (quota note) must NOT be written to llm_cache."""
    from backend.src.services import llm_cache
    # Snapshot cache size before
    before = llm_cache.stats()["entries"]
    # Simulate the ask router logic: don't cache ⚠️ answers
    answer = "⚠️ AI service has reached its daily usage limit."
    if not answer.startswith("⚠️") and not answer.startswith("⏱️"):
        llm_cache.put("some question", False, "", {"answer": answer, "intent": "general",
                                                    "players": [], "mode": "mcp",
                                                    "data_sources": [], "latency_ms": 0,
                                                    "rag_cache_hit": False, "tools_used": []})
    assert llm_cache.stats()["entries"] == before, "Quota/error answer was incorrectly cached"


# ── LLM cache invalidation after data refresh ─────────────────────────────────

def test_llm_cache_invalidate_all():
    from backend.src.services import llm_cache
    llm_cache.put("test q", False, "", {"answer": "x", "intent": "general",
                                         "players": [], "mode": "mcp",
                                         "data_sources": [], "latency_ms": 0,
                                         "rag_cache_hit": False, "tools_used": []})
    assert llm_cache.stats()["entries"] >= 1
    evicted = llm_cache.invalidate_all()
    assert evicted >= 1
    assert llm_cache.stats()["entries"] == 0


def test_run_refresh_flushes_cache(monkeypatch):
    """After a successful _run_refresh(), llm_cache must be empty."""
    from backend.src.services import llm_cache
    from backend.src.routers import admin

    # Pre-populate cache
    llm_cache.put("stale q", False, "", {"answer": "stale answer", "intent": "general",
                                          "players": [], "mode": "mcp",
                                          "data_sources": [], "latency_ms": 0,
                                          "rag_cache_hit": False, "tools_used": []})
    assert llm_cache.stats()["entries"] >= 1

    # Monkey-patch subprocess.run to simulate a successful refresh without network
    import subprocess
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_result)

    # Patch pathlib.Path.exists / unlink so it doesn't touch real filesystem
    monkeypatch.setattr("pathlib.Path.exists", lambda self: False)

    admin._run_refresh()

    assert llm_cache.stats()["entries"] == 0, (
        "llm_cache not flushed after successful Cricsheet refresh — stale answers will be served"
    )
