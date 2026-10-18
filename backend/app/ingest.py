"""Public-feed ingestion: fetch -> normalise -> validate -> dedupe -> upsert into FalkorDB.
Runs on the backend schedule only; browsers never call the external feeds."""
import os, time, math, asyncio, logging
from datetime import datetime, timezone, timedelta
import httpx
from .db import q

log = logging.getLogger("ingest")
UA = {"User-Agent": "CrisisGraph/0.1 (hackathon prototype)"}
CATS = {"EQ": "earthquake", "TC": "cyclone", "FL": "flood", "VO": "volcano", "WF": "wildfire", "DR": "drought"}
ALERT_SEV = {"red": "critical", "orange": "high", "yellow": "medium", "green": "low"}
USGS_URL = os.getenv("USGS_FEED", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson")
GDACS_URL = os.getenv("GDACS_URL", "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH")
INTERVALS = {"usgs": int(os.getenv("USGS_POLL_SECONDS", "600")), "gdacs": int(os.getenv("GDACS_POLL_SECONDS", "900"))}
KEYS = ["id", "source", "source_id", "name", "category", "status", "severity", "severity_basis", "alert_level", "lat", "lng", "precision",
        "summary", "source_url", "event_time", "updated_at", "retrieved_at", "data_origin", "magnitude"]

def _ok(lat, lng):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lng)) and -90 <= lat <= 90 and -180 <= lng <= 180
def _https(u): return u if isinstance(u, str) and u.startswith("https://") else None
def _ts(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp())
    except Exception:
        return None

def norm_usgs(f, now):
    p, c = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or []
    if len(c) < 2 or not f.get("id") or p.get("time") is None or not _ok(c[1], c[0]): return None
    mag, alert = p.get("mag"), (p.get("alert") or "").lower() or None
    if alert in ALERT_SEV: sev, basis = ALERT_SEV[alert], "usgs_pager"
    else: sev, basis = ("high" if (mag or 0) >= 7 else "medium" if (mag or 0) >= 6 else "low"), "magnitude"
    depth = f" Depth {c[2]} km." if len(c) > 2 and c[2] is not None else ""
    return {"id": f"usgs-{f['id']}", "source": "usgs", "source_id": f["id"], "name": p.get("title") or p.get("place") or "Earthquake",
            "category": "earthquake", "status": "reported", "severity": sev, "severity_basis": basis, "alert_level": alert, "lat": c[1], "lng": c[0],
            "precision": "point", "summary": f"{p.get('title') or p.get('place')}.{depth} Source-reported, not independently verified.",
            "source_url": _https(p.get("url")), "event_time": int(p["time"] / 1000), "updated_at": int(p["updated"] / 1000) if p.get("updated") else None,
            "retrieved_at": now, "data_origin": "live:usgs", "magnitude": mag}

def norm_gdacs(f, now):
    p, g = {str(k).lower(): v for k, v in (f.get("properties") or {}).items()}, f.get("geometry") or {}
    c = g.get("coordinates") or []
    if g.get("type") != "Point" or len(c) < 2 or not _ok(c[1], c[0]) or not p.get("eventid") or p.get("eventtype") not in CATS: return None
    alert = str(p.get("alertlevel") or "").lower() or None
    cur = str(p.get("iscurrent")).lower() != "false"
    sev = (p.get("severitydata") or {}).get("severitytext") if isinstance(p.get("severitydata"), dict) else None
    url = p.get("url") if isinstance(p.get("url"), dict) else {}
    return {"id": f"gdacs-{p['eventtype']}-{p['eventid']}", "source": "gdacs", "source_id": f"{p['eventtype']}-{p['eventid']}",
            "name": p.get("name") or p.get("eventname") or CATS[p["eventtype"]], "category": CATS[p["eventtype"]], "status": "active" if cur else "resolved",
            "severity": ALERT_SEV.get(alert, "unrated") if alert in ("red", "orange", "green") else "unrated", "severity_basis": "gdacs_alert",
            "alert_level": alert, "lat": c[1], "lng": c[0], "precision": "point",
            "summary": (p.get("description") or p.get("htmldescription") or "") + (f" {sev}." if sev else ""), "source_url": _https(url.get("report")),
            "event_time": _ts(p.get("fromdate")), "updated_at": _ts(p.get("datemodified")), "retrieved_at": now, "data_origin": "live:gdacs", "magnitude": None}

def haversine(a, b, c, d):
    r = math.radians; x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(x))

def is_dupe(a, b, km=150, secs=7200):
    return a["category"] == b["category"] and a["source"] != b["source"] and a.get("event_time") and b.get("event_time") \
        and abs(a["event_time"] - b["event_time"]) <= secs and haversine(a["lat"], a["lng"], b["lat"], b["lng"]) <= km

async def _get(client, url, params=None, tries=3):
    for n in range(tries):
        try:
            r = await client.get(url, params=params, headers=UA); r.raise_for_status(); return r.json()
        except Exception:
            if n == tries - 1: raise
            await asyncio.sleep(2 ** n)

