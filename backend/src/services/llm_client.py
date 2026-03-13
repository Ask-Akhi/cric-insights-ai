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


def get_llm_response(prompt: str, context: Dict[str, Any] = {}) -> str:
    """Standard LLM response — uses training data only, cached."""
    key = _cache_key(prompt, context)
    cached = _get_cached(key)
    if cached:
        return f"⚡ *(cached)*\n\n{cached}"

    if LLM_PROVIDER == "gemini":
        answer = _gemini_response(prompt, context, grounded=False)
    elif LLM_PROVIDER == "openai":
        answer = _openai_response(prompt, context)
    else:
        return f"Unknown LLM provider: {LLM_PROVIDER}"

    if not answer.startswith("❌"):
        _set_cached(key, answer)
    return answer


def get_llm_response_grounded(prompt: str, context: Dict[str, Any] = {}) -> str:
    """Grounded LLM response — uses Google Search for live/current-season data. Not cached."""
    if LLM_PROVIDER == "gemini":
        return _gemini_response(prompt, context, grounded=True)
    # OpenAI has no built-in search grounding — fall back gracefully
    return get_llm_response(prompt, context)


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

    for model in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                return response.text
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
    today = date.today().strftime("%d %B %Y")   # e.g. "13 March 2026"

    system = (
        f"You are an expert cricket analyst. Today's date is {today}.\n"
        "IMPORTANT INSTRUCTIONS:\n"
        "1. Use your most up-to-date knowledge — include stats from the current IPL season if it has started.\n"
        "2. If you are uncertain about very recent match results (last few days), say so clearly and give the most recent data you have.\n"
        "3. Give COMPLETE answers — never cut off mid-sentence or mid-list. Always finish every bullet point and section.\n"
        "4. Use bullet points and clear sections. Include all key stats: matches, runs, average, SR, wickets, economy, recent form.\n"
        "5. End with a clear summary or recommendation.\n\n"
    )

    # Include all non-empty context values (no truncation on values)
    ctx_parts = [f"{k}: {v}" for k, v in context.items() if v]
    ctx_str = "\n".join(ctx_parts) if ctx_parts else ""

    full = system
    if ctx_str:
        full += f"Context:\n{ctx_str}\n\n"
    full += f"Question: {prompt}"

    # Truncate only if truly enormous (12000 chars ~ 3000 tokens)
    if len(full) > MAX_PROMPT_CHARS:
        full = full[:MAX_PROMPT_CHARS] + "\n...[context truncated for length]"

    return full
