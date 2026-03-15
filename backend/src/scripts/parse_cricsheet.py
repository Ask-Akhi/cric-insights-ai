"""
parse_cricsheet.py
──────────────────
Converts raw Cricsheet "v1 CSV" match files into Parquet datasets.

CSV format (v1.x):
  • info rows  → info, <key>, <value>
  • ball rows  → ball, <innings>, <over>, <batting_team>, <batter>,
                       <non_striker>, <bowler>, <runs_off_bat>, <extras>,
                       <wides>, <noballs>, <byes>, <legbyes>, <penalties>,
                       <wicket_type>, <player_dismissed>

Format is NOT stored in the v1 CSV — it is parsed from the README inside
each gender zip file (e.g. all_male_csv.zip).

Run:
    python -m backend.src.scripts.parse_cricsheet [--gender male|female|both]
                                                   [--batch 1000]
                                                   [--force]
                                                   [--patch]   # fix format col on existing parquets
"""

import argparse
import csv
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional

import polars as pl

# ── Paths ──────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve()
DATA_DIR = Path(os.environ.get("CRICSHEET_DATA_DIR",
                               str(_HERE.parents[1] / "data")))
RAW_DIR  = DATA_DIR / "raw"
PARQ_DIR = DATA_DIR / "parquet"

ZIP_NAMES = {
    "male":   "all_male_csv.zip",
    "female": "all_female_csv.zip",
}

# ── Ball column names (positional) ────────────────────────────────────────
BALL_COLS = [
    "innings", "over", "batting_team", "batter", "non_striker",
    "bowler", "runs_off_bat", "extras",
    "wides", "noballs", "byes", "legbyes", "penalties",
    "wicket_type", "player_dismissed",
]

# ── Info keys ─────────────────────────────────────────────────────────────
INFO_SCALAR = {
    "season", "venue", "city",
    "competition", "toss_winner", "toss_decision", "winner",
    "player_of_match", "event",
}


# ── README parser → match_id: str → format: str ───────────────────────────
# README lines look like:
#   2016-11-03 - international - Test - male - 1000851 - Australia vs South Africa
_README_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+-\s+\S+\s+-\s+(\S+)\s+-\s+\S+\s+-\s+(\d+)\s+-"
)

def build_format_map(gender: str) -> Dict[str, str]:
    """Parse the README inside the gender zip → {match_id: format}."""
    zip_path = RAW_DIR / ZIP_NAMES[gender]
    fmt_map: Dict[str, str] = {}
    if not zip_path.exists():
        print(f"  [WARN] Zip not found: {zip_path}", file=sys.stderr)
        return fmt_map
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            readme = next((n for n in names if "README" in n.upper()), None)
            if not readme:
                return fmt_map
            with z.open(readme) as f:
                for line in f.read().decode("utf-8", errors="replace").splitlines():
                    m = _README_RE.match(line.strip())
                    if m:
                        fmt, mid = m.group(1), m.group(2)
                        fmt_map[mid] = fmt
    except Exception as e:
        print(f"  [WARN] Could not read README from {zip_path}: {e}", file=sys.stderr)
    print(f"  [README] {gender}: {len(fmt_map):,} match→format mappings loaded")
    return fmt_map


