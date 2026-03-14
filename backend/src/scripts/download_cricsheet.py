import argparse
import os
import zipfile
from pathlib import Path
import httpx
import polars as pl

DATA_DIR = Path(os.environ.get("CRICSHEET_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data")))
RAW_DIR = DATA_DIR / "raw"
PARQUET_DIR = DATA_DIR / "parquet"

MEN_URL = "https://cricsheet.org/downloads/all_male_csv.zip"
WOMEN_URL = "https://cricsheet.org/downloads/all_female_csv.zip"

# Simple column name mapping to standardize
COLMAP = {
    "match_id": "match_id",
    "season": "season",
    "start_date": "start_date",
    "gender": "gender",
    "team": "batting_team",
    "opposition": "bowling_team",
    "venue": "venue",
    "city": "city",
    "country": "country",
    "competition": "competition",
    "match_type": "format",
    "innings": "innings",
    "ball": "ball",
    "bat_striker": "batter",
    "bat_non_striker": "non_striker",
    "bowler": "bowler",
    "runs_off_bat": "runs_off_bat",
    "extras": "extras",
    "wides": "wides",
    "noballs": "noballs",
    "byes": "byes",
    "legbyes": "legbyes",
    "penalties": "penalties",
    "wicket_type": "wicket_type",
    "player_dismissed": "player_dismissed",
}

# Some cricsheet CSVs may have different header cases; helper to rename safely
def standardize_columns(df: pl.DataFrame) -> pl.DataFrame:
    lower = {c.lower(): c for c in df.columns}
    # build mapping based on lower-case
    rename_map = {}
    for src_lower, dest in COLMAP.items():
        if src_lower in lower:
            rename_map[lower[src_lower]] = dest
    df = df.rename(rename_map)
    return df


def download_zip(url: str, dest_zip: Path):
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_zip, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)


def extract_zip(zip_path: Path, dest_dir: Path):
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(dest_dir)


def _read_csv_resilient(csv_path: Path) -> pl.DataFrame:
    """Read CSV using polars with options to handle ragged lines and inconsistent rows.
    Try a primary read with truncate_ragged_lines, then a fallback with ignore_errors for bad rows.
    """
    try:
        return pl.read_csv(
            csv_path,
            null_values=[""],
            infer_schema_length=1000,
            truncate_ragged_lines=True,
        )
    except Exception:
        # Fallback: try reading with a larger infer length and skip rows with errors
        return pl.read_csv(
            csv_path,
            null_values=[""],
            infer_schema_length=2000,
            truncate_ragged_lines=True,
            ignore_errors=True,
        )


