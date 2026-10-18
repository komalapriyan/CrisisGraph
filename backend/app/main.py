from .ai_status import router as ai_router
try:
    from dotenv import load_dotenv; load_dotenv()   # reads backend/.env if python-dotenv is installed
except ImportError:
    pass
import os, json, time, logging, asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .db import q
from .seed import reset
from .allocator import allocate
from . import ingest, agent, discover
from .assess import assess
from collections import Counter
from .ai_status import router as ai_router

app = FastAPI(title="CrisisGraph")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(ai_router)

def guard(fn):
    try:
        return fn()
    except RuntimeError as e:
        raise HTTPException(503, str(e))

@app.get("/api/health")
def health():
    return guard(lambda: {"falkordb": "ok", "nodes": q("MATCH (n) RETURN count(n)")[0][0]})

@app.post("/api/seed")
def do_seed():
    guard(reset); return {"status": "seeded (synthetic)"}

INC_FIELDS = ["id","name","category","status","severity","lat","lng","summary","data_origin","source","source_url","alert_level","event_time","updated_at","retrieved_at","precision","also_reported_by", "discovery_status", "discovery_at", "discovery_error"]
INC_RET = ",".join("i." + f for f in INC_FIELDS)

@app.get("/api/incidents")
def incidents():
    rows = guard(lambda: q("MATCH (i:Incident) RETURN " + INC_RET + " ORDER BY i.event_time DESC LIMIT 1000"))
    return [dict(zip(INC_FIELDS, r)) for r in rows]

@app.get("/api/incidents/{iid}/dependencies")
def deps(iid: str):
    """Multi-hop: incident -> location -> road -> provider -> resource."""
    rows = guard(lambda: q(
        "MATCH (i:Incident {id:$i})-[:OCCURRED_AT]->(l:Location)<-[:LEADS_TO]-(rd:Road)<-[:DELIVERS_VIA]-(p:Provider)-[:OFFERS]->(r:Resource) "
        "RETURN l.name, rd.name, rd.status, p.name, r.category, r.qty", {"i": iid}))
    if not rows: raise HTTPException(404, "Incident not found or has no dependencies")
    return [dict(zip(["location","road","road_status","provider","resource","stock"], r)) for r in rows]

def _plan():
    needs = [dict(zip(["id","category","qty","priority","location"], r)) for r in
             q("MATCH (l:Location)-[:HAS_NEED]->(n:Need) RETURN n.id,n.category,n.qty,n.priority,l.name")]
    rows = [dict(zip(["need_id","provider_id","provider","resource_id","stock","road_id","road"], r)) for r in q(
        "MATCH (n:Need)<-[:HAS_NEED]-(l:Location)<-[:LEADS_TO]-(rd:Road {status:'open'})<-[:DELIVERS_VIA]-(p:Provider {status:'active'})-[:OFFERS]->(r:Resource) "
        "WHERE r.category=n.category RETURN n.id,p.id,p.name,r.id,r.qty,rd.id,rd.name")]
    allocs, unmet = allocate(needs, rows)
    return {"allocations": allocs, "unmet": unmet, "total_demand": sum(n["qty"] for n in needs),
            "total_allocated": sum(a["qty"] for a in allocs), "origin": "SIMULATED"}

@app.get("/api/plan")
def plan():
    return guard(_plan)

@app.post("/api/simulate/close-road/{road_id}")
def close_road(road_id: str):
    def run():
        before = _plan()
        if not q("MATCH (r:Road {id:$r}) SET r.status='closed' RETURN r.id", {"r": road_id}):
            raise HTTPException(404, "Unknown road")
        after = _plan()
        broken = [a for a in before["allocations"] if a["road_id"] == road_id]
        q("CREATE (d:Decision {id:$id, action:'close_road', road:$r, created_at:$t, summary:$s})",
          {"id": f"dec-{time.time_ns()}", "r": road_id, "t": int(time.time()),
           "s": json.dumps({"broken": len(broken), "unmet_after": sum(u['qty'] for u in after['unmet'])})})
        return {"closed": road_id, "affected_allocations": broken, "before": before, "after": after}
    return guard(run)

@app.post("/api/simulate/reset")
def reset_sim():
    guard(lambda: q("MATCH (r:Road) SET r.status='open'")); return {"status": "baseline restored"}

@app.get("/api/decisions")
def decisions():
    return guard(lambda: [dict(zip(["id","action","road","created_at","summary"], r)) for r in
                          q("MATCH (d:Decision) RETURN d.id,d.action,d.road,d.created_at,d.summary ORDER BY d.created_at DESC")])


@app.get("/api/incidents/{iid}")
def incident(iid: str):
    rows = guard(lambda: q("MATCH (i:Incident {id:$i}) RETURN " + INC_RET, {"i": iid}))
    if not rows: raise HTTPException(404, f"Incident '{iid}' not found")
    return dict(zip(INC_FIELDS, rows[0]))

