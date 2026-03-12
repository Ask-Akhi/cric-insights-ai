import time
import hashlib
from typing import Dict, Any, Optional
from .llm_settings import LLM_PROVIDER, LLM_MODEL, GEMINI_API_KEY, OPENAI_API_KEY

# ─── Token / Prompt limits ─────────────────────────────────────────────────
MAX_PROMPT_CHARS = 2000      # ~500 tokens input
MAX_RESPONSE_TOKENS = 2048   # full detailed answers
CACHE_TTL_SECONDS = 3600     # cache answers for 1 hour

# ─── In-memory response cache ──────────────────────────────────────────────
_cache: Dict[str, Dict] = {}   # key → {answer, ts} — cleared on restart

# ─── Fallback models (verified available) ─────────────────────────────────
GEMINI_FALLBACK_MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.5-flash",
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
    # Check cache first — no API call needed
    key = _cache_key(prompt, context)
    cached = _get_cached(key)
    if cached:
        return f"⚡ *(cached)*\n\n{cached}"

    if LLM_PROVIDER == "gemini":
        answer = _gemini_response(prompt, context)
    elif LLM_PROVIDER == "openai":
        answer = _openai_response(prompt, context)
    else:
        return f"Unknown LLM provider: {LLM_PROVIDER}"

    # Only cache successful responses
    if not answer.startswith("❌"):
        _set_cached(key, answer)
    return answer


def _gemini_response(prompt: str, context: Dict[str, Any]) -> str:
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY not set in .env file."

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    full_prompt = _build_prompt(prompt, context)

    models_to_try = [LLM_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != LLM_MODEL]

    for model in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=MAX_RESPONSE_TOKENS,
                        temperature=0.3,   # more focused, less verbose
                    ),
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
                    break   # model doesn't exist, skip to next
                else:
                    return f"❌ Gemini error: {err}"

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
    # Concise system instruction — fewer tokens
    system = "You are a cricket analyst. Give a complete, factual answer with all key stats. Use bullet points. Never truncate or cut off mid-sentence. Always finish your full response.\n\n"

    # Only include non-empty context values
    ctx_parts = [f"{k}: {str(v)[:80]}" for k, v in context.items() if v]
    ctx_str = "\n".join(ctx_parts) if ctx_parts else ""

    full = f"{system}"
    if ctx_str:
        full += f"Context: {ctx_str}\n\n"
    full += f"Q: {prompt}"

    # Truncate to MAX_PROMPT_CHARS to stay within token budget
    if len(full) > MAX_PROMPT_CHARS:
        full = full[:MAX_PROMPT_CHARS] + "..."

    return full
