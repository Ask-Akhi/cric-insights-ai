"""Quick smoke-test of the backend API endpoints."""
import urllib.request
import json
import sys

BASE = "http://127.0.0.1:8002"

def get(path):
    try:
        r = urllib.request.urlopen(BASE + path, timeout=10)
        return json.loads(r.read())
    except Exception as e:
        return {"ERROR": str(e)}

print("=== /api/players/?q=kohli ===")
result = get("/api/players/?q=kohli&limit=5")
print(json.dumps(result, indent=2))

print("\n=== /api/players/V Kohli/stats (top-level keys) ===")
import urllib.parse
result2 = get(f"/api/players/{urllib.parse.quote('V Kohli')}/stats")
# Only print top-level to keep it short
print(json.dumps({k: type(v).__name__ if isinstance(v, dict) else v 
                  for k, v in result2.items()}, indent=2))

print("\n=== /api/players/kohli/stats (fuzzy) ===")
result3 = get(f"/api/players/{urllib.parse.quote('kohli')}/stats")
print(json.dumps({k: type(v).__name__ if isinstance(v, dict) else v 
                  for k, v in result3.items()}, indent=2))

print("\nDone.")
