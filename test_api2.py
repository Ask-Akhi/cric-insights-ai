import urllib.request, json, sys, urllib.parse

BASE = "http://127.0.0.1:8002"

def get(path):
    try:
        url = BASE + path
        r = urllib.request.urlopen(url, timeout=15)
        return json.loads(r.read())
    except Exception as e:
        return {"ERROR": str(e)}

results = {}

# 1. Player search
results["search_kohli"] = get("/api/players/?q=kohli&limit=5")

# 2. Exact name stats
results["stats_v_kohli"] = get("/api/players/" + urllib.parse.quote("V Kohli") + "/stats")

# 3. Fuzzy stats
results["stats_fuzzy_kohli"] = get("/api/players/" + urllib.parse.quote("kohli") + "/stats")

# 4. Bumrah search
results["search_bumrah"] = get("/api/players/?q=bumrah&limit=5")

with open(r"C:\Users\1223505\Personal Apps\test_results.json", "w") as f:
    # Summarise stats to keep it small
    for k in ["stats_v_kohli", "stats_fuzzy_kohli"]:
        if k in results and isinstance(results[k], dict):
            d = results[k]
            if d.get("batter"):
                d["batter"] = {kk: vv for kk, vv in d["batter"].items() if kk not in ("runs_per_match", "format_runs", "dismissals")}
            if d.get("bowler"):
                d["bowler"] = {kk: vv for kk, vv in d["bowler"].items() if kk not in ("wickets_per_match", "format_wickets")}
    json.dump(results, f, indent=2)

print("Results written.")
