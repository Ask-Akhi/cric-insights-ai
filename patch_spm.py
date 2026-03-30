#!/usr/bin/env python3
"""
patch_spm.py — Patches ALL Package.swift files found anywhere under
~/cric-insights-ai that declare swift-tools-version: 5.9, downgrading
them to 5.7 so Xcode 14 can build them.

Also clears Xcode's SPM cache so stale resolved packages don't cause
"package 'capapp-spm' is using Swift tools version 5.9.0 but installed
version is 5.7.0" errors even after the file has been patched.

Run on Mac:
  curl -s https://raw.githubusercontent.com/Ask-Akhi/cric-insights-ai/master/patch_spm.py | python3
"""
import os, glob, sys, shutil, subprocess

# Search the whole repo tree (includes node_modules/@capacitor/splash-screen)
base = os.path.expanduser("~/cric-insights-ai")

if not os.path.isdir(base):
    print(f"ERROR: Repo not found at {base}")
    print("Run: git clone https://github.com/Ask-Akhi/cric-insights-ai ~/cric-insights-ai")
    sys.exit(1)

# ── 1. Patch all Package.swift files ──────────────────────────────────────────
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

# ── 2. Clear Xcode SPM cache (fixes "stale resolved" errors in Xcode 14) ──────
print("\n── Clearing Xcode SPM caches ──────────────────────────────────────────────")

spm_cache = os.path.expanduser("~/Library/Caches/org.swift.swiftpm")
xcode_spm  = os.path.expanduser("~/Library/org.swift.swiftpm")
build_dirs = glob.glob(base + "/frontend/ios/App/.build")

for path in [spm_cache, xcode_spm] + build_dirs:
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
            print(f"Removed: {path}")
        except Exception as e:
            print(f"Could not remove {path}: {e}")
    else:
        print(f"Not present (OK): {path}")

# Also remove Package.resolved so Xcode re-resolves from scratch
resolved_files = glob.glob(base + "/**/Package.resolved", recursive=True)
for r in resolved_files:
    try:
        os.remove(r)
        print(f"Removed resolved: {r}")
    except Exception as e:
        print(f"Could not remove {r}: {e}")

print("""
── All done! ─────────────────────────────────────────────────────────────────
Now run in Terminal:
  open ~/cric-insights-ai/frontend/ios/App/App.xcworkspace

Wait ~30 s for SPM to auto-resolve packages, then click ▶ in Xcode.
──────────────────────────────────────────────────────────────────────────────
""")
