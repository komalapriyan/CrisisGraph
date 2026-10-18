import asyncio, json, pytest
from app import agent

INC = {"id": "usgs-x", "name": "M 6", "category": "earthquake", "severity": "medium", "lat": 1.0, "lng": 2.0, "summary": "s", "event_time": 5}
GOOD = {"summary": "ok", "severity_assessment": "medium", "confirmed": ["a"], "unverified": [], "inferences": ["b"], "unknowns": ["pop"],
        "resource_needs": [{"resource": "medical", "reason": "injuries", "priority": "high"}], "confidence": "low"}

@pytest.fixture
def env(monkeypatch):
    store, calls = {}, []
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(agent, "_load", lambda i: store.get(i))
    monkeypatch.setattr(agent, "_save", lambda i, h, st, e=None, d=None: store.update({i: {"input_hash": h, "status": st, "attempted_at": 10**12, "error": e, "data": d}}))
    return store, calls, monkeypatch

def run(c): return asyncio.run(c)

def test_validate_rejects_bad_output():
    for bad in ({}, dict(GOOD, confidence="sure"), dict(GOOD, resource_needs=[{"resource": "x", "reason": "y", "priority": "urgent"}]), dict(GOOD, confirmed="a")):
        with pytest.raises(ValueError): agent.validate(bad)
    assert "quantity" not in agent.validate(dict(GOOD, resource_needs=[{"resource": "w", "reason": "r", "priority": "low", "quantity": 999}]))["resource_needs"][0]

def test_cache_skips_unchanged_and_reruns_on_change(env):
    store, calls, mp = env
    async def fake(inc): calls.append(1); return GOOD
    mp.setattr(agent, "_call_llm", fake)
    assert run(agent.analyze_incident(INC)) == "ok" and run(agent.analyze_incident(INC)) == "skipped" and len(calls) == 1
    assert run(agent.analyze_incident(dict(INC, severity="high"))) == "ok" and len(calls) == 2

def test_failure_does_not_raise_and_is_recorded(env):
    store, calls, mp = env
    async def boom(inc): raise TimeoutError("slow")
    mp.setattr(agent, "_call_llm", boom)
    assert run(agent.analyze_incident(INC)) == "unavailable" and store["usgs-x"]["status"] == "unavailable"
    async def bad(inc): return {"summary": "x"}
    mp.setattr(agent, "_call_llm", bad)
    assert run(agent.analyze_incident(INC, force=True)) == "unavailable"

def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert run(agent.analyze_incident(INC)) == "disabled"


def test_extract_gemini_response():
    ok = {"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]}
    assert agent.extract(ok)["summary"] == "ok"
    assert agent.extract({"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps(GOOD) + "\n```"}]}}]})["confidence"] == "low"
    for bad in ({}, {"promptFeedback": {"blockReason": "SAFETY"}}, {"candidates": [{"finishReason": "SAFETY"}]}, {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}):
        with pytest.raises(ValueError): agent.extract(bad)
