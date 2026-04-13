"""
Shared token budgeting utilities.

Uses tiktoken for accurate token counting when available,
falls back to character-based estimation otherwise.

Used by llm_client, cricket_graph, and context_assembler.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from .config import settings

log = logging.getLogger("core.token_utils")

# ── Try to load a real tokenizer ───────────────────────────────
_tokenizer: object | None = None
_tokenizer_loaded = False


def _init_tokenizer() -> None:
    global _tokenizer, _tokenizer_loaded
    if _tokenizer_loaded:
        return
    _tokenizer_loaded = True

    try:
        import tiktoken

        _tokenizer = tiktoken.get_encoding("cl100k_base")
        log.info("Using tiktoken (cl100k_base) for token counting")
    except Exception:
        _tokenizer = None
        log.info("tiktoken not available — using character-based estimation")


def count_tokens(text: str) -> int:
    """Count tokens accurately when possible, estimate otherwise."""
    if not text:
        return 0
    _init_tokenizer()

    if _tokenizer is not None:
        try:
            return len(_tokenizer.encode(text))  # type: ignore[union-attr]
        except Exception:
            pass

    return _estimate_tokens(text)


def _estimate_tokens(text: str) -> int:
    """Character-based token estimation with content-type adjustments."""
    if not text:
        return 0

    base = len(text) // 4

    # Markdown tables have more overhead (pipes, dashes)
    table_rows = text.count("|") // 2
    if table_rows > 5:
        base = int(base * 1.15)

    # Very short text has higher per-token overhead
    if len(text) < 50:
        base = max(base, len(text.split()))

    return max(1, base)


# ── Public aliases ─────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    """Alias for count_tokens — backward compat."""
    return count_tokens(text)


def max_tokens_for(prompt: str) -> int:
    """Dynamic max output tokens based on query complexity."""
    p = prompt.lower()

    # Complex: fantasy, predictions, comparisons, full tables
    if any(
        w in p
        for w in [
            "fantasy",
            "dream11",
            "playing xi",
            "playing 11",
            "predict",
            "head to head",
            "compare",
            "captain",
            "vice captain",
        ]
    ):
        return settings.max_tokens_complex  # 4096

    # Medium: stats, single-player analysis
    if any(
        w in p
        for w in [
            "average",
            "strike rate",
            "economy",
            "career",
            "record",
            "stats",
            "ranking",
            "centuries",
            "wickets",
            "top scorer",
            "best",
        ]
    ):
        return settings.max_tokens_medium  # 2048

    # Simple: short factual queries
    if len(p) < 60:
        return settings.max_tokens_simple  # 1024

    return settings.max_tokens_medium  # 2048


def truncate_to_budget(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a token budget, preserving sentence boundaries."""
    current = count_tokens(text)
    if current <= max_tokens:
        return text

    # Approximate character cutoff
    ratio = max_tokens / max(current, 1)
    max_chars = int(len(text) * ratio * 0.95)  # 5% safety margin
    truncated = text[:max_chars]

    # Try to end at a sentence boundary
    last_period = truncated.rfind(".")
    last_newline = truncated.rfind("\n")
    best_break = max(last_period, last_newline)

    if best_break > max_chars * 0.7:
        truncated = truncated[: best_break + 1]

    return truncated + "\n\n[Context truncated to fit token budget]"


def remaining_budget(used: int, total: Optional[int] = None) -> int:
    """Calculate remaining token budget."""
    total = total or settings.mcp_max_context_tokens
    return max(0, total - used)
