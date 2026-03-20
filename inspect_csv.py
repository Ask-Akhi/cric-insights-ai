from pathlib import Path
import csv

raw = Path('backend/src/data/raw/male')
csv_file = list(raw.rglob('*.csv'))[0]
print("File:", csv_file)

# Read raw content to see true line endings
with open(csv_file, 'rb') as f:
    raw_bytes = f.read(2000)

print("\n--- Raw bytes (first 2000) ---")
print(repr(raw_bytes[:500]))

# Now read as text with universal newlines
with open(csv_file, 'r', newline='', encoding='utf-8') as f:
    content = f.read()

lines = content.splitlines()
print(f"\nTotal lines (splitlines): {len(lines)}")

# Find non-info lines
ball_lines = [l for l in lines if l.startswith('ball,')]
print(f"Ball lines: {len(ball_lines)}")
if ball_lines:
    print(f"\nFirst ball line: {repr(ball_lines[0])}")
    cols = ball_lines[0].split(',')
    print(f"Column count: {len(cols)}")
    print(f"Columns: {cols}")
    
    # Find a wicket line
    for bl in ball_lines:
        parts = bl.split(',')
        if len(parts) > 0 and parts[-1].strip().strip('"') not in ('', ):
            print(f"\nWicket line: {repr(bl)}")
            print(f"Parts: {parts}")
            break

# Also read with csv module to see how it parses
print("\n--- CSV module parse of first 5 ball rows ---")
with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    count = 0
    for row in reader:
        if row and row[0] == 'ball':
            print(f"  {row}")
            count += 1
            if count >= 5:
                break
