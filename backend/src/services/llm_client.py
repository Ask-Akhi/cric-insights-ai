import re
import time
import hashlib
from datetime import date
from typing import Dict, Any, Optional
from .llm_settings import LLM_PROVIDER, LLM_MODEL, GEMINI_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, GROQ_MODEL
from .circuit_breaker import gemini_breaker

_QUOTA_MSG = (
    "⚠️ The AI service has reached its daily usage limit. "
    "Please try again in a few hours, or the limit resets at midnight Pacific time."
)

# ─── Token / Prompt limits ─────────────────────────────────────────────────
MAX_PROMPT_CHARS         = 12000  # ~3000 tokens — for non-grounded (LangGraph) path
MAX_PROMPT_CHARS_GROUNDED = 6000  # grounded path: allow room for prediction tables
MAX_RESPONSE_TOKENS          = 8192  # non-grounded: full detailed answers
MAX_RESPONSE_TOKENS_GROUNDED = 4096  # grounded: raised from 2048 — prevents mid-table truncation
CACHE_TTL_SECONDS = 1800          # 30 min cache — shorter so current-season data refreshes

# ─── In-memory response cache ──────────────────────────────────────────────
_cache: Dict[str, Dict] = {}   # key → {answer, ts} — cleared on restart

# ─── Dynamic max_output_tokens based on query complexity ───────────────────
def _max_tokens_for(prompt: str) -> int:
    """Simple queries → 1024, medium → 2048, complex → 4096, huge → 8192."""
    p = prompt.lower()
    # Complex: multiple comparisons, fantasy XI, full predictions with tables
    if any(w in p for w in ["fantasy", "dream11", "playing xi", "playing 11",
                             "predict", "head to head", "compare",
                             "captain", "vice captain"]):
        return 4096
    # Medium: stats questions, single-player analysis
    if any(w in p for w in ["average", "strike rate", "economy", "career",
                             "record", "stats", "ranking", "centuries",
                             "wickets", "top scorer", "best"]):
        return 2048
    # Simple: factual, yes/no, short answers
    if len(p) < 60:
        return 1024
    return 2048

# ─── Fallback models (best-first order, all verified non-retired) ────────
# gemini-2.5-flash      — primary, best quality, may 503 under high demand
# gemini-2.5-flash-8b   — lighter/faster variant, good fallback
# gemini-2.0-flash-lite — smallest quota usage, last resort
# NOTE: gemini-2.0-flash and gemini-2.0-flash-001 are RETIRED (404).
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-8b",
    "gemini-2.0-flash-lite",
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
        return "GEMINI_API_KEY is not configured. Please set it in Render → Environment."
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
        return "OPENAI_API_KEY is not configured. Please set it in Render → Environment."
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


def _sanitize_error(err: str) -> str:
    """Remove API keys and sensitive tokens from error messages before surfacing to clients."""
    # Redact api_key:VALUE patterns (Google includes the key in 403 error bodies)
    sanitized = re.sub(r"api_key:[A-Za-z0-9_\-]+", "api_key:[REDACTED]", err)
    # Redact any remaining long alphanumeric tokens that look like keys (≥20 chars)
    sanitized = re.sub(r"'[A-Za-z0-9_\-]{20,}'", "'[REDACTED]'", sanitized)
    return sanitized


def _clean_response(text: str) -> str:
    """Strip Gemini <think> blocks and biography-dump sentences from web grounding."""
    # Remove <think>...</think> reasoning blocks (Gemini 2.5 flash thinking mode)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Remove biography-dump lines that Gemini echoes verbatim from Google Search.
    # These are non-table, non-heading lines that are very long and contain bio phrases.
    bio_re = re.compile(
        r"(He is the (?:first|only|youngest|oldest)\b|"
        r"born \d{1,2} \w+ \d{4}|"
        r"\bHe has played \d+|"
        r"\b(?:Right|Left)-arm (?:fast|medium|spin|off-spin|leg-spin))",
        re.IGNORECASE,
    )
    lines = text.splitlines()
    clean = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("|") and not s.startswith("#") and bio_re.search(s) and len(s) > 100:
            continue   # skip bio-dump line
        clean.append(line)
    return "\n".join(clean).strip()


