"""
LangGraph-powered cricket analysis agent.

Graph flow:
  intent_router → rag_enrichment → [stats | compare | fantasy | predict | general]
                                 → synthesizer → END
  intent_router → non_cricket → END
"""
from __future__ import annotations
import os
import logging
from typing import Annotated, Any, Dict, List, TypedDict

log = logging.getLogger(__name__)

# ── LangGraph / LangChain imports (graceful fallback if not installed) ────────
try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.graph import StateGraph, END
    from langgraph.graph.message import add_messages
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    log.warning("langgraph/langchain not installed — graph pipeline disabled, falling back to direct LLM")

from .rag_service import build_rag_context, detect_players_in_prompt, is_cricket_question
from .llm_settings import GEMINI_API_KEY, LLM_MODEL


# ── Shared graph state ────────────────────────────────────────────────────────
if _LANGGRAPH_AVAILABLE:
    class CricketState(TypedDict):
        messages: Annotated[List, add_messages]
        prompt: str
        context: Dict[str, Any]
        intent: str          # stats | compare | fantasy | predict | general
        players: List[str]
        rag_context: Dict[str, Any]
        sub_answers: List[str]
        final_answer: str
        is_cricket: bool
        mode: str            # "graph" — surfaced to API response


    # ── LLM factory ───────────────────────────────────────────────────────────
    def _llm(temperature: float = 0.3) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=temperature,
            max_output_tokens=4096,
        )


    # ── Node 1: Intent Router ─────────────────────────────────────────────────
    def intent_router_node(state: CricketState) -> dict:
        prompt = state["prompt"].lower()
        if any(w in prompt for w in ["fantasy", "pick", "xi", "squad", "captain", "differential"]):
            intent = "fantasy"
        elif any(w in prompt for w in ["compare", "vs", "versus", "better between", "who is better"]):
            intent = "compare"
        elif any(w in prompt for w in ["predict", "tomorrow", "next match", "will win", "who will", "forecast"]):
            intent = "predict"
        elif any(w in prompt for w in ["average", "stats", "record", "runs", "wickets", "century", "fifty", "strike rate", "economy"]):
            intent = "stats"
        else:
            intent = "general"

        players = detect_players_in_prompt(state["prompt"])
        is_cricket = is_cricket_question(state["prompt"]) or len(players) > 0

        return {
            "intent": intent,
            "players": players,
            "is_cricket": is_cricket,
        }


    # ── Node 2: RAG Enrichment ────────────────────────────────────────────────
    def rag_enrichment_node(state: CricketState) -> dict:
        enriched = build_rag_context(state["prompt"], state["context"])
        return {"rag_context": enriched}


    # ── Node 3: Stats ─────────────────────────────────────────────────────────
    def stats_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "No Cricsheet data available.")
        try:
            resp = _llm(0.1).invoke([
                SystemMessage(content=(
                    "You are a cricket statistics expert. Analyse the Cricsheet data provided "
                    "and give precise, data-driven insights. Always cite specific numbers. "
                    "Use bullet points. Be thorough but concise."
                )),
                HumanMessage(content=(
                    f"Question: {state['prompt']}\n\n"
                    f"Cricsheet verified data:\n{cricsheet}\n\n"
                    "Provide detailed statistical analysis."
                )),
            ])
            answer = f"📊 **Stats Analysis**\n\n{resp.content}"
        except Exception as e:
            answer = f"📊 Stats node error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 4: Compare ───────────────────────────────────────────────────────
    def compare_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        players = state.get("players", [])
        try:
            resp = _llm(0.2).invoke([
                SystemMessage(content=(
                    "You are a cricket analyst specialising in player comparisons. "
                    "Use verified Cricsheet data to build a factual side-by-side table. "
                    "End with a clear verdict on who performs better and in what conditions."
                )),
                HumanMessage(content=(
                    f"Compare: {', '.join(players) if players else 'the players mentioned'}\n"
                    f"Question: {state['prompt']}\n"
                    f"Cricsheet data:\n{cricsheet}\n\n"
                    "Format: markdown table + 2-3 bullet verdict points."
                )),
            ])
            answer = f"⚖️ **Player Comparison**\n\n{resp.content}"
        except Exception as e:
            answer = f"⚖️ Compare node error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 5: Fantasy ───────────────────────────────────────────────────────
    def fantasy_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        try:
            resp = _llm(0.3).invoke([
                SystemMessage(content=(
                    "You are a fantasy cricket expert. Score players on:\n"
                    "• Recent form 40% • Match conditions 30% • Historical stats 20% • Value 10%\n"
                    "Always recommend a CAPTAIN pick and VICE-CAPTAIN pick with clear reasoning."
                )),
                HumanMessage(content=(
                    f"Fantasy question: {state['prompt']}\n"
                    f"Player stats:\n{cricsheet}\n\n"
                    "Format: ranked list with scores, then C/VC recommendation + rationale."
                )),
            ])
            answer = f"🏆 **Fantasy Recommendation**\n\n{resp.content}"
        except Exception as e:
            answer = f"🏆 Fantasy node error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 6: Predict ───────────────────────────────────────────────────────
    def predict_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        try:
            resp = _llm(0.4).invoke([
                SystemMessage(content=(
                    "You are a cricket prediction expert. "
                    "Base predictions on historical data, current form and match conditions. "
                    "Always give a confidence percentage (e.g. 65%) and list the 3 key deciding factors."
                )),
                HumanMessage(content=(
                    f"Predict: {state['prompt']}\n"
                    f"Historical data:\n{cricsheet}\n\n"
                    "Format: Prediction + Confidence % + 3 key factors + risk factors."
                )),
            ])
            answer = f"🔮 **Prediction**\n\n{resp.content}"
        except Exception as e:
            answer = f"🔮 Predict node error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 7: General ───────────────────────────────────────────────────────
    def general_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        today = __import__("datetime").date.today().strftime("%d %B %Y")
        try:
            resp = _llm(0.3).invoke([
                SystemMessage(content=(
                    f"You are an expert cricket analyst. Today is {today}. "
                    "Give complete, well-structured answers with relevant stats and context. "
                    "If Cricsheet data is provided, use it as your primary source."
                )),
                HumanMessage(content=(
                    f"Question: {state['prompt']}\n"
                    + (f"\nCricsheet data:\n{cricsheet}" if cricsheet else "")
                )),
            ])
            answer = resp.content
        except Exception as e:
            answer = f"General node error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 8: Non-cricket ───────────────────────────────────────────────────
    def non_cricket_node(state: CricketState) -> dict:
        answer = (
            "🏏 I'm a **Cricket Insights AI** specialist.\n\n"
            "Your question doesn't appear to be cricket-related. I can help with:\n\n"
            "- 📊 **Player stats** — batting/bowling averages, strike rates, form\n"
            "- ⚖️ **Player comparisons** — head-to-head across formats\n"
            "- 🏆 **Fantasy XI** — captain picks, value differentials\n"
            "- 🔮 **Match predictions** — form-based forecasts with confidence %\n"
            "- 🏟️ **Venue & tactic analysis** — pitch conditions, team strategies\n\n"
            f"> Your question: *\"{state['prompt']}\"*\n\n"
            "Try asking about a cricketer or match! 🏟️"
        )
        return {"final_answer": answer, "sub_answers": []}


    # ── Node 9: Synthesizer ───────────────────────────────────────────────────
    def synthesizer_node(state: CricketState) -> dict:
        sub = state.get("sub_answers", [])
        if not sub:
            return {"final_answer": "No analysis generated.", "mode": "graph"}
        if len(sub) == 1:
            return {"final_answer": sub[0], "mode": "graph"}
        # Multiple sections — merge them cleanly
        combined = "\n\n---\n\n".join(sub)
        try:
            resp = _llm(0.2).invoke([
                SystemMessage(content=(
                    "Merge these cricket analysis sections into one coherent, well-structured response. "
                    "Remove repetition. Keep all key data points and recommendations. "
                    "Use markdown headers to organise."
                )),
                HumanMessage(content=f"Original question: {state['prompt']}\n\n{combined}"),
            ])
            return {"final_answer": resp.content, "mode": "graph"}
        except Exception:
            return {"final_answer": combined, "mode": "graph"}


    # ── Routing functions ─────────────────────────────────────────────────────
    def _route_after_router(state: CricketState) -> str:
        return "rag_enrichment" if state["is_cricket"] else "non_cricket"

    def _route_after_rag(state: CricketState) -> str:
        return {
            "stats":   "stats",
            "compare": "compare",
            "fantasy": "fantasy",
            "predict": "predict",
        }.get(state["intent"], "general")


    # ── Build & compile the graph ─────────────────────────────────────────────
    def _build_graph():
        g = StateGraph(CricketState)

        g.add_node("intent_router",  intent_router_node)
        g.add_node("rag_enrichment", rag_enrichment_node)
        g.add_node("stats",          stats_node)
        g.add_node("compare",        compare_node)
        g.add_node("fantasy",        fantasy_node)
        g.add_node("predict",        predict_node)
        g.add_node("general",        general_node)
        g.add_node("non_cricket",    non_cricket_node)
        g.add_node("synthesizer",    synthesizer_node)

        g.set_entry_point("intent_router")

        g.add_conditional_edges(
            "intent_router",
            _route_after_router,
            {"rag_enrichment": "rag_enrichment", "non_cricket": "non_cricket"},
        )
        g.add_conditional_edges(
            "rag_enrichment",
            _route_after_rag,
            {"stats": "stats", "compare": "compare",
             "fantasy": "fantasy", "predict": "predict", "general": "general"},
        )
        for node in ["stats", "compare", "fantasy", "predict", "general"]:
            g.add_edge(node, "synthesizer")
        g.add_edge("synthesizer", END)
        g.add_edge("non_cricket", END)

        return g.compile()

    _GRAPH = None

    def _get_graph():
        global _GRAPH
        if _GRAPH is None:
            _GRAPH = _build_graph()
        return _GRAPH


