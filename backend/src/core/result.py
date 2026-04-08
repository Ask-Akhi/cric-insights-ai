"""
Structured result types — no more checking if a string starts with '❌'.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolResult:
    """Result from a single MCP tool call."""

    tool_name: str
    data: str  # Markdown/text content for LLM context
    source: str = ""  # e.g. "Cricsheet RAG", "Live Score", "Google Search"
    tokens_estimate: int = 0
    cached: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.data.strip())


@dataclass
class AskResult:
    """Final result returned to the frontend from the MCP orchestrator."""

    answer: str
    intent: str = "general"
    players: list[str] = field(default_factory=list)
    mode: str = "direct"
    data_sources: list[str] = field(default_factory=list)
    latency_ms: int = 0
    rag_cache_hit: bool = False
    tools_used: list[str] = field(default_factory=list)
    error: Optional[str] = None
