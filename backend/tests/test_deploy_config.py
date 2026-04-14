import re, tomllib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

def _render():
    """Parse render.yaml — requires PyYAML (add to dev requirements if missing)."""
    try:
        import yaml
        return yaml.safe_load((ROOT_DIR / "render.yaml").read_text(encoding="utf-8"))
    except ImportError:
        # Fallback: return raw text so text-based assertions still work
        return (ROOT_DIR / "render.yaml").read_text(encoding="utf-8")

def _dockerfile():
    return (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")

def _reqs():
    return (ROOT_DIR / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()

# ── render.yaml tests ─────────────────────────────────────────────────────────

def test_render_yaml_exists():
    assert (ROOT_DIR / "render.yaml").exists(), "render.yaml missing — Render needs this to deploy"

def test_render_service_runtime_docker():
    cfg = _render()
    if isinstance(cfg, str):
        assert "runtime: docker" in cfg
    else:
        svc = cfg.get("services", [{}])[0]
        assert svc.get("runtime") == "docker", f"runtime must be 'docker', got '{svc.get('runtime')}'"

def test_render_healthcheck_path():
    cfg = _render()
    if isinstance(cfg, str):
        assert "healthCheckPath: /api/health" in cfg
    else:
        svc = cfg.get("services", [{}])[0]
        assert svc.get("healthCheckPath") == "/api/health", \
            f"healthCheckPath is '{svc.get('healthCheckPath')}' — must be '/api/health'"

def test_render_gemini_key_declared_not_hardcoded():
    cfg = _render()
    if isinstance(cfg, str):
        assert "GEMINI_API_KEY" in cfg, "GEMINI_API_KEY not declared in render.yaml"
        assert "sync: false" in cfg, "GEMINI_API_KEY must use 'sync: false' — do not commit actual key"
    else:
        svc = cfg.get("services", [{}])[0]
        env_vars = svc.get("envVars", [])
        keys = {e.get("key"): e for e in env_vars}
        assert "GEMINI_API_KEY" in keys, "GEMINI_API_KEY not declared in envVars"
        entry = keys["GEMINI_API_KEY"]
        assert "value" not in entry, \
            "GEMINI_API_KEY must NOT have a 'value:' — use 'sync: false' and set it in Render dashboard"

# ── Dockerfile tests ──────────────────────────────────────────────────────────

def test_dockerfile_cmd_uvicorn():
    cmds = [l.strip() for l in _dockerfile().splitlines() if l.strip().startswith("CMD")]
    assert cmds and "uvicorn" in cmds[-1] and "npm" not in cmds[-1]

def test_dockerfile_cmd_binds_0000():
    cmds = [l.strip() for l in _dockerfile().splitlines() if l.strip().startswith("CMD")]
    assert cmds and "0.0.0.0" in cmds[-1]

def test_dockerfile_cmd_port_env():
    cmds = [l.strip() for l in _dockerfile().splitlines() if l.strip().startswith("CMD")]
    assert cmds and "PORT" in cmds[-1]

def test_dockerfile_final_stage_python():
    froms = [l.strip() for l in _dockerfile().splitlines()
             if l.strip().upper().startswith("FROM") and " AS " not in l.upper()]
    assert froms and "python" in froms[-1].lower()

def test_dockerfile_cricsheet_baked_at_build():
    """Cricsheet data should be downloaded at Docker build time and raw files cleaned up."""
    df = _dockerfile()
    assert "--download" in df, "Cricsheet download should run at build time"
    assert "rm -rf" in df and "raw" in df, "Raw CSVs should be cleaned up after parse"

def test_dockerfile_polars_threads():
    assert "POLARS_MAX_THREADS" in _dockerfile()

# ── requirements.txt tests ────────────────────────────────────────────────────

def test_requirements_no_pytest():
    assert not re.search(r"^pytest(\s|=|$)", _reqs(), re.MULTILINE)

def test_requirements_no_dev_tools():
    reqs = _reqs()
    for pkg in ("black", "ruff", "mypy", "pylint"):
        assert not re.search(rf"^{pkg}", reqs, re.MULTILINE), f"{pkg} found in prod requirements"

def test_requirements_pyarrow_not_too_high():
    m = re.search(r"pyarrow==(\d+)", _reqs())
    if m:
        assert int(m.group(1)) < 18, f"pyarrow=={m.group(1)} may cause OOM on 512MB containers"
