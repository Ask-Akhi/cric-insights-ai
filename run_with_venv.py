"""
run_with_venv.py  –  helper to execute a backend script using the correct
Python 3.12 interpreter with the venv312 site-packages on sys.path.

Usage (from workspace root):
    & "C:\Program Files\Python312\python.exe" run_with_venv.py parse_cricsheet --gender both --patch
"""
import sys, os
from pathlib import Path

WORKSPACE = Path(__file__).parent
SITE_PACKAGES = WORKSPACE / ".venv312" / "Lib" / "site-packages"

# Prepend venv312 site-packages so all installed packages are visible
sys.path.insert(0, str(SITE_PACKAGES))
sys.path.insert(0, str(WORKSPACE))

# Hand off to the real script
script = sys.argv[1]
sys.argv = sys.argv[1:]   # shift so the script sees its own args

if script == "parse_cricsheet":
    from backend.src.scripts.parse_cricsheet import main
    main()
elif script == "download_cricsheet":
    from backend.src.scripts.download_cricsheet import main
    main()
else:
    print(f"Unknown script: {script}", file=sys.stderr)
    sys.exit(1)