async def fetch_usgs(client, now):
    feats = (await _get(client, USGS_URL)).get("features", [])
    items = [x for x in (norm_usgs(f, now) for f in feats) if x]
    return items, len(feats) - len(items)

async def fetch_gdacs(client, now):
    # Endpoint + lowercase params (eventlist, fromdate, todate, alertlevel) per the official GDACS API quickstart.
    # pageSize/pageNumber come from a third-party client and are unverified; the loop stops at a short page.
    t, feats = datetime.now(timezone.utc), []
    for page in range(1, 6):
        prm = {"eventlist": "EQ;TC;FL;VO;WF;DR", "alertlevel": "red;orange;green", "fromdate": (t - timedelta(days=14)).strftime("%Y-%m-%d"),
               "todate": t.strftime("%Y-%m-%d"), "pageSize": 100, "pageNumber": page}
        got = (await _get(client, GDACS_URL, prm)).get("features", []); feats += got
        if len(got) < 100: break
    items = [x for x in (norm_gdacs(f, now) for f in feats) if x]
    return items, len(feats) - len(items)

FETCH = {"usgs": fetch_usgs, "gdacs": fetch_gdacs}
SET = ", ".join(f"i.{k}=${k}" for k in KEYS if k != "id")

def store(items):
    """Upsert by stable id; a report of the same real event from another source is merged, not duplicated."""
    out = {"inserted": 0, "updated": 0, "merged": 0}
    for it in items:
        if q("MATCH (i:Incident {id:$id}) RETURN count(i)", {"id": it["id"]})[0][0]:
            q(f"MATCH (i:Incident {{id:$id}}) SET {SET}", {k: it.get(k) for k in KEYS}); out["updated"] += 1; continue
        t = it["event_time"] or it["retrieved_at"]
        near = q("MATCH (i:Incident) WHERE i.category=$c AND i.source IS NOT NULL AND i.source<>$s AND i.event_time>=$a AND i.event_time<=$b "
                 "RETURN i.id,i.source,i.category,i.lat,i.lng,i.event_time,i.also_reported_by", {"c": it["category"], "s": it["source"], "a": t - 7200, "b": t + 7200})
        dup = next((r for r in near if is_dupe(it, {"source": r[1], "category": r[2], "lat": r[3], "lng": r[4], "event_time": r[5]})), None)
        if dup:
            seen = set(filter(None, (dup[6] or "").split(",")))
            q("MATCH (i:Incident {id:$id}) SET i.also_reported_by=$v", {"id": dup[0], "v": ",".join(sorted(seen | {it["id"]}))}); out["merged"] += 1; continue
        q(f"MERGE (i:Incident {{id:$id}}) SET {SET}, i.first_seen=$retrieved_at", {k: it.get(k) for k in KEYS}); out["inserted"] += 1
    return out

def _status(name, now, ok, err=None, n=0):
    if ok: q("MERGE (s:Source {id:$id}) SET s.last_attempt=$t, s.last_success=$t, s.last_error=null, s.last_count=$n", {"id": name, "t": now, "n": n})
    else: q("MERGE (s:Source {id:$id}) SET s.last_attempt=$t, s.last_error=$e", {"id": name, "t": now, "e": str(err)[:200]})

async def run_source(name):
    now = int(time.time())
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            items, rejected = await FETCH[name](c, now)
        res = await asyncio.to_thread(store, items)
        await asyncio.to_thread(_status, name, now, True, None, len(items))
        return {"source": name, "fetched": len(items), "rejected_invalid": rejected, **res}
    except Exception as e:
        log.exception("ingest %s failed", name)
        try: await asyncio.to_thread(_status, name, now, False, f"{type(e).__name__}: {e}")
        except Exception: log.exception("could not record failure for %s", name)
        return {"source": name, "error": f"{type(e).__name__}: {e}"}

last_run = {}
OWNER = f"{os.getpid()}-{time.time_ns()}"

def hold_lease(ttl=120):
    """Only one process may run the scheduler: a lease node in FalkorDB, renewed each cycle. One query = atomic."""
    now = int(time.time())
    q("MERGE (l:Lease {id:'scheduler'}) ON CREATE SET l.until=0, l.owner=''")
    return bool(q("MATCH (l:Lease {id:'scheduler'}) WHERE l.until<$n OR l.owner=$o SET l.owner=$o, l.until=$u RETURN l.owner", {"n": now, "o": OWNER, "u": now + ttl}))

async def scheduler():
    from . import agent, discover
    while True:
        try:
            if await asyncio.to_thread(hold_lease):
                for n in FETCH:
                    if time.time() - last_run.get(n, 0) >= INTERVALS[n]:
                        last_run[n] = time.time(); await run_source(n)
                await agent.analyze_pending()
                await discover.discover_pending()
        except Exception:
            log.exception("scheduler cycle failed; will retry")
        await asyncio.sleep(30)
