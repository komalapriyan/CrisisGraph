"""Geographic resource discovery for LIVE incidents: OpenStreetMap Overpass -> Facility nodes -> incident graph.
Root cause this fixes: only seed.py ever created Location/Road/Provider/Resource edges, so live incidents had none.
Mapped facilities are NOT claimed to be operating, staffed or stocked. Roads are not inferred (no reliable status source yet)."""
import os, time, json, hashlib, asyncio, logging
import httpx
from .db import q
from .ingest import haversine
from . import graphbuild

log = logging.getLogger("discover")
OVERPASS_URLS = [u.strip() for u in os.getenv("OVERPASS_URLS", "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter").split(",") if u.strip()]
RADIUS_KM = float(os.getenv("OSM_RADIUS_KM", "20"))
MAX_FAC = int(os.getenv("OSM_MAX_FACILITIES", "40"))
RETRY_AFTER, REFRESH_AFTER = 600, 7 * 86400
UA = {"User-Agent": "CrisisGraph/0.1 (hackathon prototype)"}
OSM = {"hospital": ("amenity", "hospital"), "clinic": ("amenity", "clinic"), "pharmacy": ("amenity", "pharmacy"),
       "fire_station": ("amenity", "fire_station"), "police": ("amenity", "police"), "assembly_point": ("emergency", "assembly_point")}
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

def build_query(lat, lng, radius_m):
    parts = "".join(f'nwr["{k}"="{v}"](around:{int(radius_m)},{lat},{lng});' for k, v in OSM.values())
    return f"[out:json][timeout:25];({parts});out center tags 300;"

def parse(elements, lat, lng, now, cap=MAX_FAC):
    out = {}
    for el in elements or []:
        tags = el.get("tags") or {}
        cat = next((c for c, (k, v) in OSM.items() if tags.get(k) == v), None)
        c = el.get("center") or el
        la, lo = c.get("lat"), c.get("lon")
        if not cat or not isinstance(la, (int, float)) or not isinstance(lo, (int, float)) or not (-90 <= la <= 90 and -180 <= lo <= 180) or not el.get("id") or not el.get("type"): continue
        web = tags.get("website") or tags.get("contact:website")
        out[f"osm-{el['type']}-{el['id']}"] = {"id": f"osm-{el['type']}-{el['id']}", "name": tags.get("name") or f"Unnamed {cat.replace('_', ' ')}", "category": cat, "lat": la, "lng": lo,
            "distance_km": round(haversine(lat, lng, la, lo), 2), "source_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}", "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": web if isinstance(web, str) and web.startswith(("http://", "https://")) else None, "retrieved_at": now, "verification": "osm_mapped_unverified"}
    return sorted(out.values(), key=lambda f: f["distance_km"])[:cap]

def persist(inc, ents, now):
    """Idempotent: base graph (offline) + facilities; stale NEAR edges from earlier runs are removed."""
    specs = graphbuild.ensure_base_graph(inc)
    graphbuild.link_facilities(inc, ents, specs, now)

def _err(e):
    name = type(e).__name__; msg = str(e).strip()
    if isinstance(e, (httpx.TimeoutException,)) or not msg: return f"{name}: Overpass did not answer in time (public servers are often busy)"[:200]
    return f"{name}: {msg}"[:200]

async def _overpass(lat, lng, radius_km):
    """Try each mirror in turn; raise the last error if all fail."""
    last = None
    for url in OVERPASS_URLS:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(70, connect=10), headers=UA) as c:
                r = await c.post(url, data={"data": build_query(lat, lng, radius_km * 1000)}); r.raise_for_status()
                return r.json().get("elements")
        except Exception as e:
            last = e; log.warning("overpass mirror %s failed: %s", url, type(e).__name__)
    raise last

def _hash(inc): return hashlib.sha256(f"{round(inc['lat'], 2)}|{round(inc['lng'], 2)}|{inc['category']}|{RADIUS_KM}".encode()).hexdigest()[:12]
def _mark(iid, status, h, err=None):
    q("MATCH (i:Incident {id:$i}) SET i.discovery_status=$s, i.discovery_hash=$h, i.discovery_at=$n, i.discovery_error=$e", {"i": iid, "s": status, "h": h, "n": int(time.time()), "e": err})

async def discover_incident(inc, force=False):
    """'ok' | 'failed' | 'skipped'. Never raises. The base graph is built FIRST so it exists even if Overpass is down."""
    try: await asyncio.to_thread(graphbuild.ensure_base_graph, inc)
    except Exception: log.exception("base graph failed for %s", inc.get("id"))
    h, now = _hash(inc), int(time.time())
    st, at, prev = inc.get("discovery_status"), inc.get("discovery_at") or 0, inc.get("discovery_hash")
    if not force and prev == h and ((st == "ok" and now - at < REFRESH_AFTER) or (st == "failed" and now - at < RETRY_AFTER)): return "skipped"
    try:
        try: els = await _overpass(inc["lat"], inc["lng"], RADIUS_KM)
        except Exception as first:
            if not isinstance(first, httpx.TimeoutException) or RADIUS_KM <= 10: raise
            els = await _overpass(inc["lat"], inc["lng"], 10)          # busy server: retry with a smaller area
        ents = parse(els, inc["lat"], inc["lng"], now)
        await asyncio.to_thread(persist, inc, ents, now); await asyncio.to_thread(_mark, inc["id"], "ok", h); return "ok"
    except Exception as e:
        log.exception("discovery failed for %s", inc.get("id"))
        try: await asyncio.to_thread(_mark, inc["id"], "failed", h, _err(e))
        except Exception: log.exception("could not record discovery failure")
        return "failed"

F = ["id", "name", "category", "severity", "lat", "lng", "precision", "event_time", "discovery_status", "discovery_at", "discovery_hash"]
async def discover_pending(limit=2):
    try: await asyncio.to_thread(graphbuild.ensure_all)
    except Exception: log.exception("ensure_all failed")
    rows = q("MATCH (i:Incident) WHERE i.source IS NOT NULL AND i.lat IS NOT NULL RETURN " + ",".join("i." + f for f in F))
    incs = sorted((dict(zip(F, r)) for r in rows), key=lambda x: (SEV_RANK.get(x["severity"], 4), -(x["event_time"] or 0)))
    todo, res = [], {"ok": 0, "failed": 0, "skipped": 0}
    for inc in incs:
        if len(todo) >= limit: break
        now, st = int(time.time()), inc.get("discovery_status")
        if inc.get("discovery_hash") != _hash(inc) or st is None or (st == "ok" and now - (inc["discovery_at"] or 0) >= REFRESH_AFTER) or (st == "failed" and now - (inc["discovery_at"] or 0) >= RETRY_AFTER): todo.append(inc)
    for inc in todo:
        res[await discover_incident(inc)] += 1; await asyncio.sleep(2)   # be polite to the public Overpass server
    return res
