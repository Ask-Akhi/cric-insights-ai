import sys, os
sys.path.insert(0, r'c:\Users\1223505\Personal Apps')
os.chdir(r'c:\Users\1223505\Personal Apps')

from backend.src.scripts.parse_cricsheet import patch_format, build_format_map

try:
    print("Building format map for male...")
    m = build_format_map("male")
    print(f"  Got {len(m)} entries")
    sample = list(m.items())[:3]
    print(f"  Sample: {sample}")

    print("\nPatching male parquets...")
    patch_format("male")

    print("\nPatching female parquets...")
    patch_format("female")

    print("\nAll done.")
except Exception as e:
    import traceback
    print("ERROR:", e)
    traceback.print_exc()
