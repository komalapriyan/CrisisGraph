"""Universal incident graph builder. Deterministic and OFFLINE: every valid incident gets
Incident -[:OCCURRED_AT]-> Area and Incident -[:REQUIRES]-> Requirement, whether or not AI or facility discovery worked.
Requirements come from the stored Gemini assessment when it succeeded, else from the labelled rule fallback.
Nothing here claims a road is blocked, a facility operates, or stock exists."""
import re, logging
from .db import q
from .assess import assess

log = logging.getLogger("graphbuild")
NEED_TO_FACILITY = {"medical": ["hospital", "clinic", "pharmacy"], "search and rescue": ["fire_station"], "shelter": ["assembly_point"]}
KW = [(("medical", "hospital", "injur", "trauma", "health", "clinic", "pharm", "ambulance"), ["hospital", "clinic", "pharmacy"]),
      (("rescue", "fire", "search"), ["fire_station"]), (("shelter", "evacu", "housing", "assembly"), ["assembly_point"])]
COLS = ["id", "name", "category", "severity", "alert_level", "magnitude", "data_origin", "lat", "lng", "precision"]

def valid(inc):
    la, lo = inc.get("lat"), inc.get("lng")
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (la, lo)) and -90 <= la <= 90 and -180 <= lo <= 180

def fac_types(text):
    t = text.lower(); out = []
    for words, cats in KW:
        if any(w in t for w in words): out += [c for c in cats if c not in out]
    return out

def requirement_specs(inc):
    try:
        from . import agent
        st = agent.get_stored(inc["id"])
        needs = ((st.get("data") or {}).get("resource_needs") if st.get("status") == "ok" else None) or []
        if needs: return [{"category": n["resource"][:80], "priority": n["priority"], "reason": n["reason"], "basis": "gemini", "fac": fac_types(n["resource"] + " " + n["reason"])} for n in needs]
    except Exception as e:
        log.debug("no AI needs for %s (%s); using rules", inc.get("id"), type(e).__name__)
    return [{"category": n["category"], "priority": n["priority"], "reason": n["reason"], "basis": "rules_v1", "fac": NEED_TO_FACILITY.get(n["category"], [])} for n in assess(inc)["needs"]]

def ensure_base_graph(inc):
    """Idempotent. Returns the requirement specs, or None if coordinates are invalid (then nothing is written)."""
    if not valid(inc): return None
    iid = inc["id"]
    q("MATCH (i:Incident {id:$i}) MERGE (a:Area {id:$a}) SET a.name=$n, a.lat=$la, a.lng=$lo, a.precision=$p, a.basis='event_coordinates' MERGE (i)-[:OCCURRED_AT]->(a)",
      {"i": iid, "a": f"area-{iid}", "n": (inc.get("name") or iid)[:80], "la": inc["lat"], "lo": inc["lng"], "p": inc.get("precision") or "point"})
    specs, ids = requirement_specs(inc), []
    for sp in specs:
        sp["id"] = rid = f"req-{iid}-{re.sub(r'[^a-z0-9]+', '_', sp['category'].lower()).strip('_')[:40]}"; ids.append(rid)
        q("MATCH (i:Incident {id:$i}) MERGE (r:Requirement {id:$r}) SET r.category=$c, r.priority=$p, r.reason=$why, r.basis=$b, r.quantity='not_estimated' MERGE (i)-[:REQUIRES]->(r)",
          {"i": iid, "r": rid, "c": sp["category"], "p": sp["priority"], "why": sp["reason"][:300], "b": sp["basis"]})
    q("MATCH (r:Requirement) WHERE r.id STARTS WITH $pre AND NOT r.id IN $ids DETACH DELETE r", {"pre": f"req-{iid}-", "ids": ids})
    return specs

def link_facilities(inc, ents, specs, now):
    iid = inc["id"]
    for f in ents:
        q("MERGE (f:Facility {id:$id}) SET f.name=$name, f.category=$category, f.lat=$lat, f.lng=$lng, f.source_url=$source_url, f.phone=$phone, f.website=$website, f.verification=$verification, f.status='unverified'", f)
        q("MATCH (i:Incident {id:$i}),(f:Facility {id:$f}) MERGE (i)-[r:NEAR]->(f) SET r.distance_km=$d, r.source='osm_overpass', r.retrieved_at=$t", {"i": iid, "f": f["id"], "d": f["distance_km"], "t": now})
    q("MATCH (i:Incident {id:$i})-[r:NEAR]->(f:Facility) WHERE NOT f.id IN $ids DELETE r", {"i": iid, "ids": [f["id"] for f in ents]})
    for sp in specs or []:
        for f in ents:
            if f["category"] in sp["fac"]:
                q("MATCH (f:Facility {id:$f}),(r:Requirement {id:$r}) MERGE (f)-[x:RELEVANT_TO]->(r) SET x.basis='osm_category_match', x.verified=false", {"f": f["id"], "r": sp["id"]})

def ensure_all(limit=50):
    """Cheap sweep: live incidents with no Area yet, or whose AI assessment succeeded after rule-based requirements were stored."""
    cols = ",".join("i." + c for c in COLS)
    rows = q("MATCH (i:Incident) WHERE i.source IS NOT NULL AND i.lat IS NOT NULL OPTIONAL MATCH (i)-[:OCCURRED_AT]->(a:Area) WITH i, a WHERE a IS NULL RETURN " + cols + " LIMIT $n", {"n": limit}) \
         + q("MATCH (i:Incident)-[:HAS_ASSESSMENT]->(s:Assessment {status:'ok'}) WHERE i.lat IS NOT NULL OPTIONAL MATCH (i)-[:REQUIRES]->(r:Requirement {basis:'gemini'}) WITH i, count(r) AS c WHERE c=0 RETURN " + cols + " LIMIT $n", {"n": limit})
    seen = {}
    for r in rows: seen[r[0]] = dict(zip(COLS, r))
    for inc in seen.values():
        try: ensure_base_graph(inc)
        except Exception: log.exception("base graph failed for %s", inc["id"])
    return len(seen)