@app.get("/api/incidents/{iid}/assessment")
def incident_assessment(iid: str):
    return {**assess(incident(iid)), "ai": guard(lambda: agent.get_stored(iid))}

@app.get("/api/analytics")
def analytics():
    """Current-state snapshot computed from the graph. No history is stored, so none is returned."""
    def run():
        inc = q("MATCH (i:Incident) RETURN i.severity, i.status")
        roads = dict(q("MATCH (r:Road) RETURN r.status, count(r)"))
        p = _plan()
        stock = dict(q("MATCH (r:Resource) RETURN r.category, sum(r.qty)"))
        demand = dict(q("MATCH (n:Need) RETURN n.category, sum(n.qty)"))
        alloc, short = Counter(), Counter()
        for a in p["allocations"]: alloc[a["category"]] += a["qty"]
        for u in p["unmet"]: short[u["category"]] += u["qty"]
        reach = q("MATCH (l:Location) OPTIONAL MATCH (l)<-[:LEADS_TO]-(rd:Road {status:'open'})<-[:DELIVERS_VIA]-(pr:Provider {status:'active'}) "
                  "RETURN l.name, count(DISTINCT pr)")
        cats = sorted(set(stock) | set(demand))
        res = {"incidents_total": len(inc),
                "severity": dict(Counter((r[0] or "unrated") for r in inc)),
                "status": dict(Counter((r[1] or "unknown") for r in inc)),
                "roads": {"open": roads.get("open", 0), "closed": roads.get("closed", 0)},
                "resources": [{"category": c, "stock": stock.get(c, 0), "demand": demand.get(c, 0),
                               "allocated": alloc[c], "shortage": short[c]} for c in cats],
                "locations": [{"name": r[0], "reachable_providers": r[1]} for r in reach],
                "unreachable_locations": [r[0] for r in reach if r[1] == 0],
                "plan": {"demand": p["total_demand"], "allocated": p["total_allocated"], "unmet": p["total_demand"] - p["total_allocated"]},
                "history": "/api/history", "origin": "SIMULATED"}
        _snapshot(res)
        return res
    return guard(run)

@app.get("/api/graph")
def graph_data():
    """All stored relationships, as nodes + edges, straight from FalkorDB."""
    rows = guard(lambda: q("MATCH (a)-[e]->(b) WHERE NOT (a:Facility OR b:Facility OR a:Requirement OR b:Requirement OR a:Area OR b:Area OR a:Assessment OR b:Assessment) RETURN a.id, labels(a)[0], coalesce(a.name,a.category,a.id), coalesce(a.status,''), "
                           "type(e), b.id, labels(b)[0], coalesce(b.name,b.category,b.id), coalesce(b.status,'')"))
    nodes, edges = {}, []
    for aid, al, an, ast, et, bid, bl, bn, bst in rows:
        nodes[aid] = {"id": aid, "type": al, "label": an, "status": ast}
        nodes[bid] = {"id": bid, "type": bl, "label": bn, "status": bst}
        edges.append({"from": aid, "to": bid, "type": et})
    return {"nodes": list(nodes.values()), "edges": edges}


# ---- history: real timestamped snapshots of scenario state -------------------
RANGES = {"hourly": (3600, 24), "daily": (86400, 14), "weekly": (604800, 12), "monthly": (2592000, 12)}
METRICS = ("unmet", "allocated", "closed_roads")

def _snapshot(a):
    """Store one observation when scenario state changed (or every 15 min). Timestamps are real."""
    try:
        cur = (a["plan"]["unmet"], a["plan"]["allocated"], a["roads"]["closed"])
        last = q("MATCH (s:Snapshot) RETURN s.ts,s.unmet,s.allocated,s.closed_roads ORDER BY s.ts DESC LIMIT 1")
        now = int(time.time())
        if last and now - last[0][0] < 900 and tuple(last[0][1:]) == cur:
            return
        q("CREATE (:Snapshot {id:$id, ts:$ts, unmet:$u, allocated:$a, demand:$d, closed_roads:$c})",
          {"id": f"snap-{time.time_ns()}", "ts": now, "u": cur[0], "a": cur[1], "d": a["plan"]["demand"], "c": cur[2]})
    except Exception:
        logging.exception("snapshot failed")

