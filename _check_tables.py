import asyncio, asyncpg, os, sys
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def check():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        print("DATABASE_URL not set in env or backend/.env", flush=True)
        sys.exit(1)
    print(f"Connecting to: {url.split('@')[1] if '@' in url else url}", flush=True)
    conn = await asyncpg.connect(url)
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    print("\nTables in Supabase:", flush=True)
    for r in tables:
        print(" -", r['tablename'], flush=True)
    print("\nRow counts:", flush=True)
    for t in ['player_season_stats', 'head_to_head_summary', 'match_summary', 'recent_form']:
        try:
            n = await conn.fetchval(f"SELECT COUNT(*) FROM {t}")
            print(f"   {t}: {n} rows", flush=True)
        except Exception as e:
            print(f"   {t}: ERROR {e}", flush=True)
    await conn.close()

asyncio.run(check())
