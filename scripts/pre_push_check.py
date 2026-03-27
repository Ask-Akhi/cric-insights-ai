"""
pre_push_check.py -- Deployment validation gate run before every git push.

Catches config bugs that pytest (unit/integration tests) will never see:
  1. railway.toml  -- forbidden keys that override Dockerfile CMD
  2. Dockerfile    -- CMD must be uvicorn, not npm/node
  3. requirements  -- no dev-only packages in prod
  4. Frontend build -- vite build must succeed (catches TS/JSX errors)
  5. Backend import -- main.py must import without crashing
  6. pytest gate   -- deployment config tests (file-read only, ~0.1s)

Exit 0 = safe to push.  Exit 1 = blocked.
"""
from __future__ import annotations
import sys, os, io, re, subprocess, tomllib
from pathlib import Path

# Force UTF-8 stdout so ANSI works on Windows cp1252 consoles
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PASS = "\033[32m[OK]  \033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
errors: list[str] = []
warnings: list[str] = []


def check(label: str, ok: bool, detail: str = "", fatal: bool = True) -> bool:
    if ok:
        print(f"  {PASS}  {label}")
    else:
        print(f"  {FAIL}  {label}" + (f"\n         -> {detail}" if detail else ""))
        if fatal:
            errors.append(label)
        else:
            warnings.append(label)
    return ok


# -- 1. railway.toml ----------------------------------------------------------
print("\n[1/6] railway.toml")
railway_path = ROOT / "railway.toml"
try:
    raw = railway_path.read_text(encoding="utf-8")
    cleaned = "\n".join(
        line for line in raw.splitlines()
        if not line.strip().startswith("//")
    )
    cfg = tomllib.loads(cleaned)
    deploy = cfg.get("deploy", {})

    _sc = deploy.get("startCommand", "")
    check(
        "No startCommand override",
        "startCommand" not in deploy,
        detail=(
            f'startCommand = "{_sc}" overrides Dockerfile CMD. '
            "Final image is python:3.12-slim -- npm/node do not exist there."
        )
    )

    build = cfg.get("build", {})
    check(
        "builder = dockerfile",
        build.get("builder", "").lower() == "dockerfile",
        detail=f"builder is '{build.get('builder')}' -- must be 'dockerfile'"
    )

    hc = deploy.get("healthcheckPath", "")
    check(
        "healthcheckPath = /api/health",
        hc == "/api/health",
        detail=f"healthcheckPath is '{hc}'"
    )

    hct = deploy.get("healthcheckTimeout", 0)
    check(
        f"healthcheckTimeout >= 300 (got {hct})",
        hct >= 300,
        detail="Cricsheet background download takes ~2-4 min -- timeout must be > 300s",
        fatal=False
    )

except Exception as e:
    check("railway.toml parses cleanly", False, detail=str(e))


# -- 2. Dockerfile ------------------------------------------------------------
print("\n[2/6] Dockerfile")
dockerfile_path = ROOT / "Dockerfile"
try:
    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    df_lines = dockerfile.splitlines()

    cmd_lines = [l.strip() for l in df_lines if l.strip().startswith("CMD")]
    check("CMD found in Dockerfile", bool(cmd_lines), detail="No CMD instruction found")

    if cmd_lines:
        last_cmd = cmd_lines[-1]
        check(
            "CMD uses uvicorn (not npm/node)",
            "uvicorn" in last_cmd and "npm" not in last_cmd and "node " not in last_cmd,
            detail=f"CMD is: {last_cmd}"
        )
        check(
            "CMD binds to 0.0.0.0 (not 127.0.0.1)",
            "0.0.0.0" in last_cmd,
            detail="127.0.0.1 is unreachable inside Railway containers"
        )
        check(
            "CMD references PORT env var",
            "PORT" in last_cmd,
            detail="Railway injects $PORT -- hardcoded port may conflict",
            fatal=False
        )

    from_lines = [
        l.strip() for l in df_lines
        if l.strip().upper().startswith("FROM") and " AS " not in l.upper()
    ]
    if from_lines:
        check(
            "Final stage is python (not node)",
            "python" in from_lines[-1].lower(),
            detail=f"Final FROM is: {from_lines[-1]} -- npm won't exist in a python image"
        )

    check(
        "No unconditional Cricsheet download at build",
        "--download" not in dockerfile or "BUILD_CRICSHEET" in dockerfile,
        detail="Unconditional --download causes 800 MB OOM on Railway Hobby (512 MB RAM)"
    )

    check(
        "POLARS_MAX_THREADS set",
        "POLARS_MAX_THREADS" in dockerfile,
        detail="Without this Polars spawns many threads -> OOM on 512 MB containers",
        fatal=False
    )

    # scripts/ must be COPY'd before npm ci so postinstall finds patch-spm.cjs
    scripts_copy_idx = next(
        (i for i, l in enumerate(df_lines)
         if re.search(r'COPY\s+frontend/scripts', l) or re.search(r'COPY\s+frontend/\s+\./', l)),
        None
    )
    # Match only actual RUN instructions, not comments that mention "npm ci"
    npm_ci_idx = next(
        (i for i, l in enumerate(df_lines)
         if re.search(r'^\s*RUN\b.*\bnpm\s+ci\b', l)),
        None
    )
    if scripts_copy_idx is not None and npm_ci_idx is not None:
        scripts_before_npmci = scripts_copy_idx < npm_ci_idx
    elif scripts_copy_idx is None:
        scripts_before_npmci = False
    else:
        scripts_before_npmci = True
    check(
        "frontend/scripts/ copied before npm ci",
        scripts_before_npmci,
        detail=(
            "scripts/patch-spm.cjs is the postinstall hook in package.json. "
            "It must exist in the Docker build context before 'RUN npm ci' runs. "
            "Add:  COPY frontend/scripts/ ./scripts/  before the RUN npm ci line."
        )
    )

    patch_spm_path = ROOT / "frontend" / "scripts" / "patch-spm.cjs"
    if patch_spm_path.exists():
        # Check for UTF-8 BOM (0xEF 0xBB 0xBF) -- Node.js throws SyntaxError on BOM
        raw_bytes = patch_spm_path.read_bytes()
        has_bom = raw_bytes[:3] == b'\xef\xbb\xbf'
        check(
            "patch-spm.cjs has no UTF-8 BOM",
            not has_bom,
            detail=(
                "patch-spm.cjs starts with a UTF-8 BOM (written by PowerShell WriteAllText with default UTF8 encoding). "
                "Node.js throws 'SyntaxError: Invalid or unexpected token' on BOM. "
                "Fix: use New-Object System.Text.UTF8Encoding $false when writing the file."
            )
        )

        patch_spm_src = patch_spm_path.read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM if present
        is_guarded = (
            "process.platform" in patch_spm_src
            and "darwin" in patch_spm_src
            and "process.exit" in patch_spm_src
        )
        check(
            "patch-spm.cjs exits early on non-macOS (Docker-safe)",
            is_guarded,
            detail=(
                "scripts/patch-spm.cjs runs as postinstall in Docker (Linux). "
                "It must check process.platform !== 'darwin' and call process.exit(0) early, "
                "otherwise it crashes 'npm ci' during the Docker build."
            )
        )

