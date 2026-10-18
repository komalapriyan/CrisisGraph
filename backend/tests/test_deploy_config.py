import pytest
from fastapi.testclient import TestClient
from app import main

@pytest.fixture
def client():
    return TestClient(main.app)

def test_cron_disabled_without_secret(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert client.get("/api/cron/ingest").status_code == 503

def test_cron_rejects_missing_or_wrong_token(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert client.get("/api/cron/ingest").status_code == 401
    assert client.get("/api/cron/ingest", headers={"Authorization": "Bearer nope"}).status_code == 401

def test_cron_runs_every_source_and_survives_one_failure(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    async def fake_run(src):
        if src == "bad": raise RuntimeError("boom")
        return {"ok": src}
    monkeypatch.setattr(main.ingest, "FETCH", {"good": object(), "bad": object()})
    monkeypatch.setattr(main.ingest, "run_source", fake_run)
    r = client.get("/api/cron/ingest", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200
    assert r.json() == {"good": {"ok": "good"}, "bad": {"error": "RuntimeError"}}

def test_ingest_loop_defaults_off_on_vercel_on_locally(monkeypatch):
    monkeypatch.delenv("INGEST_ENABLED", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    assert main.ingest_enabled() is True
    monkeypatch.setenv("VERCEL", "1")
    assert main.ingest_enabled() is False
    monkeypatch.setenv("INGEST_ENABLED", "true")      # explicit setting always wins
    assert main.ingest_enabled() is True
