"""
LangGraph-powered cricket analysis agent.
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


# -- State ---------------------------------------------------------------------
if _LANGGRAPH_AVAILABLE:
    class CricketState(TypedDict, total=False):
        prompt: str
        intent: str
        is_cricket: bool
        players: List[str]
        rag_context: Dict[str, Any]
        sub_answers: List[str]
        final_answer: str
        mode: str
else:
    CricketState = dict  # type: ignore


def _llm(temperature: float = 0.3) -> Any:
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        google_api_key=GEMINI_API_KEY,
        temperature=temperature,
        max_output_tokens=512,
    )


# -- Node 1: Intent Router -----------------------------------------------------
def intent_router_node(state: CricketState) -> dict:
    prompt = state["prompt"].lower()
    if any(w in prompt for w in ["vs", "versus", "compare", "better", "who is better"]):
        intent = "compare"
    elif any(w in prompt for w in ["fantasy", "dream11", "pick", "captain", "vice captain", "xi"]):
        intent = "fantasy"
    elif any(w in prompt for w in ["predict", "prediction", "winner", "who will win", "chance", "likely"]):
        intent = "predict"
    elif any(w in prompt for w in ["stat", "average", "run", "wicket", "record", "career", "form", "innings"]):
        intent = "stats"
    else:
        intent = "general"
    players = detect_players_in_prompt(state["prompt"])
    is_cricket = is_cricket_question(state["prompt"])
    return {"intent": intent, "players": players, "is_cricket": is_cricket}


# -- Node 2: RAG Enrichment ----------------------------------------------------
def rag_enrichment_node(state: CricketState) -> dict:
    ctx = state.get("rag_context") or {}
    enriched = build_rag_context(state["prompt"], ctx)
    return {"rag_context": enriched}


# -- Node 3: Stats -------------------------------------------------------------
_STATS_SYSTEM = f"""You are a cricket statistician. Today is {TODAY}.
RULES: Lead with Cricsheet numbers. Max 200 words.
Format:
## [Player] -- Statistical Profile
**Key Numbers:** [inline stats]
**Recent Form:** [last 5 if available]
**Verdict:** [1-2 sentences what the numbers mean]
"""


def stats_node(state: CricketState) -> dict:
    cricsheet = state["rag_context"].get("cricsheet_data", "")
    try:
        resp = _llm(0.2).invoke([
            SystemMessage(content=_STATS_SYSTEM),
            HumanMessage(content=(
                f"Stats question: {state['prompt']}\n\n"
                f"--- CRICSHEET DATA ---\n{cricsheet or 'No data found.'}\n--- END ---\n\n"
                "Statistical analysis in under 200 words."
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Stats error: {e}"
    return {"sub_answers": state.get("sub_answers", []) + [answer]}


# -- Node 4: Compare -----------------------------------------------------------
_COMPARE_SYSTEM = f"""You are a cricket analyst specialising in player comparisons. Today is {TODAY}.
Max 200 words. Use a markdown table then a Verdict sentence.
"""


def compare_node(state: CricketState) -> dict:
    cricsheet = state["rag_context"].get("cricsheet_data", "")
    try:
        resp = _llm(0.3).invoke([
            SystemMessage(content=_COMPARE_SYSTEM),
            HumanMessage(content=(
                f"Comparison: {state['prompt']}\n\n"
                f"--- CRICSHEET DATA ---\n{cricsheet or 'No data'}\n--- END ---\n\n"
                "Head-to-head comparison under 200 words."
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Comparison error: {e}"
    return {"sub_answers": state.get("sub_answers", []) + [answer]}


# -- Node 5: Fantasy -----------------------------------------------------------
_FANTASY_SYSTEM = f"""You are a fantasy cricket expert. Today is {TODAY}.
Max 150 words. Format: Captain, Vice-Captain, Core Picks, Differential, Avoid.
"""


def fantasy_node(state: CricketState) -> dict:
    cricsheet = state["rag_context"].get("cricsheet_data", "")
    try:
        resp = _llm(0.4).invoke([
            SystemMessage(content=_FANTASY_SYSTEM),
            HumanMessage(content=(
                f"Fantasy question: {state['prompt']}\n\n"
                f"--- CRICSHEET DATA ---\n{cricsheet or 'No data'}\n--- END ---\n\n"
                "Fantasy picks under 150 words."
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Fantasy error: {e}"
    return {"sub_answers": state.get("sub_answers", []) + [answer]}


# -- Node 6: Predict -----------------------------------------------------------
_PREDICT_SYSTEM = f"""You are a cricket prediction analyst. Today is {TODAY}.
Max 120 words. Format:
## Prediction: [Subject]
**Winner: [Name] -- Confidence: XX%**
**3 Key Reasons:** 1. ... 2. ... 3. ...
**Risk:** [one sentence]
Always give a concrete winner -- never say "too early to tell".
"""


def predict_node(state: CricketState) -> dict:
    cricsheet = state["rag_context"].get("cricsheet_data", "")
    try:
        resp = _llm(0.4).invoke([
            SystemMessage(content=_PREDICT_SYSTEM),
            HumanMessage(content=(
                f"Prediction: {state['prompt']}\n\n"
                f"--- CRICSHEET DATA ---\n{cricsheet or 'No data'}\n--- END ---\n\n"
                "Direct prediction under 120 words with confidence %."
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"Prediction error: {e}"
    return {"sub_answers": state.get("sub_answers", []) + [answer]}


# -- Node 7: General -----------------------------------------------------------
_GENERAL_SYSTEM = f"""You are a sharp cricket analyst. Today is {TODAY}.
Max 150 words. Lead with the answer immediately. Back every claim with a stat.
Never say "it's hard to predict" -- give your best direct assessment.
"""


def general_node(state: CricketState) -> dict:
    cricsheet = state["rag_context"].get("cricsheet_data", "")
    try:
        resp = _llm(0.3).invoke([
            SystemMessage(content=_GENERAL_SYSTEM),
            HumanMessage(content=(
                f"Question: {state['prompt']}\n\n"
                + (f"--- CRICSHEET DATA ---\n{cricsheet}\n--- END ---\n\n" if cricsheet else "")
                + "Answer in under 150 words."
            )),
        ])
        answer = resp.content
    except Exception as e:
        answer = f"General error: {e}"
    return {"sub_answers": state.get("sub_answers", []) + [answer]}


# -- Node 8: Non-Cricket -------------------------------------------------------
def non_cricket_node(state: CricketState) -> dict:
    return {
        "final_answer": (
            "I'm a cricket specialist and can only answer cricket-related questions. "
            "Try asking about player stats, match predictions, fantasy XI picks, "
            "head-to-head comparisons, or tournament analysis."
        ),
        "sub_answers": [],
    }


# -- Node 9: Synthesizer -------------------------------------------------------
_SYNTH_SYSTEM = """You are a cricket content editor. Merge the sections into ONE response.
Max 200 words. Remove duplicates. Keep all stats, verdicts, recommendations. Clean markdown.
"""


def synthesizer_node(state: CricketState) -> dict:
    sub_answers = state.get("sub_answers", [])
    if not sub_answers:
        return {"final_answer": "No analysis generated.", "mode": "graph"}
    if len(sub_answers) == 1:
        return {"final_answer": sub_answers[0], "mode": "graph"}
    combined = "\n\n---\n\n".join(sub_answers)
    try:
        resp = _llm(0.2).invoke([
            SystemMessage(content=_SYNTH_SYSTEM),
            HumanMessage(content=f"Merge into one response under 200 words:\n\n{combined}"),
        ])
        return {"final_answer": resp.content, "mode": "graph"}
    except Exception:
        return {"final_answer": combined, "mode": "graph"}


# -- Edge routing --------------------------------------------------------------
def route_after_intent(state: CricketState) -> str:
    return "rag_enrichment" if state["is_cricket"] else "non_cricket"


def route_after_rag(state: CricketState) -> str:
    return {"stats": "stats", "compare": "compare", "fantasy": "fantasy", "predict": "predict"}.get(
        state.get("intent", "general"), "general"
    )


# -- Build graph ---------------------------------------------------------------
_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is not None:
        return _GRAPH
    if not _LANGGRAPH_AVAILABLE:
        return None
    try:
        g = StateGraph(CricketState)
        g.add_node("intent_router", intent_router_node)
        g.add_node("rag_enrichment", rag_enrichment_node)
        g.add_node("stats", stats_node)
        g.add_node("compare", compare_node)
        g.add_node("fantasy", fantasy_node)
        g.add_node("predict", predict_node)
        g.add_node("general", general_node)
        g.add_node("non_cricket", non_cricket_node)
        g.add_node("synthesizer", synthesizer_node)
        g.set_entry_point("intent_router")
        g.add_conditional_edges("intent_router", route_after_intent, {
            "rag_enrichment": "rag_enrichment",
            "non_cricket": "non_cricket",
        })
        g.add_conditional_edges("rag_enrichment", route_after_rag, {
            "stats": "stats",
            "compare": "compare",
            "fantasy": "fantasy",
            "predict": "predict",
            "general": "general",
        })
        for node in ["stats", "compare", "fantasy", "predict", "general"]:
            g.add_edge(node, "synthesizer")
        g.add_edge("synthesizer", END)
        g.add_edge("non_cricket", END)
        _GRAPH = g.compile()
        return _GRAPH
    except Exception as e:
        log.error(f"Failed to build LangGraph: {e}")
        return None


# -- Public entry point --------------------------------------------------------
async def run_graph(prompt: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run the LangGraph pipeline. Falls back to direct LLM if graph unavailable."""
    ctx = context or {}
    graph = get_graph()

    if graph is not None:
        try:
            initial_state: CricketState = {
                "prompt": prompt,
                "intent": "general",
                "is_cricket": True,
                "players": [],
                "rag_context": ctx,
                "sub_answers": [],
                "final_answer": "",
                "mode": "graph",
            }
            result = await graph.ainvoke(initial_state)
            return {
                "answer": result.get("final_answer", ""),
                "intent": result.get("intent", "general"),
                "players": result.get("players", []),
                "mode": result.get("mode", "graph"),
            }
        except Exception as e:
            log.error(f"LangGraph pipeline error: {e}")

    # Direct LLM fallback
    try:
        enriched = build_rag_context(prompt, ctx)
        cricsheet = enriched.get("cricsheet_data", "")
        resp = _llm(0.3).invoke([
            SystemMessage(content=_GENERAL_SYSTEM),
            HumanMessage(content=(
                f"Question: {prompt}\n\n"
                + (f"--- CRICSHEET DATA ---\n{cricsheet}\n--- END ---\n\n" if cricsheet else "")
                + "Answer in under 150 words."
            )),
        ])
        return {
            "answer": resp.content,
            "intent": "general",
            "players": detect_players_in_prompt(prompt),
            "mode": "fallback",
        }
    except Exception as e:
        log.error(f"Direct LLM fallback error: {e}")
        return {
            "answer": f"Sorry, I encountered an error: {e}",
            "intent": "general",
            "players": [],
            "mode": "error",
        }
