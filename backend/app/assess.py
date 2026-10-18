"""Transparent rule-based needs assessment. It names likely need categories and priorities;
it never invents quantities, populations or stock. v1 heuristic, not an official assessment."""
RULES = {
    "earthquake": [("search and rescue", 3, "collapsed structures are the main early risk"), ("medical", 3, "crush injuries and trauma"), ("shelter", 2, "damaged housing and aftershocks"), ("water", 2, "pipe and treatment damage")],
    "flood": [("water", 3, "contamination of drinking water"), ("shelter", 3, "displacement"), ("food", 2, "supply routes cut"), ("medical", 2, "waterborne disease and injuries")],
    "cyclone": [("shelter", 3, "wind and surge damage"), ("water", 2, "supply disruption"), ("food", 2, "access loss"), ("medical", 2, "injuries and disease")],
    "wildfire": [("shelter", 3, "evacuations"), ("medical", 2, "smoke inhalation and burns"), ("water", 1, "supply for evacuees")],
    "volcano": [("shelter", 2, "evacuation zones"), ("medical", 2, "respiratory effects of ash"), ("water", 2, "ash contamination")],
    "drought": [("water", 3, "scarcity"), ("food", 3, "crop loss")],
}
LEVEL = {1: "low", 2: "medium", 3: "high"}
BUMP = {"critical": 1, "high": 0, "medium": 0, "low": -1}
GAPS = ["affected population", "damage assessment", "verified local stock", "road access", "hospital capacity", "official situation reports"]

def assess(inc):
    rules = RULES.get(inc.get("category"))
    if not rules:
        return {"basis": "No rule for this category; no assessment made.", "needs": [], "data_gaps": GAPS, "quantities": None, "planner": None}
    b = BUMP.get(inc.get("severity"), 0)
    needs = [{"category": c, "priority": LEVEL[max(1, min(3, p + b))], "reason": r} for c, p, r in rules]
    return {"basis": f"Rule-based heuristic v1 from category '{inc['category']}' and severity '{inc.get('severity') or 'unrated'}'. Not an official assessment.",
            "inputs_used": {k: inc.get(k) for k in ("category", "severity", "alert_level", "magnitude")}, "needs": needs, "data_gaps": GAPS, "quantities": None,
            "planner": "simulation" if inc.get("data_origin") == "synthetic" else None}
