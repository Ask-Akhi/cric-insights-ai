#!/usr/bin/env python3
"""
patch_spm.py — Patches ALL Package.swift files found anywhere under
~/cric-insights-ai that declare swift-tools-version: 5.9, downgrading
them to 5.7 so Xcode 14 can build them.

Run: curl -s https://raw.githubusercontent.com/Ask-Akhi/cric-insights-ai/master/patch_spm.py | python3
"""
import os, glob, sys

# Search the whole repo tree (includes node_modules/@capacitor/splash-screen)
base = os.path.expanduser("~/cric-insights-ai")

if not os.path.isdir(base):
    print(f"ERROR: Repo not found at {base}")
    print("Run: git clone https://github.com/Ask-Akhi/cric-insights-ai ~/cric-insights-ai")
    sys.exit(1)

files = glob.glob(base + "/**/Package.swift", recursive=True)
if not files:
    print("No Package.swift files found — check the base path.")
    sys.exit(1)

patched = 0
for f in sorted(files):
    try:
        txt = open(f, encoding="utf-8").read()
    except Exception as e:
        print(f"SKIP (read error): {f} — {e}")
        continue

    if "swift-tools-version: 5.9" in txt:
        new_txt = txt.replace("swift-tools-version: 5.9", "swift-tools-version: 5.7")
        try:
            open(f, "w", encoding="utf-8").write(new_txt)
            print(f"Patched: {f}")
            patched += 1
        except Exception as e:
            print(f"SKIP (write error): {f} — {e}")
    else:
        print(f"OK (already <=5.7): {f}")

print(f"\nDone — {patched} file(s) patched.")
