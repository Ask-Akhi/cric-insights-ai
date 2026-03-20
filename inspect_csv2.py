"""Inspect all info keys across a sample of CSVs to understand available metadata."""
from pathlib import Path
from collections import Counter
import csv

raw = Path('backend/src/data/raw/male')
csvs = list(raw.rglob('*.csv'))[:50]  # sample 50

info_keys = Counter()
for csv_file in csvs:
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if row and row[0] == 'info' and len(row) >= 2:
                info_keys[row[1]] += 1

print("Info keys found across 50 sample CSVs:")
for key, count in sorted(info_keys.items()):
    print(f"  {key}: {count}")
