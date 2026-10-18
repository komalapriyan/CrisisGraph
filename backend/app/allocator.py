"""Deterministic allocation. The graph decides WHICH (need, provider, resource, road)
combinations are eligible; this code decides quantities. No LLM involved."""

def allocate(needs, rows):
    stock = {}
    for r in rows:
        stock.setdefault(r["resource_id"], r["stock"])
    allocations, unmet = [], []
    for n in sorted(needs, key=lambda x: (-x["priority"], x["id"])):
        remaining = n["qty"]
        for r in sorted((r for r in rows if r["need_id"] == n["id"]), key=lambda r: r["resource_id"]):
            if remaining <= 0:
                break
            take = min(remaining, stock[r["resource_id"]])
            if take <= 0:
                continue
            stock[r["resource_id"]] -= take  # never double-allocate stock
            remaining -= take
            allocations.append({"need_id": n["id"], "location": n["location"], "category": n["category"],
                "qty": take, "provider": r["provider"], "resource_id": r["resource_id"],
                "road": r["road"], "road_id": r["road_id"],
                "why": f"{r['provider']} stocks {n['category']} and reaches {n['location']} via open road {r['road']}."})
        if remaining > 0:
            unmet.append({"need_id": n["id"], "location": n["location"], "category": n["category"], "qty": remaining})
    return allocations, unmet
