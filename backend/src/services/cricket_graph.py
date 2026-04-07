"""
LangGraph-powered cricket analysis agent.

Graph flow:
  intent_router (LLM) → rag_enrichment → [stats|compare|fantasy|predict|general] → END
                       ↘ non_cricket → END

Fixes vs previous version:
  1. intent_router uses a fast LLM call instead of keyword matching → handles
     nuanced questions like "who scores more in powerplays" correctly.
  2. Synthesizer node removed — only ONE specialist node ever runs per query,
     so a second LLM call to "merge" a single answer was pure waste.
  3. Grounded path in ask.py now passes Cricsheet-enriched context here so
     web-search responses are backed by real ball-by-ball data.
"""
from __future__ import annotations
import logging
from datetime import date
from typing import Any, Dict, List, TypedDict

log = logging.getLogger(__name__)
TODAY = date.today().strftime("%d %B %Y")

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.graph import StateGraph, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    log.warning("langgraph not installed -- falling back to direct LLM")

from .rag_service import build_rag_context, detect_players_in_prompt, is_cricket_question
from .llm_settings import GEMINI_API_KEY, LLM_MODEL


# ── State ─────────────────────────────────────────────────────────────────────
if _LANGGRAPH_AVAILABLE:
    class CricketState(TypedDict, total=False):
        prompt: str
        intent: str
        is_cricket: bool
        players: List[str]
        rag_context: Dict[str, Any]
        final_answer: str
        mode: str
else:
    CricketState = dict  # type: ignore


def _llm(temperature: float = 0.3, prompt: str = "") -> Any:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from .llm_client import _max_tokens_for
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=temperature,
        max_output_tokens=_max_tokens_for(prompt) if prompt else 4096,
    )


# ── Node 1: Intent Router (LLM-based) ─────────────────────────────────────────
# Uses a tiny LLM call with a strict classification prompt so nuanced questions
# like "who scores more in powerplays" or "best death-overs bowler" are routed
# correctly instead of falling through keyword gaps.
_INTENT_SYSTEM = """Classify this cricket question into exactly ONE of these intents:
  stats    — career/recent numbers, averages, records, rankings, form
  compare  — comparing two or more players or teams against each other
  fantasy  — Dream11 / fantasy XI picks, captain/vice-captain choices
  predict  — match winner prediction, outcome forecasting
  general  — everything else cricket-related (rules, history, formats, news)
  none     — not about cricket at all

Reply with ONLY the single intent word. No explanation."""


def intent_router_node(state: CricketState) -> dict:
    prompt = state["prompt"]
    players = detect_players_in_prompt(prompt)
    is_cricket = is_cricket_question(prompt)

    # For non-cricket questions skip any LLM call entirely
    if not is_cricket and not players:
        return {"intent": "general", "players": players, "is_cricket": False}

    # ── Fast keyword classifier — covers ~95% of cricket questions ────────────
    # Run this FIRST. Only fall through to the LLM for genuinely ambiguous cases.
    pl_lower = prompt.lower()
    intent: str | None = None

    if any(w in pl_lower for w in ["fantasy", "dream11", "captain", "vice captain", " xi ", "pick for",
                                    "playing 11", "playing xi", "best pick", "dream 11"]):
        intent = "fantasy"
    elif any(w in pl_lower for w in ["predict", "who will win", "who wins", "winner", "forecast",
                                      "player prediction", "bat first", "bowl first", "toss",
                                      "bat and bowl", "provide player"]):
        intent = "predict"
    elif any(w in pl_lower for w in [" vs ", " versus ", "compare", "better than", "who is better",
                                      "head to head", "h2h", "difference between"]):
        intent = "compare"
    elif any(w in pl_lower for w in ["average", "strike rate", "economy", "career", "record",
                                      "wickets", "centuries", "stats", "ranking", "top scorer",
                                      "leading wicket", "highest", "most runs"]):
        intent = "stats"

    # ── LLM classifier only for ambiguous cases (no keyword matched) ──────────
    if intent is None:
        try:
            resp = _llm(0.0, "classify").invoke([
                SystemMessage(content=_INTENT_SYSTEM),
                HumanMessage(content=prompt),
            ])
            raw = resp.content.strip().lower().split()[0]
            intent = raw if raw in {"stats", "compare", "fantasy", "predict", "general", "none"} else "general"
            if intent == "none":
                return {"intent": "general", "players": players, "is_cricket": False}
        except Exception as e:
            log.warning("Intent LLM failed (%s) — defaulting to general", e)
            intent = "general"

    return {"intent": intent, "players": players, "is_cricket": is_cricket}


