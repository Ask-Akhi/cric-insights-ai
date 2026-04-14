"""
Context Assembler — merges MCP tool results into a single prompt context block.

Token-aware: uses count_tokens() to stay within budget, truncating
lowest-priority results first.
"""
from __future__ import annotations

import logging
import re
from typing import Sequence

from ..core.config import settings
from ..core.result import ToolResult
from ..core.token_utils import count_tokens, truncate_to_budget

log = logging.getLogger("mcp.context_assembler")

# Patterns that indicate a tool returned no useful data (noise to filter out)
_EMPTY_PATTERNS = (
    "no head-to-head data found",
    "no matchup data found",
    "no batting data found",
    "no bowling data found",
    "no venue data found",
    "no data found",
    "no form data found",
    "error fetching",
    "daily usage limit",                  # quota error leaked from web_search
    "ai service has reached",             # quota warning message from fallback
)


def _is_empty_result(r: ToolResult) -> bool:
    """Check if a tool result is effectively empty / 'no data found' noise."""
    if not r.data or not r.data.strip():
        return True
    data_lower = r.data.strip().lower()
    return any(pat in data_lower for pat in _EMPTY_PATTERNS)


# Source priority — lower number = higher priority (kept first when truncating)
_SOURCE_PRIORITY: dict[str, int] = {
    "cricsheet": 1,
    "live": 2,
    "search": 5,
}


def assemble(
    results: Sequence[ToolResult],
    max_tokens: int | None = None,
) -> str:
    """
    Merge tool results into a single context string, respecting token budget.

    Strategy:
      1. Sort by source priority (cheapest/most-reliable first)
      2. Add results one by one until budget is reached
      3. Truncate the last added result if it would exceed the budget
      4. Wrap in clear section delimiters so the LLM knows what came from where
    """
    budget = max_tokens or settings.mcp_max_context_tokens    # Filter out failed / empty results and suppress "no data found" noise
    good = [r for r in results if r.ok and not _is_empty_result(r)]
    if not good:
        return ""

    # Sort by source priority (stable sort preserves insertion order within same priority)
    good.sort(key=lambda r: _SOURCE_PRIORITY.get(r.source, 99))

    sections: list[str] = []
    used_tokens = 0

    for r in good:
        section = _format_section(r)
        section_tokens = count_tokens(section)

        if used_tokens + section_tokens <= budget:
            sections.append(section)
            used_tokens += section_tokens
        else:
            # Partial fit — truncate this section to fill remaining budget
            remaining = budget - used_tokens
            if remaining > 100:  # only worth adding if > 100 tokens remain
                truncated = truncate_to_budget(section, remaining)
                sections.append(truncated)
                used_tokens += count_tokens(truncated)
            break  # budget exhausted

    if not sections:
        return ""

    assembled = "\n\n".join(sections)
    log.info(
        "Assembled %d sections, ~%d tokens (budget %d)",
        len(sections), used_tokens, budget,
    )
    return assembled


# ── Section delimiter regex for stripping before user-facing output ──────────

_DELIMITER_RE = re.compile(
    r"---\s*(?:END\s+)?"
    r"(?:CRICSHEET BALL-BY-BALL DATA|LIVE/RECENT MATCH DATA|WEB SEARCH RESULTS)"
    r"(?:\s*\(tool:\s*\w+\))?\s*---[ \t]*\n?",
    re.IGNORECASE,
)


def strip_delimiters(text: str) -> str:
    """
    Remove internal section delimiters from assembled context so it reads
    cleanly when served directly to users (quota fallback, circuit breaker).

    Delimiters like ``--- CRICSHEET BALL-BY-BALL DATA (tool: team_matchup) ---``
    are meant for LLM consumption, not end users.
    """
    if not text:
        return text
    cleaned = _DELIMITER_RE.sub("", text)
    # Collapse runs of 3+ blank lines into 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _format_section(r: ToolResult) -> str:
    """Format a single tool result as a delimited section."""
    source_label = {
        "cricsheet": "CRICSHEET BALL-BY-BALL DATA",
        "live": "LIVE/RECENT MATCH DATA",
        "search": "WEB SEARCH RESULTS",
    }.get(r.source, r.source.upper())

    return (
        f"--- {source_label} (tool: {r.tool_name}) ---\n"
        f"{r.data}\n"
        f"--- END {source_label} ---"
    )


def quality_gate(results: Sequence[ToolResult]) -> dict:
    """
    Check whether tool results have enough substance for a good LLM answer.

    Returns:
        {
            "pass": bool,
            "total_tokens": int,
            "good_count": int,
            "sources": list[str],
            "reason": str,   # only set when pass=False
        }
    """
    good = [r for r in results if r.ok and not _is_empty_result(r)]
    total_tokens = sum(r.tokens_estimate for r in good)
    sources = list({r.source for r in good})

    if not good:
        return {
            "pass": False,
            "total_tokens": 0,
            "good_count": 0,
            "sources": [],
            "reason": "No tools returned useful data",
        }

    # Very thin results — less than 50 tokens total
    if total_tokens < 50:
        return {
            "pass": False,
            "total_tokens": total_tokens,
            "good_count": len(good),
            "sources": sources,
            "reason": f"Tool results too thin ({total_tokens} tokens)",
        }

    return {
        "pass": True,
        "total_tokens": total_tokens,
        "good_count": len(good),
        "sources": sources,
    }
