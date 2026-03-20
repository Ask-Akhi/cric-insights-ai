import sys, os
from pathlib import Path

WORKSPACE = Path("c:/Users/1223505/Personal Apps")
sys.path.insert(0, str(WORKSPACE / ".venv312" / "Lib" / "site-packages"))
sys.path.insert(0, str(WORKSPACE))
os.chdir(str(WORKSPACE))

LOG = WORKSPACE / "verify_log.txt"
out = open(LOG, "w", encoding="utf-8")


def log(msg):
    out.write(str(msg) + "\n")
    out.flush()


try:
    import polars as pl
    log(f"polars {pl.__version__}")

    from backend.src.providers.cricsheet_provider import CricsheetProvider
    p = CricsheetProvider()
    p.load()
    log(f"Provider loaded: {p.loaded}")

    lf = p.datasets.get("balls")
    if lf is None:
        log("ERROR: balls dataset is None")
    else:
        df = lf.collect()
        log(f"Total rows: {df.height:,}")
        log(f"Columns: {df.columns}")

        fc = (
            df.group_by("format")
            .agg(pl.col("match_id").n_unique().alias("matches"))
            .sort("matches", descending=True)
        )
        log(f"\nFormat breakdown:\n{fc}")

        sample = (
            df.select(["match_id", "format", "start_date"])
            .unique(subset=["match_id"])
            .filter(pl.col("format").is_not_null())
            .head(5)
        )
        log(f"\nSample matches:\n{sample}")

        log(f"\nPlayer search Kohli: {p.list_players(q='Kohli', limit=10)}")

        ev = p.get_player_events("V Kohli")
        log(f"V Kohli events: {ev.height:,} rows")
        if ev.height > 0:
            bat = ev.filter(pl.col("batter") == "V Kohli")
            log(f"  Batting rows: {bat.height:,}, runs: {bat['runs_off_bat'].sum():,}")

        # Test venue stats
        venue_df = p.get_venue_stats("Wankhede")
        log(f"\nVenue stats (Wankhede): {venue_df.height:,} rows")

        # Test head-to-head
        h2h_df = p.get_head_to_head("India", "Australia")
        log(f"H2H (India vs Australia): {h2h_df.height:,} rows, "
            f"{h2h_df.select(pl.col('match_id').n_unique()).item() if not h2h_df.is_empty() else 0} matches")

except Exception as e:
    import traceback
    log(f"ERROR: {e}\n{traceback.format_exc()}")
finally:
    out.close()
