import zipfile, sys

with zipfile.ZipFile('backend/src/data/raw/all_male_csv.zip') as z:
    with z.open('README.txt') as f:
        content = f.read().decode('utf-8')

lines = content.splitlines()

with open('readme_dump.txt', 'w', encoding='utf-8') as out:
    out.write(f"Total lines: {len(lines)}\n\n")
    out.write("=== FIRST 50 ===\n")
    for l in lines[:50]:
        out.write(repr(l) + "\n")
    out.write("\n=== LAST 30 ===\n")
    for l in lines[-30:]:
        out.write(repr(l) + "\n")
    out.write("\n=== Lines containing match IDs (numeric) ===\n")
    # match listing lines contain a long number (match id)
    import re
    pattern = re.compile(r'\b\d{7}\b')
    match_lines = [l for l in lines if pattern.search(l)]
    out.write(f"Found: {len(match_lines)}\n")
    for l in match_lines[:10]:
        out.write(repr(l) + "\n")

print("Written to readme_dump.txt")
