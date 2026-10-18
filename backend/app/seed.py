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

def reset():
    q("MATCH (n) WHERE NOT n:Snapshot AND NOT n:Source AND NOT n:Assessment AND NOT n:Lease AND NOT (n:Incident AND n.data_origin STARTS WITH 'live') DETACH DELETE n")  # keep history + live data
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
