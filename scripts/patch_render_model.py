from __future__ import annotations

import pathlib

p = pathlib.Path("render.yaml")
t = p.read_text(encoding="utf-8")

# Normalize possible weird whitespace/line endings and patch the model value.
# We patch any line that sets LLM_MODEL under envVars.
out_lines: list[str] = []
lines = t.splitlines(True)
i = 0
while i < len(lines):
    line = lines[i]
    out_lines.append(line)
    if "- key:" in line and "LLM_MODEL" in line:
        # Next non-empty line with 'value:' should be the model choice.
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            out_lines.append(lines[j])
            j += 1
        if j < len(lines) and lines[j].lstrip().startswith("value:"):
            indent = lines[j].split("value:")[0]
            out_lines.append(f"{indent}value: gemini-2.5-flash\n")
            i = j + 1
            continue
    i += 1

new_t = "".join(out_lines)
p.write_text(new_t, encoding="utf-8")

# Print what we set (for debugging)
for l in new_t.splitlines():
    if "- key:" in l and "LLM_MODEL" in l:
        print(l)
    if l.strip().startswith("value:") and "gemini" in l:
        # print nearby values
        pass
