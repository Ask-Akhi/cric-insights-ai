import re, tomllib
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

def _railway():
    raw = (ROOT_DIR / "railway.toml").read_text(encoding="utf-8")
    cleaned = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("//"))
    return tomllib.loads(cleaned)

def _dockerfile():
    return (ROOT_DIR / "Dockerfile").read_text(encoding="utf-8")

def _reqs():
    return (ROOT_DIR / "backend" / "requirements.txt").read_text(encoding="utf-8").lower()

def test_railway_no_startcommand():
    deploy = _railway().get("deploy", {})
    assert "startCommand" not in deploy, f"startCommand overrides Dockerfile CMD: {deploy.get('startCommand')}"

def test_railway_builder_dockerfile():
    assert _railway().get("build", {}).get("builder", "").lower() == "dockerfile"

def test_railway_healthcheck_path():
    assert _railway().get("deploy", {}).get("healthcheckPath") == "/api/health"

def test_railway_healthcheck_timeout():
    assert _railway().get("deploy", {}).get("healthcheckTimeout", 0) >= 120

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

def test_dockerfile_no_oom_download():
    df = _dockerfile()
    assert "--download" not in df or "BUILD_CRICSHEET" in df

def test_dockerfile_polars_threads():
    assert "POLARS_MAX_THREADS" in _dockerfile()

def test_requirements_no_pytest():
    assert not re.search(r"^pytest(\s|=|$)", _reqs(), re.MULTILINE)

def test_requirements_no_dev_tools():
    reqs = _reqs()
    for pkg in ("black", "ruff", "mypy", "pylint"):
        assert not re.search(rf"^{pkg}", reqs, re.MULTILINE), f"{pkg} found in prod requirements"

def test_requirements_pyarrow_not_too_high():
    m = re.search(r"pyarrow==(\d+)", _reqs())
    if m:
        assert int(m.group(1)) < 18, f"pyarrow=={m.group(1)} causes OOM on Railway 512MB"
