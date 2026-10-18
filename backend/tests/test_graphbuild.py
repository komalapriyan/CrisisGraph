import asyncio
from app import graphbuild as gb, discover as d

INC = {"id": "usgs-t", "name": "M 4.6 test", "category": "earthquake", "severity": "low", "lat": -5.4767, "lng": 35.0428, "data_origin": "live:usgs"}

def rec(monkeypatch):
    calls = []; f = lambda c, p=None: calls.append((c, p)) or []
    monkeypatch.setattr(gb, "q", f); monkeypatch.setattr(d, "q", f); return calls

def test_base_graph_needs_no_network_or_facilities(monkeypatch):
    calls = rec(monkeypatch); monkeypatch.setattr("app.agent.get_stored", lambda i: {"status": "not_run"})
    specs = gb.ensure_base_graph(INC)
    text = " ".join(c for c, _ in calls)
    assert "MERGE (a:Area" in text and "OCCURRED_AT" in text and text.count("MERGE (r:Requirement") == len(specs) > 0 and "Facility" not in text
    assert all(s["basis"] == "rules_v1" for s in specs)

def test_requirements_follow_successful_ai_assessment(monkeypatch):
    rec(monkeypatch)
    monkeypatch.setattr("app.agent.get_stored", lambda i: {"status": "ok", "data": {"resource_needs": [{"resource": "Medical triage teams", "reason": "injuries", "priority": "high"}]}})
    s = gb.ensure_base_graph(INC)
    assert [x["basis"] for x in s] == ["gemini"] and s[0]["fac"] == ["hospital", "clinic", "pharmacy"] and s[0]["id"] == "req-usgs-t-medical_triage_teams"

def test_invalid_coordinates_write_nothing(monkeypatch):
    calls = rec(monkeypatch)
    assert gb.ensure_base_graph(dict(INC, lat=95)) is None and gb.ensure_base_graph(dict(INC, lng=None)) is None and calls == []

def test_graph_exists_even_when_overpass_fails(monkeypatch):
    built, marks = [], []
    monkeypatch.setattr(gb, "ensure_base_graph", lambda i: built.append(i["id"]) or [])
    monkeypatch.setattr(d, "_mark", lambda *a: marks.append(a))
    async def boom(*a, **k): raise d.httpx.ReadTimeout("")
    monkeypatch.setattr(d.httpx.AsyncClient, "post", boom)
    assert asyncio.run(d.discover_incident(dict(INC), force=True)) == "failed" and built == ["usgs-t"] and marks[0][1] == "failed"

def test_second_mirror_is_used_when_first_fails(monkeypatch):
    monkeypatch.setattr(d, "OVERPASS_URLS", ["https://a.example/x", "https://b.example/x"])
    class R:
        def raise_for_status(self): pass
        def json(self): return {"elements": [{"type": "node", "id": 1, "lat": -5.4, "lon": 35.0, "tags": {"amenity": "clinic"}}]}
    async def post(self, url, **k):
        if "a.example" in url: raise d.httpx.ConnectTimeout("")
        return R()
    monkeypatch.setattr(d.httpx.AsyncClient, "post", post)
    assert asyncio.run(d._overpass(-5.4767, 35.0428, 20))[0]["id"] == 1
