import asyncio
from app import discover as d, graphbuild as gb

EL = [{"type": "node", "id": 1, "lat": 10.0, "lon": 20.1, "tags": {"amenity": "hospital", "name": "A", "website": "javascript:x", "phone": "123"}},
      {"type": "way", "id": 2, "center": {"lat": 10.0, "lon": 20.01}, "tags": {"amenity": "fire_station"}},
      {"type": "node", "id": 3, "lat": 95, "lon": 0, "tags": {"amenity": "hospital"}},          # invalid coords
      {"type": "node", "id": 4, "lat": 10, "lon": 20, "tags": {"shop": "bakery"}}]               # not a target category

def test_query_shape():
    qy = d.build_query(10, 20, 25000)
    assert "around:25000,10,20" in qy and '"amenity"="hospital"' in qy and qy.startswith("[out:json]")

def test_parse_validates_sorts_and_never_invents_contacts():
    r = d.parse(EL, 10.0, 20.0, 5)
    assert [f["id"] for f in r] == ["osm-way-2", "osm-node-1"]           # nearest first, bad coords + wrong category dropped
    assert r[0]["name"] == "Unnamed fire station" and r[1]["website"] is None and r[1]["phone"] == "123"
    assert all(f["verification"] == "osm_mapped_unverified" for f in r)

def test_persist_is_idempotent_and_makes_no_supply_claims(monkeypatch):
    calls = []
    rec = lambda c, p=None: calls.append((c, p)) or []
    monkeypatch.setattr(d, "q", rec); monkeypatch.setattr(gb, "q", rec)
    monkeypatch.setattr("app.agent.get_stored", lambda i: {"status": "not_run"})
    inc = {"id": "usgs-x", "name": "M6", "category": "earthquake", "severity": "high", "lat": 10.0, "lng": 20.0, "data_origin": "live:usgs"}
    d.persist(inc, d.parse(EL, 10.0, 20.0, 5), 5)
    text = " ".join(c for c, _ in calls)
    assert text.count("MERGE (f:Facility") == 2 and "DELETE r" in text and "SUPPLIES" not in text and "stock" not in text.lower()
    assert any("RELEVANT_TO" in c and p["r"].endswith("search_and_rescue") for c, p in calls)

def test_skip_when_recent_and_failure_does_not_raise(monkeypatch):
    inc = {"id": "u", "category": "earthquake", "lat": 1.0, "lng": 2.0}
    inc.update(discovery_status="ok", discovery_at=10**12, discovery_hash=d._hash(inc))
    assert asyncio.run(d.discover_incident(inc)) == "skipped"
    marks = []
    monkeypatch.setattr(d, "_mark", lambda *a: marks.append(a)); monkeypatch.setattr(gb, "ensure_base_graph", lambda i: [])
    async def boom(*a, **k): raise d.httpx.ReadTimeout("")
    monkeypatch.setattr(d.httpx.AsyncClient, "post", boom)
    assert asyncio.run(d.discover_incident(dict(inc, discovery_status=None), force=True)) == "failed" and marks[0][1] == "failed" and "did not answer" in marks[0][3]
