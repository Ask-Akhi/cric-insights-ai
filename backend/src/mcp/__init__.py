"""
MCP (Model Context Protocol) integration layer.

Provides:
  - servers/          → Tool providers (cricsheet, live, search)
  - client.py         → Tool discovery and routing
  - orchestrator.py   → Full ask pipeline (intent → tools → context → LLM)
  - context_assembler.py → Merges tool results into LLM context
"""
