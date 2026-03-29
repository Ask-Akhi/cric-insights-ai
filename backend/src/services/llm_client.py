import time
import hashlib
from datetime import date
from typing import Dict, Any, Optional
from .llm_settings import LLM_PROVIDER, LLM_MODEL, GEMINI_API_KEY, OPENAI_API_KEY

# ─── Token / Prompt limits ─────────────────────────────────────────────────
MAX_PROMPT_CHARS = 12000     # ~3000 tokens input — enough for full squad/context
MAX_RESPONSE_TOKENS = 8192   # full detailed answers, never truncated
CACHE_TTL_SECONDS = 1800     # 30 min cache — shorter so current-season data refreshes

# ─── In-memory response cache ──────────────────────────────────────────────
_cache: Dict[str, Dict] = {}   # key → {answer, ts} — cleared on restart

# ─── Fallback models (verified available, best-first order) ───────────────
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash",         # largest context + best current knowledge
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
]


def _cache_key(prompt: str, context: Dict[str, Any]) -> str:
    raw = prompt + str(sorted(context.items()))
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> Optional[str]:
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
        return entry["answer"]
    return None


def _set_cached(key: str, answer: str) -> None:
    # Keep cache small — max 100 entries (evict oldest)
    if len(_cache) >= 100:
        oldest = min(_cache, key=lambda k: _cache[k]["ts"])
        del _cache[oldest]
    _cache[key] = {"answer": answer, "ts": time.time()}


def _check_api_key() -> str | None:
    """Returns an error message if no API key is configured, else None."""
    if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
        return "GEMINI_API_KEY is not configured. Please set it in Railway → Variables."
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
        return "OPENAI_API_KEY is not configured. Please set it in Railway → Variables."
    return None


def get_llm_response(prompt: str, context: Dict[str, Any] = {}) -> str:
    """Standard LLM response — uses training data only, cached."""
    if err := _check_api_key():
        raise ValueError(err)

    key = _cache_key(prompt, context)
    cached = _get_cached(key)
    if cached:
        return f"⚡ *(cached)*\n\n{cached}"

    if LLM_PROVIDER == "gemini":
        answer = _gemini_response(prompt, context, grounded=False)
    elif LLM_PROVIDER == "openai":
        answer = _openai_response(prompt, context)
    else:
        raise ValueError(f"Unknown LLM provider: {LLM_PROVIDER}")

    if not answer.startswith("❌"):
        _set_cached(key, answer)
    return answer


def get_llm_response_grounded(prompt: str, context: Dict[str, Any] = {}) -> str:
    """Grounded LLM response — uses Google Search for live/current-season data. Not cached."""
    if err := _check_api_key():
        raise ValueError(err)
    if LLM_PROVIDER == "gemini":
        return _gemini_response(prompt, context, grounded=True)
    # OpenAI has no built-in search grounding — fall back gracefully
    return get_llm_response(prompt, context)


def _is_truncated_table(text: str) -> bool:
    """Return True if the response ends with a table header row but no data rows."""
    if not text:
        return False
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    last = lines[-1].strip()
    # Last line is a pipe-delimited row (header or separator)
    if not (last.startswith("|") and last.endswith("|")):
        return False
    # Check if it's ONLY a header (no separator line followed by data)
    # Find the last table block
    table_lines = []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.insert(0, stripped)
        else:
            break
    # A complete table needs: header + separator + at least 1 data row = 3+ lines
    has_separator = any(set(l.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")) == set() for l in table_lines)
    return len(table_lines) < 3 or not has_separator


def _gemini_response(prompt: str, context: Dict[str, Any], grounded: bool = False) -> str:
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY not set in .env file."

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    full_prompt = _build_prompt(prompt, context)

    # Grounding requires models that support it — 2.0-flash+ only
    # gemini-2.5-flash and gemini-2.0-flash both support Google Search grounding
    grounding_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-001"]
    all_models = [LLM_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != LLM_MODEL]
    models_to_try = [m for m in all_models if m in grounding_models] if grounded else all_models

    config_kwargs: dict = {
        "max_output_tokens": MAX_RESPONSE_TOKENS,
        "temperature": 0.3,
    }
    if grounded:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

    import logging as _log
    _logger = _log.getLogger(__name__)

    for model in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )

                # ── Robust text extraction ─────────────────────────────────
                # response.text raises / returns "" when finish_reason is
                # RECITATION, SAFETY, MAX_TOKENS, etc. Extract from parts directly.
                text = ""
                try:
                    text = response.text or ""
                except Exception:
                    pass

                # If .text is empty, try extracting from candidates[0].content.parts
                if not text:
                    try:
                        for candidate in (response.candidates or []):
                            finish = getattr(candidate, "finish_reason", None)
                            _logger.warning(
                                f"Gemini {model} (grounded={grounded}): "
                                f"response.text empty, finish_reason={finish}"
                            )
                            content = getattr(candidate, "content", None)
                            if content:
                                for part in (getattr(content, "parts", None) or []):
                                    t = getattr(part, "text", None)
                                    if t:
                                        text += t
                    except Exception as ex:
                        _logger.warning(f"Gemini candidate extraction failed: {ex}")

                # If still empty and grounded, fall back to non-grounded immediately
                if not text and grounded:
                    _logger.warning(
                        f"Gemini grounded response empty for model={model} — "
                        f"falling back to non-grounded call"
                    )
                    return _gemini_response(prompt, context, grounded=False)

                # ── Truncation guard ───────────────────────────────────────
                # If response ends mid-table, retry once with a continuation prompt.
                if text and _is_truncated_table(text) and attempt == 0:
                    continuation = (
                        full_prompt
                        + "\n\n[SYSTEM: Your previous response was cut off mid-table. "
                        "Please complete the markdown table with ALL data rows and finish the response.]"
                    )
                    r2 = client.models.generate_content(
                        model=model,
                        contents=continuation,
                        config=types.GenerateContentConfig(**config_kwargs),
                    )
                    retry_text = ""
                    try:
                        retry_text = r2.text or ""
                    except Exception:
                        pass
                    text = retry_text or text

                return text

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    if attempt == 0:
                        time.sleep(8)
                        continue
                    break   # try next model
                elif "404" in err or "NOT_FOUND" in err:
                    break   # model doesn't exist, skip
                elif grounded and ("tools" in err.lower() or "search" in err.lower()):
                    # Search not supported on this model — fall back without grounding
                    return _gemini_response(prompt, context, grounded=False)
                else:
                    return f"❌ Gemini error: {err}"

    if grounded:
        # All grounding-capable models exhausted — try without grounding
        return _gemini_response(prompt, context, grounded=False)
    return "❌ All Gemini models quota exhausted. Wait a few minutes or visit https://ai.dev/rate-limit"


def _openai_response(prompt: str, context: Dict[str, Any]) -> str:
    try:
        from openai import OpenAI
        if not OPENAI_API_KEY:
            return "❌ OPENAI_API_KEY not set in .env file."
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=MAX_RESPONSE_TOKENS,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "Cricket analyst. Be concise."},
                {"role": "user", "content": _build_prompt(prompt, context)}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ OpenAI error: {str(e)}"


