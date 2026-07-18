import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.scoring import global_risk, stock_score


def test_scoring():
    r = global_risk({"VIX":{"last":18,"change_pct":-1}}, {"items":[]})
    assert 0 <= r["score"] <= 100
    s = stock_score({"change_pct":2,"ma20_gap_pct":4,"volume_ratio":1.3}, 10, r["score"])
    assert 0 <= s["score"] <= 100


if __name__ == "__main__":
    test_scoring()
    print("smoke_test_ok")
