import asyncio, asyncpg, os

async def run_schema():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    sql = open('backend/src/db/schema.sql').read()
    await conn.execute(sql)
    print('Schema applied OK')
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    print('Tables:', [r['tablename'] for r in tables])
    await conn.close()

asyncio.run(run_schema())
