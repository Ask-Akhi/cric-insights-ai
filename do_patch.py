import sys, os
from pathlib import Path

WORKSPACE = Path(__file__).parent
SITE_PACKAGES = WORKSPACE / ".venv312" / "Lib" / "site-packages"
sys.path.insert(0, str(SITE_PACKAGES))
sys.path.insert(0, str(WORKSPACE))

out = open(WORKSPACE / "patch_log.txt", "w", encoding="utf-8")

def log(msg):
    print(msg, flush=True)
    out.write(msg + "\n")
    out.flush()

try:
    log("Starting...")
    import polars as pl
    log(f"polars {pl.__version__}")

    from backend.src.scripts.parse_cricsheet import patch_format, build_format_map

    for gender in ["male", "female"]:
        log(f"\n=== {gender} ===")
        fmt_map = build_format_map(gender)
        log(f"Format map: {len(fmt_map)} entries")
        if fmt_map:
            sample = list(fmt_map.items())[:2]
            log(f"Sample: {sample}")
        patch_format(gender)

    log("\nAll done!")
except Exception as e:
    import traceback
    msg = traceback.format_exc()
    log(f"ERROR: {e}\n{msg}")
finally:
    out.close()
