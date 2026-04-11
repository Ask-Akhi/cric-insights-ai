"""Quick AST parse + collapsed-line scan for key backend files."""
import re, ast, sys

files_to_check = [
    "backend/src/mcp/servers/cricsheet_server.py",
    "backend/src/mcp/orchestrator.py",
    "backend/src/core/config.py",
    "backend/src/main.py",
    "backend/src/providers/cricsheet_provider.py",
    "backend/src/services/rag_service.py",
]

all_ok = True
for fpath in files_to_check:
    try:
        with open(fpath, encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        print(f"SKIP {fpath} (not found)")
        continue

    # AST parse
    try:
        ast.parse(src)
        print(f"OK   {fpath}")
    except SyntaxError as e:
        print(f"FAIL {fpath} — SyntaxError at line {e.lineno}: {e.msg}")
        lines = src.splitlines()
        for i in range(max(0, e.lineno - 3), min(len(lines), e.lineno + 2)):
            print(f"     {i+1}: {lines[i]}")
        all_ok = False

    # Collapsed-line scan
    collapse_re = re.compile(
        r'[)\"\'\}\]]\s{4,}'
        r'(def |class |try:|except |else:|elif |return |if |for |with |import |from )'
    )
    for n, line in enumerate(src.splitlines(), 1):
        if collapse_re.search(line):
            print(f"  ⚠️  Suspicious collapse at {fpath}:{n}: {line.rstrip()[:120]}")
            all_ok = False

if all_ok:
    print("\nAll files OK — no syntax errors, no collapsed lines.")
else:
    print("\n❌ Issues found above.")
    sys.exit(1)