def parse_csv_folder_to_parquet(src_dir: Path, gender: str):
    """
    Walk CSVs under src_dir and write parquet files partitioned by format under PARQUET_DIR/gender/format.
    Keeps a single unified schema as much as possible.
    """
    out_base = PARQUET_DIR / gender
    out_base.mkdir(parents=True, exist_ok=True)

    csv_files = list(src_dir.rglob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {src_dir}")
        return

    failures = []

    # Expected minimal schema dtypes (best-effort); we won't hard-fail, just warn
    expected_types = {
        "gender": pl.Utf8,
        "format": pl.Utf8,
        "competition": pl.Utf8,
        "venue": pl.Utf8,
        "city": pl.Utf8,
        "country": pl.Utf8,
        "batting_team": pl.Utf8,
        "bowling_team": pl.Utf8,
        "innings": pl.Int32,
        "ball": pl.Float64,
        "runs_off_bat": pl.Int32,
        "extras": pl.Int32,
    }

    for csv_path in csv_files:
        try:
            df = _read_csv_resilient(csv_path)
            df = standardize_columns(df)
            # Ensure required columns exist, add defaults if missing
            required = [
                "match_id","season","start_date","gender","format","competition","venue","city","country",
                "batting_team","bowling_team","innings","ball","batter","non_striker","bowler","runs_off_bat","extras",
                "wides","noballs","byes","legbyes","penalties","wicket_type","player_dismissed"
            ]
            for col in required:
                if col not in df.columns:
                    df = df.with_columns(pl.lit(None).alias(col))

            # Casts
            df = df.with_columns([
                pl.col("gender").fill_null(gender).cast(pl.Utf8),
                pl.col("format").cast(pl.Utf8),
                pl.col("competition").cast(pl.Utf8),
                pl.col("venue").cast(pl.Utf8),
                pl.col("city").cast(pl.Utf8),
                pl.col("country").cast(pl.Utf8),
                pl.col("batting_team").cast(pl.Utf8),
                pl.col("bowling_team").cast(pl.Utf8),
                pl.col("innings").cast(pl.Int32),
                pl.col("ball").cast(pl.Float64),
                pl.col("runs_off_bat").cast(pl.Int32),
                pl.col("extras").cast(pl.Int32),
            ])

            # Basic schema validation warnings
            mismatches = []
            for name, dtype in expected_types.items():
                if name in df.columns and df.schema[name] != dtype:
                    mismatches.append(f"{name}: {df.schema[name]} -> {dtype}")
            if mismatches:
                print(f"[Schema warn] {csv_path.name} mismatched types: {', '.join(mismatches)}")

            # Detect format (partition directory)
            fmt = None
            if "format" in df.columns:
                fmt_series = df.select(pl.col("format")).to_series().drop_nulls()
                fmt = fmt_series.mode().first() if fmt_series.len() > 0 else None
            fmt_dir = out_base / (fmt or "Unknown")
            fmt_dir.mkdir(parents=True, exist_ok=True)

            # Write per-match parquet to keep files small
            if "match_id" in df.columns:
                # Iterate unique match_id values; filter for each
                mids = (
                    df.select(pl.col("match_id")).drop_nulls().unique().to_series().to_list()
                    if df.height > 0
                    else []
                )
                if mids:
                    for match_id in mids:
                        # Safe filename string
                        mid_str = str(match_id).replace("/", "-").replace("\\", "-").strip()
                        subdf = df.filter(pl.col("match_id") == match_id)
                        out_path = fmt_dir / f"{mid_str}.parquet"
                        subdf.write_parquet(out_path)
                else:
                    # No valid match_id values, fallback single parquet per file
                    out_path = fmt_dir / (csv_path.stem + ".parquet")
                    df.write_parquet(out_path)
            else:
                # Fallback single parquet per file
                out_path = fmt_dir / (csv_path.stem + ".parquet")
                df.write_parquet(out_path)
            print(f"Parsed {csv_path.name} -> {fmt or 'Unknown'}")
        except Exception as e:
            # capture a brief head for context
            head = None
            try:
                head = df.head(3).to_dict(as_series=False) if 'df' in locals() else None
            except Exception:
                head = None
            failures.append((csv_path, str(e), head))
            print(f"Failed to parse {csv_path}: {e}")

    if failures:
        log_path = out_base / "parse_failures.log"
        with open(log_path, "w", encoding="utf-8") as f:
            for item in failures:
                path, err, head = item
                f.write(f"{path}: {err}\n")
                if head is not None:
                    f.write(f"Sample rows: {head}\n")
        print(f"Completed with {len(failures)} failures. See {log_path} for details.")
    else:
        print("All files parsed successfully.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--men", action="store_true")
    parser.add_argument("--women", action="store_true")
    parser.add_argument("--parse", action="store_true", help="Parse extracted CSVs to parquet")
    args = parser.parse_args()

    if not args.men and not args.women:
        print("Specify --men and/or --women")
        # Still allow parse-only if data present
        if not args.parse:
            return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    if args.men:
        men_zip = RAW_DIR / "all_male_csv.zip"
        print("Downloading men data...")
        download_zip(MEN_URL, men_zip)
        extract_zip(men_zip, RAW_DIR / "male")
    if args.women:
        women_zip = RAW_DIR / "all_female_csv.zip"
        print("Downloading women data...")
        download_zip(WOMEN_URL, women_zip)
        extract_zip(women_zip, RAW_DIR / "female")

    if args.parse:
        # Parse folders if present
        male_dir = RAW_DIR / "male"
        female_dir = RAW_DIR / "female"
        if male_dir.exists():
            print("Parsing male CSVs to parquet...")
            parse_csv_folder_to_parquet(male_dir, gender="male")
        if female_dir.exists():
            print("Parsing female CSVs to parquet...")
            parse_csv_folder_to_parquet(female_dir, gender="female")

    print("Done.")


if __name__ == "__main__":
    main()
