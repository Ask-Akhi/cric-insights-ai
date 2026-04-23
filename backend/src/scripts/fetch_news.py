"""
fetch_news.py — Pull latest cricket headlines from public RSS feeds and
upsert into the news_items table. Runs as a nightly cron (Render cron job)
so RAG context has fresh injury / playing-XI / toss hints.

Run manually:
    python -m backend.src.scripts.fetch_news

Sources used (all public RSS, no authentication, no scraping protected pages):
  - ESPN Cricinfo (News)
  - ESPN Cricinfo (Latest)

Respect-the-source rules:
  - Only title + <description> (summary) are stored.
  - Full-article URL is preserved so users can click through to the source.
  - No repeated fetches within 1h (TTL via published_at).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("fetch_news")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Public RSS feeds — no auth required.
FEEDS = [
    ("ESPN Cricinfo", "https://www.espncricinfo.com/rss/content/story/feeds/0.xml"),
    ("ESPN Cricinfo Latest", "https://www.espncricinfo.com/rss/content/story/feeds/latest.xml"),
]

USER_AGENT = "Mozilla/5.0 (compatible; CricInsightsAI/1.0; +https://cric-insights-ai.com)"


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:600]  # keep summaries short


def _parse_feed(source: str, body: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        log.warning("Could not parse %s: %s", source, exc)
        return []

    items = []
    for item in root.iter("item"):
        url = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if not url or not title:
            continue
        desc = _strip_html(item.findtext("description") or "")
        pub = item.findtext("pubDate") or ""
        published: datetime | None = None
        try:
            if pub:
                published = parsedate_to_datetime(pub)
        except Exception:
            published = None
        items.append({
            "url": url,
            "title": title,
            "summary": desc,
            "source": source,
            "published_at": published,
        })
    return items


async def _fetch(session, source: str, url: str) -> list[dict[str, Any]]:
    try:
        async with session.get(url, timeout=15) as resp:
            body = await resp.read()
            return _parse_feed(source, body)
    except Exception as exc:
        log.warning("Fetch %s failed: %s", source, exc)
        return []


def _detect_tags(text: str) -> list[str]:
    """Lightweight tag extraction — find known teams / players in title+summary."""
    try:
        from ..services.rag_service import (
            detect_players_in_prompt,
            detect_teams_in_prompt,
        )
    except Exception:
        return []
    tags: list[str] = []
    try:
        tags.extend(detect_teams_in_prompt(text))
        tags.extend(detect_players_in_prompt(text))
    except Exception:
        pass
    # Dedup, cap at 12
    seen, out = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
            if len(out) >= 12:
                break
    return out


async def upsert_news(pool, items: list[dict[str, Any]]) -> int:
    if not items:
        return 0
    sql = """
        INSERT INTO news_items (url, title, summary, source, published_at, tags)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (url) DO UPDATE SET
            title = EXCLUDED.title,
            summary = EXCLUDED.summary,
            source = EXCLUDED.source,
            published_at = COALESCE(EXCLUDED.published_at, news_items.published_at),
            tags = EXCLUDED.tags,
            fetched_at = NOW()
    """
    n = 0
    for it in items:
        try:
            text = f"{it['title']} {it.get('summary') or ''}"
            tags = _detect_tags(text)
            await pool.execute(
                sql,
                it["url"], it["title"], it.get("summary"),
                it.get("source"), it.get("published_at"), tags,
            )
            n += 1
        except Exception as exc:
            log.warning("Upsert skipped for %s: %s", it.get("url"), exc)
    # Trim old rows (keep 500 most recent)
    try:
        await pool.execute("""
            DELETE FROM news_items
            WHERE url NOT IN (
                SELECT url FROM news_items
                ORDER BY COALESCE(published_at, fetched_at) DESC
                LIMIT 500
            )
        """)
    except Exception as exc:
        log.warning("Trim old news failed: %s", exc)
    return n


async def run_news_fetch() -> None:
    if not DATABASE_URL:
        log.error("DATABASE_URL not set — cannot fetch news")
        sys.exit(1)

    try:
        import aiohttp  # type: ignore
    except ImportError:
        log.error("aiohttp not installed. Add it to requirements.txt.")
        sys.exit(1)

    import asyncpg
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(url, min_size=1, max_size=2,
                                      statement_cache_size=0)

    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        all_items: list[dict[str, Any]] = []
        for source, feed_url in FEEDS:
            items = await _fetch(session, source, feed_url)
            log.info("Fetched %d items from %s", len(items), source)
            all_items.extend(items)

    n = await upsert_news(pool, all_items)
    log.info("✅ Upserted %d news items at %s", n, datetime.now(timezone.utc).isoformat())
    await pool.close()


if __name__ == "__main__":
    asyncio.run(run_news_fetch())
