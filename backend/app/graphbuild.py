"""Incident-scoped graph payload builder.

Pure functions: no database, no network, no AI. The incident node is ALWAYS built from the
incident record itself, so an incident with zero stored relationships still yields a valid graph
(one node) instead of an empty one. Nothing is invented: every other node and edge comes from a row
that the database actually returned.
"""

NODE_PROPS = ("lat", "lng", "category", "verification", "source_url", "data_origin")
EDGE_PROPS = ("distance_km", "retrieved_at")
INCIDENT_PROPS = ("category", "severity", "source", "source_url", "data_origin", "lat", "lng",
                  "event_time", "retrieved_at", "alert_level", "precision")

N = 4 + len(NODE_PROPS)   # columns per node in a result row
E = 1 + len(EDGE_PROPS)   # columns per edge in a result row


def node_cols(v):
    return (f"{v}.id, labels({v})[0], coalesce({v}.name,{v}.category,{v}.id), coalesce({v}.status,''), "
            + ", ".join(f"{v}.{p}" for p in NODE_PROPS))


def edge_cols(e):
    return f"type({e}), " + ", ".join(f"{e}.{p}" for p in EDGE_PROPS)


ROW_COLS = node_cols("a") + ", " + edge_cols("e") + ", " + node_cols("b")


def _node(c):
    nid, ntype, label, status, *vals = c
    return {"id": nid, "type": ntype or "Unknown", "label": str(label if label is not None else nid),
            "status": status or "",
            "properties": {k: v for k, v in zip(NODE_PROPS, vals) if v is not None}}


def _incident_node(inc):
    return {"id": inc["id"], "type": "Incident", "label": str(inc.get("name") or inc["id"]),
            "status": inc.get("status") or "",
            "properties": {k: inc[k] for k in INCIDENT_PROPS if inc.get(k) is not None}}


def build_incident_graph(incident, rows):
    """rows: tuples laid out as ROW_COLS (node a, edge e, node b)."""
    nodes = {incident["id"]: _incident_node(incident)}
    edges = {}
    for r in rows:
        if len(r) < 2 * N + E:
            continue
        a, e, b = r[:N], r[N:N + E], r[N + E:2 * N + E]
        if a[0] is None or b[0] is None or e[0] is None:
            continue                      # malformed row: skip rather than crash or guess
        nodes.setdefault(a[0], _node(a))
        nodes.setdefault(b[0], _node(b))
        edges.setdefault((a[0], e[0], b[0]),
                         {"from": a[0], "to": b[0], "type": e[0],
                          "properties": {k: v for k, v in zip(EDGE_PROPS, e[1:]) if v is not None}})
    ordered = [edges[k] for k in sorted(edges)]
    warnings = []
    if not ordered:
        warnings.append("No relationships are stored for this incident yet. Nothing has been invented to fill the graph.")
    if incident.get("discovery_status") == "failed":
        warnings.append("Facility discovery failed, so nearby facilities are missing from this graph.")
    return {"incident_id": incident["id"], "nodes": list(nodes.values()), "edges": ordered,
            "metadata": {"data_status": "partial" if ordered else "incident_only", "warnings": warnings}}