def _is_truncated_table(text: str) -> bool:
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

    # Circuit breaker — skip API call entirely when quota is exhausted
    if gemini_breaker.is_open:
        gemini_breaker.record_skip()
        # Try Groq fallback instead of just returning quota msg
        if GROQ_API_KEY:
            groq_answer = _groq_response(prompt, context)
            if not groq_answer.startswith("❌"):
                return groq_answer + "\n\n*(answered by Groq fallback - Gemini circuit breaker open)*"
        return _QUOTA_MSG

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=40_000),  # 40s in ms — Render wall is 60s
    )
    # Grounded path uses a shorter prompt so Gemini responds faster (web search adds ~15s)
    full_prompt = _build_prompt(prompt, context, grounded=grounded)

    # Grounding requires models that support it. Only currently supported
    # (non-retired) models that support Google Search grounding are listed.
    grounding_models = ["gemini-2.5-flash", "gemini-2.5-flash-8b"]
    all_models = [LLM_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != LLM_MODEL]
    models_to_try = [m for m in all_models if m in grounding_models] if grounded else all_models

    config_kwargs: dict = {
        # Grounded calls: cap output tokens so web-search + generation finishes in < 35s.
        # Non-grounded: dynamic based on query complexity (saves tokens on simple Qs).
        "max_output_tokens": MAX_RESPONSE_TOKENS_GROUNDED if grounded else _max_tokens_for(prompt),
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

                return _clean_response(text) if text else text

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    # Quota exhaustion → all models share same key, fail fast
                    if "quota" in err.lower() or "exceeded" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                        _logger.warning("Gemini quota exhausted — tripping circuit breaker, trying Groq")
                        gemini_breaker.trip(reason=_sanitize_error(err)[:120])
                        # Try Groq fallback before surfacing quota error
                        if GROQ_API_KEY:
                            groq_answer = _groq_response(prompt, context)
                            if not groq_answer.startswith("❌"):
                                return groq_answer + "\n\n*(answered by Groq fallback - Gemini quota exhausted)*"
                        return _QUOTA_MSG
                    if attempt == 0:
                        time.sleep(2)
                        continue
                    break   # try next model
                elif "503" in err or "UNAVAILABLE" in err or "overloaded" in err.lower() or "high demand" in err.lower():
                    # Gemini capacity error — brief pause then try next model
                    _logger.warning("Gemini %s 503/UNAVAILABLE — trying next model", model)
                    if attempt == 0:
                        time.sleep(2)
                        continue
                    break   # try next model
                elif "403" in err or "PERMISSION_DENIED" in err or "CONSUMER_SUSPENDED" in err:
                    # Key suspended or quota org-blocked — surface a clean message, never raw error
                    _logger.error("Gemini 403/PERMISSION_DENIED — key may be suspended: %s", _sanitize_error(err)[:200])
                    return (
                        "⚠️ The AI service API key has been suspended or is invalid. "
                        "Please update the GEMINI_API_KEY in the server environment."
                    )
                elif "404" in err or "NOT_FOUND" in err:
                    break   # model doesn't exist, skip
                elif grounded and ("tools" in err.lower() or "search" in err.lower()):
                    # Search not supported on this model — fall back without grounding
                    return _gemini_response(prompt, context, grounded=False)
                else:
                    _logger.warning("Gemini %s unexpected error: %s", model, _sanitize_error(err)[:200])
                    return f"❌ Gemini error: {_sanitize_error(err)}"

    if grounded:
        # All grounding-capable models exhausted — try without grounding
        return _gemini_response(prompt, context, grounded=False)
    # All Gemini models failed (503/overload/quota) — try Groq as free fallback
    if GROQ_API_KEY:
        _logger.warning("All Gemini models failed — falling back to Groq (%s)", GROQ_MODEL)
        groq_answer = _groq_response(prompt, context)
        if not groq_answer.startswith("❌"):
            return groq_answer + "\n\n*(answered by Groq fallback - Gemini was overloaded)*"
    return "❌ All Gemini models quota exhausted. Wait a few minutes or visit https://ai.dev/rate-limit"


def _groq_response(prompt: str, context: Dict[str, Any]) -> str:
    """Groq fallback - free, fast, OpenAI-compatible. Used when Gemini 503s or quota exhausted."""
    if not GROQ_API_KEY:
        return "❌ GROQ_API_KEY not set."
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=35.0,
        )
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=_max_tokens_for(prompt),
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are an expert cricket analyst. Be concise, use tables, cite numbers."},
                {"role": "user", "content": _build_prompt(prompt, context, grounded=False)},
            ],
        )
        text = response.choices[0].message.content or ""
        return _clean_response(text) if text else "❌ Groq returned empty response."
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("Groq fallback failed: %s", _sanitize_error(str(e))[:200])
        return f"❌ Groq error: {_sanitize_error(str(e))[:200]}"


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
        return f"❌ OpenAI error: {_sanitize_error(str(e))}"


def _build_prompt(prompt: str, context: Dict[str, Any], grounded: bool = False) -> str:
    today = date.today().strftime("%d %B %Y")
    # Grounded path: tighter prompt budget so Gemini + web search finishes in time
    max_chars = MAX_PROMPT_CHARS_GROUNDED if grounded else MAX_PROMPT_CHARS

    system = (
        f"You are an expert cricket analyst AI. Today is {today}.\n\n"
        "RULES:\n"
        "1. COMPLETE answers only — never cut off mid-sentence or mid-table.\n"
        "2. TABLES: always include header + separator (|---|) + ALL data rows.\n"
        "3. Use markdown headers (##), bullets, and tables. Cite sources ('per Cricsheet data' or 'per web search').\n"
        "4. CRICSHEET DATA = ground truth — use it as primary source when provided.\n"
        "5. Numbers over vague claims. No biographies.\n"
        "6. STATS: lead with stat table → context → summary.\n"
        "7. COMPARE: side-by-side table with Edge column → verdict.\n"
        "8. FANTASY: ranked table [Player|Team|Role|Exp Runs|Exp Wkts|Est Pts|Reason] → Captain/VC picks.\n"
        "9. PREDICT: winner + confidence % → 3 factors → COMPLETE player table → risk factor.\n"
        "10. Non-cricket → reply: '🏏 I am a cricket specialist.'\n"
        "11. End with a summary or actionable insight.\n\n"
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
        budget = max_chars - len(full) - len(question_suffix) - 80
        if budget > 500:
            if len(cricsheet_block) > budget:
                cricsheet_block = cricsheet_block[:budget] + "\n...[cricsheet data truncated]\n--- END CRICSHEET DATA ---\n\n"
            full += cricsheet_block
        # else: skip Cricsheet data entirely to stay within budget

    full += question_suffix
    return full
