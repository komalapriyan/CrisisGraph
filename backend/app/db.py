import os
from falkordb import FalkorDB

_graph = None

def graph():
    """One managed connection; raises a clear error instead of faking data."""
    global _graph
    if _graph is None:
        try:
            c = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")),
                         username=os.getenv("FALKORDB_USERNAME") or None, password=os.getenv("FALKORDB_PASSWORD") or None)
            g = c.select_graph(os.getenv("FALKORDB_GRAPH", "crisisgraph"))
            g.query("RETURN 1")
            _graph = g
        except Exception as e:
            raise RuntimeError(f"Cannot reach FalkorDB ({e}). Run: docker compose -f infra/docker-compose.yml up -d")
    return _graph

def q(cypher, params=None):
    return graph().query(cypher, params or {}).result_set
