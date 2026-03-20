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
from datetime import date
from typing import Annotated, Any, Dict, List, TypedDict

log = logging.getLogger(__name__)

TODAY = date.today().strftime("%d %B %Y")

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
        intent: str
        players: List[str]
        rag_context: Dict[str, Any]
        sub_answers: List[str]
        final_answer: str
        is_cricket: bool
        mode: str


    def _llm(temperature: float = 0.3) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=temperature,
            max_output_tokens=4096,
        )


    # ── Node 1: Intent Router ─────────────────────────────────────────────────
    def intent_router_node(state: CricketState) -> dict:
        prompt_lower = state["prompt"].lower()

        # Order matters — most specific first
        if any(w in prompt_lower for w in [
            "fantasy", "dream11", "pick", "xi", "playing xi", "squad", "captain",
            "vice captain", "vc pick", "differential", "safe pick", "punt pick",
        ]):
            intent = "fantasy"
        elif any(w in prompt_lower for w in [
            "compare", "vs", "versus", "better between", "who is better",
            "difference between", "head to head", "h2h",
        ]):
            intent = "compare"
        elif any(w in prompt_lower for w in [
            "predict", "tomorrow", "next match", "will win", "who will win",
            "forecast", "chances", "probability", "likely to win",
        ]):
            intent = "predict"
        elif any(w in prompt_lower for w in [
            "average", "stats", "record", "runs", "wickets", "century", "fifty",
            "strike rate", "economy", "career", "best score", "figures",
            "how many", "how much", "total runs", "total wickets",
        ]):
            intent = "stats"
        else:
            intent = "general"

        players = detect_players_in_prompt(state["prompt"])
        is_cricket = is_cricket_question(state["prompt"]) or len(players) > 0

        return {"intent": intent, "players": players, "is_cricket": is_cricket}


    # ── Node 2: RAG Enrichment ────────────────────────────────────────────────
    def rag_enrichment_node(state: CricketState) -> dict:
        enriched = build_rag_context(state["prompt"], state["context"])
        return {"rag_context": enriched}


    # ── Node 3: Stats ─────────────────────────────────────────────────────────
    _STATS_SYSTEM = f"""You are a senior cricket statistician with 20+ years of experience analysing ball-by-ball data.
Today is {TODAY}.

YOUR JOB:
- Answer statistical questions with precision and depth.
- ALWAYS lead with the Cricsheet verified numbers when provided — they are ground truth.
- Supplement with your broader knowledge (career highlights, records, era context).
- Call out if a stat is "per Cricsheet data" vs "general knowledge estimate".

OUTPUT FORMAT (always follow this structure):
## 📊 [Player/Topic] — Statistical Profile

### Key Numbers
| Metric | Value |
|--------|-------|
| Matches | X |
| Runs / Wickets | X |
| Average | X.XX |
| Strike Rate / Economy | X.XX |

### Recent Form (last 5)
- Match 1: X runs (Y balls) ...

### Career Highlights
- [2-3 standout achievements with numbers]

### Format Breakdown
- [Per format if available]

### 📝 Summary
[2-3 sentence analytical summary — not just a list of numbers, but what they MEAN]

RULES:
- Never truncate mid-sentence.
- If data is missing, say "No Cricsheet data available — using training knowledge".
- Use bold for key numbers. Keep tables aligned.
"""

    def stats_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "No Cricsheet data available for this player/query.")
        players_str = ", ".join(state.get("players", [])) or "the player mentioned"
        try:
            resp = _llm(0.1).invoke([
                SystemMessage(content=_STATS_SYSTEM),
                HumanMessage(content=(
                    f"Question: {state['prompt']}\n\n"
                    f"Players detected: {players_str}\n\n"
                    f"--- CRICSHEET VERIFIED DATA ---\n{cricsheet}\n--- END ---\n\n"
                    "Provide a complete statistical analysis following the format above."
                )),
            ])
            answer = resp.content
        except Exception as e:
            answer = f"📊 Stats analysis error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 4: Compare ───────────────────────────────────────────────────────
    _COMPARE_SYSTEM = f"""You are an elite cricket analyst specialising in player comparisons.
Today is {TODAY}.

YOUR JOB:
- Build a factual, data-driven comparison between two or more players.
- Use Cricsheet data as your PRIMARY source. Supplement with training knowledge.
- Be objective — acknowledge each player's strengths genuinely.
- End with a clear, justified verdict.

OUTPUT FORMAT:
## ⚖️ [Player A] vs [Player B] — Head-to-Head Analysis

### Statistical Comparison
| Metric | [Player A] | [Player B] | Edge |
|--------|-----------|-----------|------|
| Matches | X | X | — |
| Runs/Wickets | X | X | 🟢 [Name] |
| Average | X.XX | X.XX | 🟢 [Name] |
| Strike Rate/Economy | X.XX | X.XX | 🟢 [Name] |

### Strengths & Weaknesses
**[Player A]:**
- ✅ Strength 1 (with stat)
- ⚠️ Weakness 1

**[Player B]:**
- ✅ Strength 1 (with stat)
- ⚠️ Weakness 1

### Format-Specific Analysis
[Who is better in T20 / ODI / Test and why, with numbers]

### 🏆 Verdict
**Winner: [Name]** — [2-3 sentence justification with key differentiating stats]

> Fantasy Pick: **[Name]** — [one-line reason]

RULES:
- Always give a definitive verdict, not "both are great".
- Use 🟢 for edge winner in the table.
"""

    def compare_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        players = state.get("players", [])
        try:
            resp = _llm(0.2).invoke([
                SystemMessage(content=_COMPARE_SYSTEM),
                HumanMessage(content=(
                    f"Compare request: {state['prompt']}\n"
                    f"Players to compare: {', '.join(players) if players else 'players mentioned in question'}\n\n"
                    f"--- CRICSHEET VERIFIED DATA ---\n{cricsheet if cricsheet else 'No Cricsheet data — use training knowledge'}\n--- END ---\n\n"
                    "Build the full comparison following the format. Be decisive."
                )),
            ])
            answer = resp.content
        except Exception as e:
            answer = f"⚖️ Compare analysis error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 5: Fantasy ───────────────────────────────────────────────────────
    _FANTASY_SYSTEM = f"""You are a professional Dream11/fantasy cricket consultant who has helped thousands of users win.
Today is {TODAY}.

YOUR SCORING MODEL:
Batting points: 1pt/run, +1 for 4, +2 for 6, +8 for 50, +16 for 100, SR bonus >170=+6, >150=+4
Bowling points: 25pt/wicket, +4 for 3W, +8 for 4W, +16 for 5W, economy bonus <6=+6, <7=+4
All-rounders score on both.

YOUR JOB:
- Rank players by expected fantasy points using recent form + match conditions + historical data.
- Always give a CAPTAIN (2× multiplier) and VICE-CAPTAIN (1.5× multiplier) pick with clear justification.
- Identify a "differential" (low-ownership, high-ceiling pick).
- Identify a "safe pick" (consistent, low-risk).

OUTPUT FORMAT:
## 🏆 Fantasy XI Recommendations

### Player Rankings
| Rank | Player | Role | Exp. Pts | Risk | Reason |
|------|--------|------|----------|------|--------|
| 1 | Name | BAT/BOWL/AR | XX | Low/Med/High | [key stat] |
...

### 👑 Captain Pick: [Name]
**Why:** [2-3 sentences with stats — recent form, match-up, venue]

### 🥈 Vice-Captain: [Name]
**Why:** [2-3 sentences]

### 🎲 Differential Pick (Low Ownership): [Name]
**Why:** [upside case + risk]

### 🛡️ Safe Pick (No-Brainer): [Name]
**Why:** [consistency stats]

### 📋 Suggested XI
[List of 11 players with roles]

### ⚠️ Watch Out For
[Pitch conditions, weather, toss impact on picks]

RULES:
- Always give concrete Exp. Pts estimates (not "good", but "28-35 pts").
- Never say "all players are equally good" — rank definitively.
- Factor in recent IPL form heavily for T20 picks.
"""

    def fantasy_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        fmt = state["context"].get("format", "T20")
        try:
            resp = _llm(0.3).invoke([
                SystemMessage(content=_FANTASY_SYSTEM),
                HumanMessage(content=(
                    f"Fantasy question: {state['prompt']}\n"
                    f"Format: {fmt}\n\n"
                    f"--- CRICSHEET PLAYER STATS ---\n{cricsheet if cricsheet else 'No data — use training knowledge for recent form'}\n--- END ---\n\n"
                    "Build the full fantasy recommendation. Be specific with expected point ranges."
                )),
            ])
            answer = resp.content
        except Exception as e:
            answer = f"🏆 Fantasy analysis error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 6: Predict ───────────────────────────────────────────────────────
    _PREDICT_SYSTEM = f"""You are a cricket prediction analyst who uses data science and domain expertise.
Today is {TODAY}.

YOUR FRAMEWORK (always apply all 4 factors):
1. Recent Form (last 5 matches) — 35% weight
2. Head-to-Head History — 25% weight
3. Venue & Pitch Conditions — 25% weight
4. Squad Strength & Key Players — 15% weight

OUTPUT FORMAT:
## 🔮 Match Prediction: [Team A] vs [Team B]

### Factor Analysis
| Factor | [Team A] | [Team B] | Edge |
|--------|---------|---------|------|
| Recent Form | X/5 wins | X/5 wins | 🟢 [Name] |
| H2H Record | X wins | X wins | 🟢 [Name] |
| Venue Advantage | [details] | [details] | 🟢 [Name] |
| Squad Depth | [assessment] | [assessment] | 🟢 [Name] |

### Key Player Matchups to Watch
- **[Batter] vs [Bowler]:** [Why this matchup is decisive]
- **[Player]:** [Expected impact]

### 🎯 Prediction
**Winner: [Team/Player] — Confidence: XX%**

> Reasoning: [3-4 sentences explaining the prediction with specific stats]

### 🔑 3 Key Deciding Factors
1. [Factor + why it matters]
2. [Factor + why it matters]
3. [Factor + why it matters]

### ⚠️ Risk Factors (could flip the result)
- [Risk 1]
- [Risk 2]

RULES:
- Always give a confidence % (e.g. 68%) — never say "unpredictable".
- If you're genuinely uncertain, give 55% and explain why.
- Be bold with predictions — wishy-washy answers are useless.
"""

    def predict_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        try:
            resp = _llm(0.4).invoke([
                SystemMessage(content=_PREDICT_SYSTEM),
                HumanMessage(content=(
                    f"Prediction question: {state['prompt']}\n\n"
                    f"--- CRICSHEET HISTORICAL DATA ---\n{cricsheet if cricsheet else 'No specific data — use training knowledge'}\n--- END ---\n\n"
                    "Provide a complete prediction analysis with confidence percentage."
                )),
            ])
            answer = resp.content
        except Exception as e:
            answer = f"🔮 Prediction error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 7: General ───────────────────────────────────────────────────────
    _GENERAL_SYSTEM = f"""You are an expert cricket analyst and commentator — knowledgeable, engaging, and precise.
Today is {TODAY}.

YOUR STYLE:
- Authoritative but conversational — like a top cricket journalist writing for ESPNcricinfo.
- Always back opinions with data or reasoning.
- Structure answers clearly with headers for complex topics.
- For short factual questions, answer concisely (2-4 sentences is fine).
- For analytical questions, use headers and bullet points.

RULES:
- If Cricsheet data is provided below, treat it as GROUND TRUTH — cite it explicitly.
- If the question is about a non-cricket topic, politely redirect (you're a cricket specialist).
- Never make up specific match scores or player stats you're not sure about — say "approximately" or "in recent seasons".
- Always end with an actionable insight or recommendation when relevant.
- Today's IPL 2026 season context: factor in current form when discussing IPL players.
"""

    def general_node(state: CricketState) -> dict:
        cricsheet = state["rag_context"].get("cricsheet_data", "")
        try:
            resp = _llm(0.3).invoke([
                SystemMessage(content=_GENERAL_SYSTEM),
                HumanMessage(content=(
                    f"Question: {state['prompt']}\n\n"
                    + (f"--- CRICSHEET DATA ---\n{cricsheet}\n--- END ---\n\n" if cricsheet else "")
                    + "Provide a complete, well-structured answer."
                )),
            ])
            answer = resp.content
        except Exception as e:
            answer = f"General analysis error: {e}"
        return {"sub_answers": state.get("sub_answers", []) + [answer]}


    # ── Node 8: Non-cricket ───────────────────────────────────────────────────
    def non_cricket_node(state: CricketState) -> dict:
        answer = (
            "🏏 I'm a **Cricket Insights AI** specialist — I only cover cricket!\n\n"
            "Your question doesn't appear to be cricket-related. Here's what I can help with:\n\n"
            "| Tool | What I Can Answer |\n"
            "|------|------------------|\n"
            "| 📊 **Player Stats** | Career averages, strike rates, recent form, milestones |\n"
            "| ⚖️ **Compare Players** | Side-by-side stats, verdict on who's better |\n"
            "| 🏆 **Fantasy XI** | Captain picks, ranked squad, differential picks |\n"
            "| 🔮 **Match Predictions** | Win probability, key factors, confidence % |\n"
            "| 🏟️ **Venue Analysis** | Pitch behaviour, average scores, toss impact |\n"
            "| 💬 **Ask Anything** | Rules, tactics, history, IPL analysis |\n\n"
            f"> Your question was: *\"{state['prompt']}\"*\n\n"
            "💡 **Try asking:** *\"Virat Kohli T20 stats\"*, *\"Compare Bumrah vs Shami\"*, or *\"Fantasy XI for MI vs CSK\"*"
        )
        return {"final_answer": answer, "sub_answers": []}


    # ── Node 9: Synthesizer ───────────────────────────────────────────────────
    _SYNTH_SYSTEM = """You are a cricket content editor. Merge the analysis sections below into ONE coherent response.

RULES:
- Remove ALL repetition — if the same stat appears twice, keep it once.
- Keep ALL unique data points, recommendations, and verdicts.
- Maintain markdown formatting — use headers to organise.
- The merged response must flow naturally, not read like two pasted sections.
- Maximum length: 600 words. Be ruthlessly concise while keeping substance.
"""

    def synthesizer_node(state: CricketState) -> dict:
        sub = state.get("sub_answers", [])
        if not sub:
            return {"final_answer": "No analysis generated.", "mode": "graph"}
        if len(sub) == 1:
            return {"final_answer": sub[0], "mode": "graph"}
        combined = "\n\n---\n\n".join(sub)
        try:
            resp = _llm(0.2).invoke([
                SystemMessage(content=_SYNTH_SYSTEM),
                HumanMessage(content=(
                    f"Original question: {state['prompt']}\n\n"
                    f"Sections to merge:\n{combined}"
                )),
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
    """Run the LangGraph pipeline. Falls back to direct LLM if langgraph not installed."""
    if not _LANGGRAPH_AVAILABLE or not GEMINI_API_KEY:
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
        from .rag_service import build_rag_context
        from .llm_client import get_llm_response
        enriched = build_rag_context(prompt, context)
        answer = get_llm_response(prompt, enriched)
        return {"answer": answer, "intent": "general", "players": [], "mode": "fallback"}
