"""Synthetic, clearly labelled demo data. MERGE keeps seeding idempotent."""
from .db import q

LOCS = [("velachery","Velachery",12.9815,80.2180),("adyar","Adyar",13.0012,80.2565),
        ("tambaram","Tambaram",12.9249,80.1000),("mylapore","Mylapore",13.0368,80.2676)]
ROADS = [("r_adyar_bridge","Adyar Bridge",["velachery","adyar"]),("r_gst","GST Road",["velachery","tambaram"]),
         ("r_omr","OMR Link",["adyar","mylapore"])]
PROVIDERS = [("p_food","Tambaram Food Bank",["r_adyar_bridge"]),("p_depot","Guindy Relief Depot",["r_gst","r_omr"]),
             ("p_med","Mylapore Clinic Network",["r_omr"])]
RES = [("res_water","p_food","water",300),("res_food","p_food","food",200),("res_water2","p_depot","water",150),
       ("res_med","p_med","medical",40)]
NEEDS = [("n1","velachery","water",350,3),("n2","adyar","food",120,2),("n3","adyar","medical",60,5),("n4","tambaram","food",90,1)]

DEMO_INCIDENT = "chennai-flood"

def _params():
    return {"incident": DEMO_INCIDENT, "locations": [x[0] for x in LOCS], "roads": [x[0] for x in ROADS],
            "providers": [x[0] for x in PROVIDERS], "resources": [x[0] for x in RES], "needs": [x[0] for x in NEEDS]}

# Each step matches ONLY demo nodes: exact demo ids AND a synthetic marker or a link to the synthetic incident.
_STEPS = [
    ("needs",     "MATCH (x:Need) WHERE x.id IN $needs AND x.verification='synthetic'"),
    ("resources", "MATCH (p:Provider)-[:OFFERS]->(x:Resource) WHERE p.id IN $providers AND p.verification='synthetic' AND x.id IN $resources"),
    ("roads",     "MATCH (p:Provider)-[:DELIVERS_VIA]->(x:Road) WHERE p.id IN $providers AND p.verification='synthetic' AND x.id IN $roads"),
    ("locations", "MATCH (i:Incident {id:$incident})-[:OCCURRED_AT]->(x:Location) WHERE i.data_origin='synthetic' AND x.id IN $locations"),
    ("providers", "MATCH (x:Provider) WHERE x.id IN $providers AND x.verification='synthetic'"),
    ("decisions", "MATCH (x:Decision) WHERE x.road IN $roads"),
    ("incident",  "MATCH (x:Incident {id:$incident}) WHERE x.data_origin='synthetic'"),
]

def remove_demo(apply=False):
    """Count (default) or delete the synthetic scenario. Live incidents, facilities, snapshots, sources and assessments are never matched."""
    counts, p = {}, _params()
    for name, match in _STEPS:
        counts[name] = (q(match + " RETURN count(DISTINCT x)", p) or [[0]])[0][0]
        if apply and counts[name]:
            q(match + " DETACH DELETE x", p)
    return counts

def reset():
    """Re-create ONLY the demo scenario. Never wipes live data (the old version deleted every unlisted node, including live facilities)."""
    remove_demo(apply=True)
    seed()

def seed():
    q("MERGE (i:Incident {id:'chennai-flood'}) SET i.name='Chennai flood (SIMULATED)', i.category='flood', "
      "i.status='simulated', i.severity='high', i.lat=13.0827, i.lng=80.2707, i.summary='Synthetic flood scenario for demo. Not live data.', i.data_origin='synthetic'")
    for id_, name, lat, lng in LOCS:
        q("MERGE (l:Location {id:$id}) SET l.name=$n, l.lat=$a, l.lng=$o "
          "WITH l MATCH (i:Incident {id:'chennai-flood'}) MERGE (i)-[:OCCURRED_AT]->(l)", {"id": id_, "n": name, "a": lat, "o": lng})
    for id_, name, locs in ROADS:
        q("MERGE (r:Road {id:$id}) SET r.name=$n, r.status='open'", {"id": id_, "n": name})
        for l in locs:
            q("MATCH (r:Road {id:$r}),(l:Location {id:$l}) MERGE (r)-[:LEADS_TO]->(l)", {"r": id_, "l": l})
    for id_, name, roads in PROVIDERS:
        q("MERGE (p:Provider {id:$id}) SET p.name=$n, p.status='active', p.verification='synthetic'", {"id": id_, "n": name})
        for r in roads:
            q("MATCH (p:Provider {id:$p}),(r:Road {id:$r}) MERGE (p)-[:DELIVERS_VIA]->(r)", {"p": id_, "r": r})
    for id_, prov, cat, qty in RES:
        q("MATCH (p:Provider {id:$p}) MERGE (r:Resource {id:$id}) SET r.category=$c, r.qty=$q MERGE (p)-[:OFFERS]->(r)",
          {"id": id_, "p": prov, "c": cat, "q": qty})
    for id_, loc, cat, qty, pri in NEEDS:
        q("MATCH (l:Location {id:$l}) MERGE (n:Need {id:$id}) SET n.category=$c, n.qty=$q, n.priority=$p, n.verification='synthetic' "
          "MERGE (l)-[:HAS_NEED]->(n)", {"id": id_, "l": loc, "c": cat, "q": qty, "p": pri})


if __name__ == "__main__":
    # Dry run:  python -m app.seed          Delete demo data:  python -m app.seed --apply
    import sys
    from dotenv import load_dotenv; load_dotenv()
    apply = "--apply" in sys.argv
    print(("DELETED" if apply else "DRY RUN (nothing deleted); would delete"), remove_demo(apply))