def bucketize(rows, step, n, now):
    """rows: ascending (ts, value). Value of a bucket = last observation in it; no observation -> None (not 0)."""
    start = (now // step - n + 1) * step
    out = [{"t": start + i * step, "value": None} for i in range(n)]
    for ts, v in rows:
        i = (ts - start) // step
        if 0 <= i < n and v is not None:
            out[i]["value"] = v
    return out

@app.get("/api/history")
def history(range: str = "hourly", metric: str = "unmet"):
    if range not in RANGES: raise HTTPException(422, f"range must be one of {list(RANGES)}")
    if metric not in METRICS: raise HTTPException(422, f"metric must be one of {list(METRICS)}")
    step, n = RANGES[range]
    start = (int(time.time()) // step - n + 1) * step
    rows = guard(lambda: q(f"MATCH (s:Snapshot) WHERE s.ts >= $t RETURN s.ts, s.{metric} ORDER BY s.ts", {"t": start}))
    return {"range": range, "metric": metric, "buckets": bucketize(rows, step, n, int(time.time())),
            "snapshots": len(rows), "last_snapshot": rows[-1][0] if rows else None, "origin": "SIMULATED"}


# ---- live ingestion --------------------------------------------------------
@app.on_event("startup")
async def _start_ingest():
    if os.getenv("INGEST_ENABLED", "true").lower() == "true":
        asyncio.create_task(ingest.scheduler())

@app.get("/api/sources")
def sources():
    rows = guard(lambda: q("MATCH (s:Source) RETURN s.id,s.last_attempt,s.last_success,s.last_error,s.last_count"))
    return [dict(zip(["id", "last_attempt", "last_success", "last_error", "last_count"], r)) for r in rows]

@app.post("/api/ingest/run")
async def ingest_run(source: str):
    if source not in ingest.FETCH: raise HTTPException(422, f"source must be one of {list(ingest.FETCH)}")
    if time.time() - ingest.last_run.get(source, 0) < 60: raise HTTPException(429, "Ran less than 60 s ago")
    ingest.last_run[source] = time.time()
    return await ingest.run_source(source)

@app.get("/api/workflow/status")
def workflow_status():
    return {**guard(agent.workflow_status), "scheduler_enabled": os.getenv("INGEST_ENABLED", "true").lower() == "true",
            "sources": sources()}

@app.post("/api/incidents/{iid}/analyze")
async def analyze(iid: str):
    inc = incident(iid)
    if inc.get("source") is None: raise HTTPException(422, "Only live incidents can be analysed")
    if not agent.configured(): raise HTTPException(503, "GEMINI_API_KEY is not set on the backend")
    return {"result": await agent.analyze_incident(inc), "assessment": agent.get_stored(iid)}

GN = "{0}.id, labels({0})[0], coalesce({0}.name,{0}.category,{0}.id), coalesce({0}.status,'')"

@app.get("/api/incidents/{iid}/graph")
def incident_graph(iid: str):
    """Incident-scoped subgraph (outgoing, 2 hops), straight from FalkorDB."""
    incident(iid)
    cols = GN.format("a") + ", type(e), " + GN.format("b")
    rows = guard(lambda: q("MATCH (i:Incident {id:$i})-[e]->(b) WHERE NOT b:Assessment WITH i AS a, e, b RETURN " + cols, {"i": iid})
                 + q("MATCH (i:Incident {id:$i})-[]->(a)-[e]->(b) RETURN " + cols, {"i": iid}))
    nodes, edges = {}, set()
    for r in rows:
        nodes[r[0]] = {"id": r[0], "type": r[1], "label": r[2], "status": r[3]}; nodes[r[5]] = {"id": r[5], "type": r[6], "label": r[7], "status": r[8]}
        edges.add((r[0], r[4], r[5]))
    return {"nodes": list(nodes.values()), "edges": [{"from": a, "type": t, "to": b} for a, t, b in sorted(edges)]}

@app.get("/api/incidents/{iid}/facilities")
def facilities(iid: str):
    inc = incident(iid)
    rows = guard(lambda: q("MATCH (i:Incident {id:$i})-[r:NEAR]->(f:Facility) RETURN f.id,f.name,f.category,f.lat,f.lng,r.distance_km,f.source_url,f.phone,f.website,f.verification,r.retrieved_at ORDER BY r.distance_km", {"i": iid}))
    return {"discovery": {"status": inc.get("discovery_status") or "not_run", "at": inc.get("discovery_at"), "error": inc.get("discovery_error"), "radius_km": discover.RADIUS_KM, "source": "OpenStreetMap Overpass"},
            "facilities": [dict(zip(["id", "name", "category", "lat", "lng", "distance_km", "source_url", "phone", "website", "verification", "retrieved_at"], r)) for r in rows]}

_last_disc = {}
@app.post("/api/incidents/{iid}/discover")
async def run_discover(iid: str):
    inc = incident(iid)
    if inc.get("source") is None or inc.get("lat") is None: raise HTTPException(422, "Only live incidents with coordinates can be discovered")
    if time.time() - _last_disc.get(iid, 0) < 60: raise HTTPException(429, "Ran less than 60 s ago")
    _last_disc[iid] = time.time()
    return {"result": await discover.discover_incident(inc, force=True)}