except Exception as e:
    check("Dockerfile reads cleanly", False, detail=str(e))


# -- 3. requirements.txt -- no dev packages in prod ---------------------------
print("\n[3/6] backend/requirements.txt (prod safety)")
req_path = ROOT / "backend" / "requirements.txt"
DEV_ONLY = ["pytest", "pytest-", "black", "ruff", "mypy", "pylint", "ipython", "jupyter"]
try:
    reqs = req_path.read_text(encoding="utf-8").lower()
    for pkg in DEV_ONLY:
        found = re.search(rf"^{re.escape(pkg)}", reqs, re.MULTILINE) is not None
        check(
            f"No '{pkg}' in prod requirements",
            not found,
            detail=f"'{pkg}' is dev-only -- bloats prod image",
            fatal=False
        )
except Exception as e:
    check("requirements.txt reads", False, detail=str(e))


# -- 4. Frontend build --------------------------------------------------------
print("\n[4/6] Frontend -- vite build")
frontend_dir = ROOT / "frontend"
npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
try:
    result = subprocess.run(
        [npm_cmd, "run", "build"],
        cwd=str(frontend_dir),
        capture_output=True, timeout=120,
        encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        check("vite build succeeds", False, detail="\n         ".join(lines[-10:]))
    else:
        check("vite build succeeds", True)
except subprocess.TimeoutExpired:
    check("vite build (timeout)", False, detail="Build took >120s")
except FileNotFoundError:
    check("npm available", False, detail="npm not found -- skipping frontend check", fatal=False)


# -- 5. Backend import smoke test ---------------------------------------------
print("\n[5/6] Backend -- import smoke test")
venv_python = ROOT / ".venv312" / "Scripts" / "python.exe"
if not venv_python.exists():
    venv_python = ROOT / ".venv312" / "bin" / "python"
python_exe = str(venv_python) if venv_python.exists() else sys.executable

try:
    result = subprocess.run(
        [python_exe, "-c",
         "import sys; sys.path.insert(0, '.'); from backend.src.main import app; print('app OK')"],
        cwd=str(ROOT),
        capture_output=True, timeout=30,
        encoding="utf-8", errors="replace"
    )
    ok_import = result.returncode == 0 and "app OK" in result.stdout
    err_lines = (result.stderr or "").strip().splitlines()
    check(
        "backend.src.main imports without crash",
        ok_import,
        detail="\n         ".join(err_lines[-5:]) if not ok_import else ""
    )
except subprocess.TimeoutExpired:
    check("Backend import (timeout)", False, detail="Import hung for >30s")


# -- 6. pytest gate -----------------------------------------------------------
print("\n[6/6] pytest -- deployment config tests (file-read only, ~0.1s)")
try:
    result = subprocess.run(
        [python_exe, "-m", "pytest",
         "backend/tests/test_deploy_config.py",
         "--tb=short", "-q", "--no-header"],
        cwd=str(ROOT),
        capture_output=True, timeout=15,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONPATH": str(ROOT)}
    )
    ok_tests = result.returncode == 0
    lines = (result.stdout + result.stderr).strip().splitlines()
    if not ok_tests:
        check("pytest gate", False, detail="\n         ".join(lines[-15:]))
    else:
        summary = next((l for l in reversed(lines) if "passed" in l or "no tests" in l), "ok")
        check(f"pytest gate ({summary})", True)
except subprocess.TimeoutExpired:
    check("pytest gate (timeout)", False, detail="Tests hung >15s")


# -- Summary ------------------------------------------------------------------
print()
if errors:
    print(f"\033[31m[BLOCKED] {len(errors)} fatal error(s) -- push aborted:\033[0m")
    for e in errors:
        print(f"    * {e}")
    if warnings:
        print(f"\033[33m[WARN] {len(warnings)} warning(s) (non-fatal):\033[0m")
        for w in warnings:
            print(f"    * {w}")
    sys.exit(1)
else:
    if warnings:
        print(f"\033[33m[WARN] {len(warnings)} warning(s) -- safe to push but review:\033[0m")
        for w in warnings:
            print(f"    * {w}")
    print("\033[32m[PASS] All checks passed -- safe to push!\033[0m\n")
    sys.exit(0)