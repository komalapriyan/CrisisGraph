from app.main import bucketize

def test_bucketize_last_observation_and_gaps():
    now = 10 * 3600 + 5
    rows = [(8 * 3600 + 10, 5), (8 * 3600 + 20, 7), (10 * 3600 + 1, 2)]
    b = bucketize(rows, 3600, 3, now)
    assert b[0]["t"] == 8 * 3600
    assert [x["value"] for x in b] == [7, None, 2]   # gap stays None, never 0

def test_old_rows_ignored():
    assert all(x["value"] is None for x in bucketize([(0, 9)], 3600, 3, 10 * 3600))