def _build_prompt(prompt: str, context: Dict[str, Any]) -> str:
    today = date.today().strftime("%d %B %Y")

    system = (
        f"You are an expert cricket analyst AI — the equivalent of a senior ESPNcricinfo journalist combined with a data scientist. Today's date is {today}.\n\n"
        "=== CORE RULES ===\n"
        "1. COMPLETE answers only — never cut off mid-sentence, mid-table, or mid-list.\n"
        "2. TABLES: always include the header row, the separator row (|---|---|), AND all data rows. Never emit a table header without its data rows.\n"
        "3. STRUCTURE every response with markdown headers (##), bullet points, and tables where relevant.\n"
        "4. CRICSHEET DATA = GROUND TRUTH — if provided below, always cite it explicitly and use it as primary source.\n"
        "5. VENUE/GROUND RECORDS — if Cricsheet venue data is provided, use it. If not provided, say 'per web search' and use your grounded knowledge.\n"
        "6. FANTASY PREDICTION DATA — if FANTASY PREDICTION blocks are provided below, use those exact expected-runs/wickets numbers in your table. Do NOT say 'data unavailable'.\n"
        "7. CITE your sources — say 'per Cricsheet data' or 'per web search' so users know what's verified.\n"
        "8. CURRENT SEASON — include IPL 2026 context when discussing players.\n"
        "9. NON-CRICKET REDIRECT — if the question is not about cricket, respond: '🏏 I am a cricket specialist. Try asking about a player, match, or fantasy team.'\n"
        "10. NUMBERS over vague claims — always prefer 'average of 48.3 in 87 matches' over 'plays well consistently'.\n"
        "11. END WITH VALUE — always close with a summary, recommendation, or actionable insight.\n\n"
        "=== OUTPUT QUALITY ===\n"
        "- For STATS questions: lead with a stat table, then context, then summary.\n"
        "- For COMPARE questions: use a side-by-side table with an 'Edge' column, then give a definitive verdict.\n"
        "- For FANTASY questions: give a ranked table with columns [Player | Team | Role | Expected Runs | Expected Wickets | Est. Fantasy Pts | Pick Reason], then Captain/VC picks.\n"
        "- For PREDICT questions: give winner + confidence %, then 3 key deciding factors, then a player predictions table.\n"
        "- For GENERAL questions: match the depth to the question — concise for simple, structured for complex.\n\n"
        "=== CRITICAL TABLE FORMAT ===\n"
        "Every markdown table MUST have ALL three parts:\n"
        "1. Header row: | Col1 | Col2 | Col3 |\n"
        "2. Separator: |---|---|---|\n"
        "3. Data rows: | value | value | value |\n"
        "NEVER emit a header row without the separator and at least one data row.\n\n"
    )

    # Cricsheet RAG data — inject first so LLM treats it as ground truth
    cricsheet_data = context.get("cricsheet_data", "")
    detected_players = context.get("detected_players", "")

    # Other context fields (format, grounded etc.) — skip internal keys
    ctx_parts = [
        f"{k}: {v}" for k, v in context.items()
        if v and not k.startswith("_") and k not in ("cricsheet_data", "detected_players")
    ]
    ctx_str = "\n".join(ctx_parts)

    full = system
    if ctx_str:
        full += f"Context:\n{ctx_str}\n\n"

    question_suffix = f"Question: {prompt}"

    if cricsheet_data:
        cricsheet_block = (
            "--- VERIFIED CRICSHEET DATA (ball-by-ball, use as primary stats source) ---\n"
            f"{cricsheet_data}\n"
            "--- END CRICSHEET DATA ---\n\n"
        )
        # Truncate only the Cricsheet block if the full prompt would exceed the limit,
        # always preserving the system prompt and the question.
        budget = MAX_PROMPT_CHARS - len(full) - len(question_suffix) - 80
        if budget > 500:
            if len(cricsheet_block) > budget:
                cricsheet_block = cricsheet_block[:budget] + "\n...[cricsheet data truncated]\n--- END CRICSHEET DATA ---\n\n"
            full += cricsheet_block
        # else: skip Cricsheet data entirely to stay within budget

    full += question_suffix
    return full
