"""AI health/status. NEVER returns or logs the key. Without probe=true no network call is made.
probe=true makes REAL calls (model list + one tiny generation) so 'configured' is never mistaken for 'working'.
Uses the google-genai SDK; independent of agent.py so it can diagnose it."""
import os, time
from fastapi import APIRouter

router = APIRouter()
_probe = {"t": 0.0, "result": None}
PROBE_COOLDOWN = 30

def _client():
    from google import genai
    from google.genai import types
    key = os.environ["GEMINI_API_KEY"]
    try: return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=30000))   # ms
    except Exception: return genai.Client(api_key=key)

def safe_error(e):
    """Map SDK errors to a short message that cannot contain the key."""
    low = str(e).lower()
    for k, v in (("api key", "API key rejected or missing: check GEMINI_API_KEY"), ("api_key_invalid", "API key rejected: check GEMINI_API_KEY"), ("permission", "key has no permission for this model"),
                 ("429", "rate limited or quota exceeded"), ("quota", "quota exceeded"), ("resource_exhausted", "quota exceeded"), ("404", "model not found: check GEMINI_MODEL"),
                 ("not found", "model not found: check GEMINI_MODEL"), ("timeout", "request timed out"), ("timed out", "request timed out"), ("connect", "network error reaching Google")):
        if k in low: return v
    return type(e).__name__

def run_probe(model):
    try:
        c = _client()
        names = [m.name.removeprefix("models/") for m in c.models.list()]
        listed = model in names
        text = (c.models.generate_content(model=model, contents="Reply with the single word: ok").text or "").strip()
        return {"ok": bool(text), "model_listed": listed, "reply_received": bool(text),
                "available_models_sample": [n for n in names if n.startswith("gemini")][:15], "error": None if text else "empty reply"}
    except Exception as e:
        return {"ok": False, "model_listed": None, "reply_received": False, "available_models_sample": [], "error": safe_error(e)}

@router.get("/api/ai/status")
def ai_status(probe: bool = False):
    key, model = os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    out = {"key_configured": bool(key), "model": model, "working": None, "probe": None}
    try:
        from . import agent
        out["workflow"] = agent.workflow_status()
    except Exception as e:
        out["workflow"] = {"unavailable": type(e).__name__}
    if probe:
        if not key: out["probe"] = {"ok": False, "error": "GEMINI_API_KEY is not set (backend/.env not loaded?)"}
        elif time.time() - _probe["t"] < PROBE_COOLDOWN and _probe["result"]: out["probe"] = {**_probe["result"], "cached": True}
        else:
            _probe["t"], _probe["result"] = time.time(), run_probe(model); out["probe"] = _probe["result"]
        out["working"] = out["probe"]["ok"]
    return out
