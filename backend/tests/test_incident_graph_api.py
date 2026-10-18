"""Endpoint-level check with a fake database. Needs the real app modules, so run from backend/: pytest"""
import pytest
from fastapi.testclient import TestClient
from app import main, graph_build

FIELDS = main.INC_FIELDS
def inc_row(**kw):
    base = dict.fromkeys(FIELDS); base.update(kw)
    return [base[f] for f in FIELDS]

@pytest.fixture
def client(monkeypatch):
    db = {"quake": inc_row(id="quake", name="M 4.6 quake", category="earthquake", source="usgs", status="resolved",
                           lat=-5.4, lng=35.0, data_origin="live", discovery_status="failed", discovery_error="ReadTimeout")}
    def fake_q(cypher, params=None):
        if cypher.startswith("MATCH (i:Incident {id:$i}) RETURN"):
            r = db.get(params["i"]); return [r] if r else []
        return []                          # no stored relationships at all
    monkeypatch.setattr(main, "q", fake_q)
    return TestClient(main.app)

def test_graph_endpoint_returns_incident_node_when_no_edges(client):
    r = client.get("/api/incidents/quake/graph")
    assert r.status_code == 200
    g = r.json()
    assert [n["id"] for n in g["nodes"]] == ["quake"] and g["edges"] == []
    assert g["metadata"]["data_status"] == "incident_only"
    assert any("discovery failed" in w for w in g["metadata"]["warnings"])

def test_unknown_incident_is_404(client):
    assert client.get("/api/incidents/nope/graph").status_code == 404

def test_seed_endpoint_is_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert client.post("/api/seed").status_code == 403
