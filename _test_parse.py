"""Verify all new/modified Python files parse without syntax errors."""
import ast
import sys

files = [
    "backend/src/core/__init__.py",
    "backend/src/core/config.py",
    "backend/src/core/result.py",
    "backend/src/core/token_utils.py",
    "backend/src/mcp/__init__.py",
    "backend/src/mcp/client.py",
    "backend/src/mcp/context_assembler.py",
    "backend/src/mcp/orchestrator.py",
    "backend/src/mcp/servers/__init__.py",
    "backend/src/mcp/servers/cricsheet_server.py",
    "backend/src/mcp/servers/live_server.py",
    "backend/src/mcp/servers/search_server.py",
    "backend/src/mcp/servers/__main__.py",
    "backend/src/routers/ask.py",
    "backend/src/routers/admin.py",
]

errors = 0
for f in files:
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:
            source = fh.read()
        ast.parse(source, filename=f)
        print(f"  OK  {f}")
    except SyntaxError as e:
        print(f"  FAIL {f}: {e}")
        errors += 1
    except FileNotFoundError:
        print(f"  MISSING {f}")
        errors += 1

print()
if errors:
    print(f"FAILED: {errors} file(s) have issues")
    sys.exit(1)
else:
    print(f"ALL {len(files)} files parse OK")