# ── CSV parser ────────────────────────────────────────────────────────────
def _parse_csv(
    path: Path,
    match_id: str,
    gender: str,
    fmt_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    info: Dict[str, Any] = {
        "match_id": match_id,
        "gender":   gender,
        "format":   fmt_map.get(match_id),   # from README
    }
    dates: List[str] = []
    squad: Dict[str, List[str]] = {}  # team → [players]
    rows: List[Dict[str, Any]] = []

    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for rec in reader:
            if not rec:
                continue
            kind = rec[0]

            if kind == "info" and len(rec) >= 3:
                key, val = rec[1], rec[2]
                if key in INFO_SCALAR:
                    info[key] = val
                elif key == "date":
                    dates.append(val)
                elif key == "player" and len(rec) >= 4:
                    # info,player,<team>,<name>
                    team_name = rec[2]
                    player_name = rec[3]
                    squad.setdefault(team_name, []).append(player_name)

            elif kind == "ball" and len(rec) >= 16:
                ball: Dict[str, Any] = dict(info)
                for i, col in enumerate(BALL_COLS):
                    raw = rec[i + 1].strip().strip('"')
                    ball[col] = raw if raw else None
                rows.append(ball)

    start_date = min(dates) if dates else None
    for r in rows:
        r["start_date"] = start_date

    return rows


# ── Schema ────────────────────────────────────────────────────────────────
SCHEMA = {
    "match_id":         pl.Utf8,
    "gender":           pl.Utf8,
    "format":           pl.Utf8,
    "season":           pl.Utf8,
    "start_date":       pl.Utf8,
    "venue":            pl.Utf8,
    "city":             pl.Utf8,
    "competition":      pl.Utf8,
    "event":            pl.Utf8,
    "toss_winner":      pl.Utf8,
    "toss_decision":    pl.Utf8,
    "winner":           pl.Utf8,
    "innings":          pl.Int32,
    "over":             pl.Utf8,
    "batting_team":     pl.Utf8,
    "batter":           pl.Utf8,
    "non_striker":      pl.Utf8,
    "bowler":           pl.Utf8,
    "runs_off_bat":     pl.Int32,
    "extras":           pl.Int32,
    "wides":            pl.Int32,
    "noballs":          pl.Int32,
    "byes":             pl.Int32,
    "legbyes":          pl.Int32,
    "penalties":        pl.Int32,
    "wicket_type":      pl.Utf8,
    "player_dismissed": pl.Utf8,
}

INT_COLS = {
    "innings", "runs_off_bat", "extras", "wides",
    "noballs", "byes", "legbyes", "penalties",
}


def _int_or_none(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _rows_to_df(rows: List[Dict[str, Any]]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(
            {col: pl.Series([], dtype=dt) for col, dt in SCHEMA.items()}
        )
    for r in rows:
        for col in INT_COLS:
            r[col] = _int_or_none(r.get(col))

    data: Dict[str, list] = {col: [] for col in SCHEMA}
    for r in rows:
        for col in SCHEMA:
            data[col].append(r.get(col))

    series = {}
    for col, dtype in SCHEMA.items():
        if dtype == pl.Int32:
            series[col] = pl.Series(col, data[col], dtype=pl.Int32)
        else:
            series[col] = pl.Series(col, data[col], dtype=pl.Utf8)
    return pl.DataFrame(series)


# ── Main conversion ───────────────────────────────────────────────────────
def process_gender(gender: str, batch: int = 1000, force: bool = False) -> int:
    out_dir = PARQ_DIR / gender
    out_dir.mkdir(parents=True, exist_ok=True)

    fmt_map = build_format_map(gender)

    csv_files = sorted((RAW_DIR / gender).rglob("*.csv")) if (RAW_DIR / gender).is_dir() else []
    total = len(csv_files)
    if total == 0:
        print(f"[{gender}] No CSV files found in {RAW_DIR / gender}")
        return 0

    done: set = set()
    if not force:
        for p in out_dir.rglob("*.parquet"):
            if p.stem.isdigit():
                done.add(p.stem)

    pending = [p for p in csv_files if p.stem not in done]
    print(f"[{gender}] {total} CSVs | {len(done)} done | {len(pending)} pending")

    converted = 0
    buf: List[Dict[str, Any]] = []
    batch_idx = len(list(out_dir.glob("batch_*.parquet")))

    def _flush():
        nonlocal batch_idx
        if not buf:
            return
        df = _rows_to_df(buf)
        out_path = out_dir / f"batch_{batch_idx:05d}.parquet"
        df.write_parquet(str(out_path))
        buf.clear()
        print(f"  wrote {out_path.name}  ({df.height:,} rows)")
        batch_idx += 1

    for i, csv_path in enumerate(pending):
        match_id = csv_path.stem
        try:
            rows = _parse_csv(csv_path, match_id, gender, fmt_map)
            buf.extend(rows)
        except Exception as exc:
            print(f"  [SKIP] {csv_path.name}: {exc}", file=sys.stderr)

        converted += 1
        if len(buf) >= batch * 200:
            _flush()

        if (i + 1) % 500 == 0:
            print(f"  parsed {i+1}/{len(pending)} ...")

    _flush()
    print(f"[{gender}] Done -- {converted} new matches converted.")
    return converted


# ── Patch mode: add format col to existing parquets ───────────────────────
def patch_format(gender: str) -> None:
    """Add/overwrite the format column in existing batch parquets using README map."""
    out_dir = PARQ_DIR / gender
    fmt_map = build_format_map(gender)
    if not fmt_map:
        print(f"[{gender}] No format map — skipping patch")
        return

    parquets = sorted(out_dir.glob("batch_*.parquet"))
    print(f"[{gender}] Patching {len(parquets)} parquet files with format column...")

    for p in parquets:
        df = pl.read_parquet(p)

        # Drop stale junk columns (version number columns like '1.6.0', '1.7.0')
        drop_cols = [c for c in df.columns if re.match(r'^\d+\.\d+\.\d+$', c) or
                     re.match(r'^\d+\.\d+\.\d+\.\d+$', c)]
        # Also drop any column that is just a raw version string header
        drop_cols += [c for c in df.columns if c not in SCHEMA]
        if drop_cols:
            df = df.drop(drop_cols)

        # Add missing schema columns
        for col, dtype in SCHEMA.items():
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).cast(dtype).alias(col))

        # Apply format from map
        if "match_id" in df.columns:
            df = df.with_columns(
                pl.col("match_id").replace(fmt_map, default=None).alias("format")
            )

        # Ensure correct column order
        cols_ordered = [c for c in SCHEMA if c in df.columns]
        df = df.select(cols_ordered)

        df.write_parquet(p)

    print(f"[{gender}] Patch complete.")


# ── CLI ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Parse Cricsheet CSVs to Parquet")
    ap.add_argument("--gender", choices=["male", "female", "both"], default="both")
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--patch", action="store_true",
                    help="Patch format col on existing parquets instead of re-parsing")
    args = ap.parse_args()

    genders = ["male", "female"] if args.gender == "both" else [args.gender]
    for g in genders:
        if args.patch:
            patch_format(g)
        else:
            process_gender(g, batch=args.batch, force=args.force)


if __name__ == "__main__":
    main()
