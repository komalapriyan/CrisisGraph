from app import ai_status as s

class _M:  # fake model entry
    def __init__(self, n): self.name = n
class _Models:
    def __init__(self, names, reply="ok", boom=None): self.n, self.reply, self.boom = names, reply, boom
    def list(self): return [_M(x) for x in self.n]
    def generate_content(self, model, contents):
        if self.boom: raise self.boom
        return type("R", (), {"text": self.reply})()
class _C:
    def __init__(self, **k): self.models = _Models(["models/gemini-2.5-flash", "models/embedding-001"], **k)

def reset(): s._probe.update(t=0.0, result=None)

def test_no_key_never_probes_and_never_leaks(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False); reset()
    o = s.ai_status(probe=True)
    assert o["key_configured"] is False and o["working"] is False and "GEMINI_API_KEY" in o["probe"]["error"]

def test_configured_is_not_working_without_probe(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-123"); reset()
    o = s.ai_status()
    assert o["key_configured"] is True and o["working"] is None and "SECRET-123" not in str(o)

def test_successful_probe(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-123"); monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash"); reset()
    monkeypatch.setattr(s, "_client", lambda: _C())
    o = s.ai_status(probe=True)
    assert o["working"] is True and o["probe"]["model_listed"] is True and o["probe"]["available_models_sample"] == ["gemini-2.5-flash"]

def test_invalid_model_and_errors_are_safe(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-123"); monkeypatch.setenv("GEMINI_MODEL", "nope"); reset()
    monkeypatch.setattr(s, "_client", lambda: _C(boom=RuntimeError("404 NOT_FOUND model nope; key=SECRET-123")))
    o = s.ai_status(probe=True)
    assert o["working"] is False and "GEMINI_MODEL" in o["probe"]["error"] and "SECRET-123" not in str(o)
    reset(); monkeypatch.setattr(s, "_client", lambda: _C(boom=RuntimeError("429 RESOURCE_EXHAUSTED")))
    assert "quota" in s.ai_status(probe=True)["probe"]["error"].lower() or "rate" in s.ai_status(probe=True)["probe"]["error"].lower()

def test_probe_is_rate_limited(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k"); reset(); calls = []
    monkeypatch.setattr(s, "run_probe", lambda m: calls.append(1) or {"ok": True})
    s.ai_status(probe=True); o = s.ai_status(probe=True)
    assert len(calls) == 1 and o["probe"]["cached"] is True