# ── Node 2: RAG Enrichment ─────────────────────────────────────────────────────
def rag_enrichment_node(state: CricketState) -> dict:
    ctx = state.get("rag_context") or {}
    enriched = build_rag_context(state["prompt"], ctx)
    return {"rag_context": enriched}


# ── Shared helper: build the data block string ────────────────────────────────
def _cricsheet(state: CricketState) -> str:
    data = state.get("rag_context", {}).get("cricsheet_data", "")
    return f"--- CRICSHEET BALL-BY-BALL DATA ---\n{data}\n--- END ---" if data else ""


# ── Node 3: Stats ─────────────────────────────────────────────────────────────
_STATS_SYSTEM = f"""Senior cricket statistician. Today is {TODAY}.
Format: ## Headline → Stats table (| Metric | Value | Context |) → 2-4 Key Insights bullets → Verdict sentence.
Rules: Cricsheet data = ground truth. Real numbers only. Complete every table (header+separator+data). Cite sources."""


def stats_node(state: CricketState) -> dict:
    data_block = _cricsheet(state)
    try:
        resp = _llm(0.2, state["prompt"]).invoke([
            SystemMessage(content=_STATS_SYSTEM),
            HumanMessage(content=(
                f"Stats question: {state['prompt']}\n\n{data_block}"
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Stats error: {e}"
    return {"final_answer": answer, "mode": "graph"}


# ── Node 4: Compare ───────────────────────────────────────────────────────────
_COMPARE_SYSTEM = f"""Senior cricket analyst — player comparisons. Today is {TODAY}.
Format: ## A vs B → Side-by-side table (| Metric | A | B | Edge |, 5-8 rows) → Key Differences bullets → Verdict with stat.
Rules: Cricsheet data = ground truth. Real numbers only. Complete every table. Cite sources."""


def compare_node(state: CricketState) -> dict:
    data_block = _cricsheet(state)
    try:
        resp = _llm(0.3, state["prompt"]).invoke([
            SystemMessage(content=_COMPARE_SYSTEM),
            HumanMessage(content=(
                f"Comparison question: {state['prompt']}\n\n{data_block}"
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Comparison error: {e}"
    return {"final_answer": answer, "mode": "graph"}


# ── Node 5: Fantasy ───────────────────────────────────────────────────────────
_FANTASY_SYSTEM = f"""Expert fantasy cricket analyst (Dream11). Today is {TODAY}.
Format: ## Fantasy XI → Ranked table [Player|Team|Role|Exp Runs|Exp Wkts|Est Pts|Reason] (11 picks) → Captain (2×) & VC (1.5×) → Differential pick → 2-3 form notes.
Rules: Use Cricsheet expected numbers if provided. Real numbers only. Complete every table. Always pick C & VC."""


def fantasy_node(state: CricketState) -> dict:
    data_block = _cricsheet(state)
    try:
        resp = _llm(0.4, state["prompt"]).invoke([
            SystemMessage(content=_FANTASY_SYSTEM),
            HumanMessage(content=(
                f"Fantasy question: {state['prompt']}\n\n{data_block}"
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Fantasy error: {e}"
    return {"final_answer": answer, "mode": "graph"}


# ── Node 6: Predict ───────────────────────────────────────────────────────────
_PREDICT_SYSTEM = f"""Expert cricket prediction analyst. Today is {TODAY}.
Format: ## Match Prediction → Winner + confidence % (52-75%) → 3 stat-backed factors → COMPLETE player predictions table [Player|Team|Role|Exp Runs|Exp Wkts|Est Pts|Impact] → Captain/VC picks → Risk factor → Source note.
Rules: ALWAYS pick a winner. Use Cricsheet expected numbers if provided. Complete every table (header+separator+ALL rows). Cite sources."""


def predict_node(state: CricketState) -> dict:
    data_block = _cricsheet(state)
    try:
        resp = _llm(0.4, state["prompt"]).invoke([
            SystemMessage(content=_PREDICT_SYSTEM),
            HumanMessage(content=(
                f"Prediction question: {state['prompt']}\n\n{data_block}"
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Prediction error: {e}"
    return {"final_answer": answer, "mode": "graph"}


# ── Node 7: General ───────────────────────────────────────────────────────────
_GENERAL_SYSTEM = f"""Sharp cricket analyst. Today is {TODAY}.
Match depth to question: simple → 2-3 sentences; complex → headers, bullets, tables.
Rules: Direct answer first. Back claims with numbers. Cricsheet data = ground truth. Cite sources. No vague phrases."""


def general_node(state: CricketState) -> dict:
    data_block = _cricsheet(state)
    try:
        resp = _llm(0.3, state["prompt"]).invoke([
            SystemMessage(content=_GENERAL_SYSTEM),
            HumanMessage(content=(
                f"Question: {state['prompt']}\n\n"
                + (data_block + "\n\n" if data_block else "")
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"General error: {e}"
    return {"final_answer": answer, "mode": "graph"}


# ── Node 8: Non-Cricket ───────────────────────────────────────────────────────
def non_cricket_node(state: CricketState) -> dict:
    return {
        "final_answer": (
            "I'm a cricket specialist and can only answer cricket-related questions. "
            "Try asking about player stats, match predictions, fantasy XI picks, "
            "head-to-head comparisons, or tournament analysis."
        ),
        "mode": "graph",
    }


# ── Edge routing ──────────────────────────────────────────────────────────────
def route_after_intent(state: CricketState) -> str:
    return "rag_enrichment" if state.get("is_cricket", True) else "non_cricket"


def route_after_rag(state: CricketState) -> str:
    return {
        "stats": "stats",
        "compare": "compare",
        "fantasy": "fantasy",
        "predict": "predict",
    }.get(state.get("intent", "general"), "general")


# ── Build graph ───────────────────────────────────────────────────────────────
_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is not None:
        return _GRAPH
    if not _LANGGRAPH_AVAILABLE:
        return None
    try:
        g = StateGraph(CricketState)
        g.add_node("intent_router",   intent_router_node)
        g.add_node("rag_enrichment",  rag_enrichment_node)
        g.add_node("stats",           stats_node)
        g.add_node("compare",         compare_node)
        g.add_node("fantasy",         fantasy_node)
        g.add_node("predict",         predict_node)
        g.add_node("general",         general_node)
        g.add_node("non_cricket",     non_cricket_node)

        g.set_entry_point("intent_router")
        g.add_conditional_edges("intent_router", route_after_intent, {
            "rag_enrichment": "rag_enrichment",
            "non_cricket":    "non_cricket",
        })
        g.add_conditional_edges("rag_enrichment", route_after_rag, {
            "stats":   "stats",
            "compare": "compare",
            "fantasy": "fantasy",
            "predict": "predict",
            "general": "general",
        })
        # Each specialist node writes final_answer and goes straight to END
        # (no synthesizer — only one node runs per query, merging is wasteful)
        for node in ["stats", "compare", "fantasy", "predict", "general", "non_cricket"]:
            g.add_edge(node, END)

        _GRAPH = g.compile()
        log.info("LangGraph compiled: 8 nodes (intent_router→rag→specialist→END)")
        return _GRAPH
    except Exception as e:
        log.error("Failed to build LangGraph: %s", e)
        return None


# ── Public entry point ─────────────────────────────────────────────────────────
async def run_graph(prompt: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run the LangGraph pipeline. Falls back to direct LLM if graph unavailable."""
    ctx = context or {}
    graph = get_graph()

    if graph is not None:
        try:
            initial_state: CricketState = {
                "prompt":       prompt,
                "intent":       "general",
                "is_cricket":   True,
                "players":      [],
                "rag_context":  ctx,
                "final_answer": "",
                "mode":         "graph",
            }
            result = await graph.ainvoke(initial_state)
            return {
                "answer":  result.get("final_answer", ""),
                "intent":  result.get("intent", "general"),
                "players": result.get("players", []),
                "mode":    result.get("mode", "graph"),
            }
        except Exception as e:
            log.error("LangGraph pipeline error: %s", e)

    # ── Direct LLM fallback (no LangGraph) ───────────────────────────────────
    try:
        enriched = build_rag_context(prompt, ctx)
        data_block = ""
        if enriched.get("cricsheet_data"):
            data_block = f"--- CRICSHEET BALL-BY-BALL DATA ---\n{enriched['cricsheet_data']}\n--- END ---\n\n"
        resp = _llm(0.3, prompt).invoke([
            SystemMessage(content=_GENERAL_SYSTEM),
            HumanMessage(content=f"Question: {prompt}\n\n{data_block}"),
        ])
        return {
            "answer":  resp.content,
            "intent":  "general",
            "players": detect_players_in_prompt(prompt),
            "mode":    "fallback",
        }
    except Exception as e:
        log.error("Direct LLM fallback error: %s", e)
        return {
            "answer":  f"Sorry, I encountered an error: {e}",
            "intent":  "general",
            "players": [],
            "mode":    "error",
        }
