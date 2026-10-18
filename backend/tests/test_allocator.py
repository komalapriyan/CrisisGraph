from app.allocator import allocate

NEEDS = [{"id":"n1","category":"water","qty":350,"priority":3,"location":"V"},
         {"id":"n2","category":"water","qty":100,"priority":1,"location":"V"}]
ROWS = [{"need_id":n,"provider_id":"p","provider":"P","resource_id":"r1","stock":300,"road_id":"x","road":"X"} for n in ("n1","n2")]

def test_no_double_allocation():
    a, u = allocate(NEEDS, ROWS)
    assert sum(x["qty"] for x in a) <= 300

def test_priority_and_unmet():
    a, u = allocate(NEEDS, ROWS)
    assert a[0]["need_id"] == "n1" and a[0]["qty"] == 300
    assert {x["need_id"]: x["qty"] for x in u} == {"n1": 50, "n2": 100}

def test_no_route_means_unmet():
    a, u = allocate(NEEDS, [])
    assert a == [] and len(u) == 2