# ── Public API ────────────────────────────────────────────────────────────────
async def run_graph(prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the LangGraph pipeline.
    Returns dict with keys: answer, intent, players, mode
    Falls back to direct RAG+LLM if langgraph not installed.
    """
    if not _LANGGRAPH_AVAILABLE or not GEMINI_API_KEY:
        # Graceful fallback — use existing direct pipeline
        from .rag_service import build_rag_context
        from .llm_client import get_llm_response
        enriched = build_rag_context(prompt, context)
        answer = get_llm_response(prompt, enriched)
        return {"answer": answer, "intent": "general", "players": [], "mode": "direct"}

    initial: CricketState = {
        "messages":     [HumanMessage(content=prompt)],
        "prompt":       prompt,
        "context":      context,
        "intent":       "general",
        "players":      [],
        "rag_context":  {},
        "sub_answers":  [],
        "final_answer": "",
        "is_cricket":   True,
        "mode":         "graph",
    }

    try:
        result = await _get_graph().ainvoke(initial)
        answer = result.get("final_answer", "")
        if not answer or answer.strip() == "":
            answer = (
                "🏏 I couldn't generate a complete answer. "
                "Try asking about a specific player, match, or fantasy team."
            )
        return {
            "answer":  answer,
            "intent":  result.get("intent", "general"),
            "players": result.get("players", []),
            "mode":    result.get("mode", "graph"),
        }
    except Exception as e:
        log.error(f"LangGraph pipeline error: {e}")
        # Fallback to direct LLM on any graph error
        from .rag_service import build_rag_context
        from .llm_client import get_llm_response
        enriched = build_rag_context(prompt, context)
        answer = get_llm_response(prompt, enriched)
        return {"answer": answer, "intent": "general", "players": [], "mode": "fallback"}
