import streamlit as st
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
# Load .env if present (local dev); in production env vars come from the host/platform
_env_path = os.path.join(os.path.dirname(__file__), "../.env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)

from src.services.llm_client import get_llm_response, get_llm_response_grounded
from src.services.llm_settings import LLM_PROVIDER, LLM_MODEL

# ── Password gate ─────────────────────────────────────────────────────────────
_APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

if _APP_PASSWORD:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.set_page_config(page_title="Cric Insights AI — Login", page_icon="🏏")
        st.title("🏏 Cric Insights AI")
        st.subheader("🔒 Login required")
        pwd = st.text_input("Password", type="password", placeholder="Enter access password")
        if st.button("Login", type="primary"):
            if pwd == _APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect password. Please try again.")
        st.stop()

# ── App UI ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Cric Insights AI", page_icon="🏏", layout="wide")

col1, col2 = st.columns([4, 1])
with col1:
    st.title("🏏 Cric Insights AI")
    st.caption("Powered by **AI** · Cricsheet Data")
with col2:
    st.metric("Status", "🟢 Online")

with st.sidebar:
    st.header("⚙️ Settings")
    st.success("🤖 AI Assistant · Ready")
    st.divider()
    tool = st.selectbox("🛠️ Select Tool", [
        "💬 Ask AI",
        "🏏 Batter Stats",
        "🎳 Bowler Stats",
        "🏟️ Venue Stats",
        "⚔️ Head-to-Head",
        "📅 Recent Matches",
        "🎯 Full Match Insights",
    ])
    format_ = st.selectbox("📋 Format", ["T20", "ODI", "Test"])
    st.divider()
    use_grounding = st.toggle(
        "🌐 Live web search",
        value=True,
        help="Uses Google Search grounding for current IPL 2025/26 season data. Disable for faster responses from LLM knowledge only.",
    )
    if not use_grounding:
        st.caption("⚠️ Web search off — answers use LLM training data only (may miss recent matches)")
    st.divider()
    if _APP_PASSWORD and st.button("🔓 Logout"):
        st.session_state.authenticated = False
        st.rerun()
    st.caption("🌐 Cric Insights AI")
    st.caption("© Cric Insights 2026")

st.divider()

if tool == "💬 Ask AI":
    st.subheader("💬 Ask the Cricket AI")
    question = st.text_area(
        "Your question:",
        placeholder="Who should I pick for my fantasy team tonight?",
        height=120,
    )
    if st.button("🚀 Ask", type="primary", use_container_width=True):
        if question.strip():
            with st.spinner("🤔 Thinking..."):
                _fn = get_llm_response_grounded if use_grounding else get_llm_response
                answer = _fn(question, {"format": format_})
            st.markdown("### 💡 Answer")
            st.write(answer)
        else:
            st.warning("Please enter a question.")

elif tool == "🏏 Batter Stats":
    st.subheader("🏏 Batter Statistics")
    player = st.text_input("Player Name", placeholder="Virat Kohli")
    if st.button("📊 Analyse", type="primary", use_container_width=True):
        if player.strip():
            with st.spinner(f"Analysing {player}..."):
                _fn = get_llm_response_grounded if use_grounding else get_llm_response
                answer = _fn(
                    f"Comprehensive batting stats and analysis for {player} in {format_} cricket. "
                    "Include career averages, strike rate, recent form, strengths, weaknesses and fantasy value.",
                    {"format": format_, "player": player},
                )
            st.markdown(f"### 📊 {player} — Batting Analysis ({format_})")
            st.write(answer)
        else:
            st.warning("Please enter a player name.")

elif tool == "🎳 Bowler Stats":
    st.subheader("🎳 Bowler Statistics")
    player = st.text_input("Player Name", placeholder="Jasprit Bumrah")
    if st.button("📊 Analyse", type="primary", use_container_width=True):
        if player.strip():
            with st.spinner(f"Analysing {player}..."):
                _fn = get_llm_response_grounded if use_grounding else get_llm_response
                answer = _fn(
                    f"Comprehensive bowling stats and analysis for {player} in {format_} cricket. "
                    "Include wickets, economy, average, recent form and fantasy value.",
                    {"format": format_, "player": player},
                )
            st.markdown(f"### 📊 {player} — Bowling Analysis ({format_})")
            st.write(answer)
        else:
            st.warning("Please enter a player name.")

elif tool == "🏟️ Venue Stats":
    st.subheader("🏟️ Venue Statistics")
    venue = st.text_input("Venue Name", placeholder="Wankhede Stadium, Mumbai")
    if st.button("📊 Analyse Venue", type="primary", use_container_width=True):
        if venue.strip():
            with st.spinner(f"Analysing {venue}..."):
                _fn = get_llm_response_grounded if use_grounding else get_llm_response
                answer = _fn(
                    f"Detailed venue analysis for {venue} in {format_} cricket. "
                    "Include pitch conditions, average scores, batting/bowling nature and records.",
                    {"format": format_, "venue": venue},
                )
            st.markdown(f"### 🏟️ {venue} — Venue Analysis ({format_})")
            st.write(answer)
        else:
            st.warning("Please enter a venue name.")

elif tool == "⚔️ Head-to-Head":
    st.subheader("⚔️ Head-to-Head Analysis")
    col1, col2 = st.columns(2)
    with col1:
        team_a = st.text_input("🏳️ Team A", placeholder="India")
    with col2:
        team_b = st.text_input("🏳️ Team B", placeholder="Australia")
    if st.button("⚔️ Get Analysis", type="primary", use_container_width=True):
        if team_a.strip() and team_b.strip():
            with st.spinner(f"Analysing {team_a} vs {team_b}..."):
                _fn = get_llm_response_grounded if use_grounding else get_llm_response
                answer = _fn(
                    f"Head-to-head analysis between {team_a} and {team_b} in {format_} cricket. "
                    "Include overall record, recent meetings, key player battles and prediction.",
                    {"format": format_, "team_a": team_a, "team_b": team_b},
                )
            st.markdown(f"### ⚔️ {team_a} vs {team_b} ({format_})")
            st.write(answer)
        else:
            st.warning("Please enter both team names.")

elif tool == "📅 Recent Matches":
    st.subheader("📅 Recent Matches")
    team = st.text_input("Team Name", placeholder="India")
    n = st.slider("Number of matches", 1, 20, 5)
    if st.button("📅 Get Matches", type="primary", use_container_width=True):
        if team.strip():
            with st.spinner(f"Fetching {team} recent matches..."):
                _fn = get_llm_response_grounded if use_grounding else get_llm_response
                answer = _fn(
                    f"List and analyse the last {n} {format_} matches for {team}. "
                    "Include results, scores, key performers and current form.",
                    {"format": format_, "team": team, "n": n},
                )
            st.markdown(f"### 📅 {team} — Last {n} {format_} Matches")
            st.write(answer)
        else:
            st.warning("Please enter a team name.")

elif tool == "🎯 Full Match Insights":
    st.subheader("🎯 Full Match Insights")
    col1, col2 = st.columns(2)
    with col1:
        team_a = st.text_input("🏳️ Team A", placeholder="India")
        venue = st.text_input("🏟️ Venue", placeholder="Wankhede Stadium")
    with col2:
        team_b = st.text_input("🏳️ Team B", placeholder="Australia")
        match_date = st.text_input("📅 Match Date", placeholder="2026-03-15")
    squad_a = st.text_area(
        "Squad A (comma separated)", placeholder="Rohit Sharma, Virat Kohli...", height=80
    )
    squad_b = st.text_area(
        "Squad B (comma separated)", placeholder="Pat Cummins, David Warner...", height=80
    )
    if st.button("🎯 Generate Full Insights", type="primary", use_container_width=True):
        if team_a.strip() and team_b.strip() and venue.strip():
            with st.spinner("Generating full match insights..."):
                _fn = get_llm_response_grounded if use_grounding else get_llm_response
                answer = _fn(
                    f"Analyse the upcoming {format_} match between {team_a} and {team_b} at {venue} on {match_date}. "
                    f"Provide: 1) Team analysis 2) Key player matchups 3) Pitch & conditions "
                    f"4) Predicted Playing XI 5) Top fantasy picks 6) Match prediction with reasoning.",
                    {
                        "format": format_,
                        "venue": venue,
                        "team_a": team_a,
                        "team_b": team_b,
                        "squad_a": squad_a,
                        "squad_b": squad_b,
                        "date": match_date,
                    },
                )
            st.markdown(f"### 🎯 {team_a} vs {team_b} — Full Insights ({format_})")
            st.write(answer)
        else:
            st.warning("Please enter both teams and venue.")

st.divider()
st.caption("🏏 Cric Insights AI · AI by Google Gemini / OpenAI · 2026")
