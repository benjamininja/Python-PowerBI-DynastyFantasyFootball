import sys
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parent.parent / "mouserat_trade-bud" / "backend"
sys.path.insert(0, str(_BACKEND))

import positional_strength as ps  # noqa: E402


def test_crosswalk_dedupe_picks_newest_resolved_in_any_row_order():
    cw = pd.DataFrame({
        "scorer_id": ["s1", "s2", "s3", "s4"],
        "gsis_id": ["g1", "g1", "g1", "g2"],
        "position_raw": ["DL", "LB", "DB", "QB"],
        "resolved_date": ["2026-01-01", "2026-03-01", None, None],
    })
    for frame in (cw, cw.iloc[::-1], cw.iloc[[2, 0, 3, 1]]):
        out = ps.crosswalk_one_per_gsis(frame).set_index("gsis_id")["position_raw"]
        assert out["g1"] == "LB"
        assert out["g2"] == "QB"


def test_crosswalk_dedupe_ties_break_by_scorer_id_and_nulls_last():
    cw = pd.DataFrame({
        "scorer_id": ["s2", "s1", "s3"], "gsis_id": ["g1"] * 3,
        "position_raw": ["LB", "DL", "DB"],
        "resolved_date": ["2026-01-01", "2026-01-01", None],
    })
    for frame in (cw, cw.iloc[::-1]):
        assert ps.crosswalk_one_per_gsis(frame)["position_raw"].tolist() == ["DL"]


def test_dim_position_dedupe_is_order_free(monkeypatch):
    dp = pd.DataFrame({
        "position_raw": ["DE", "DT"], "position_group": ["DL", "DL"],
        "side_of_ball_sort_order": [2, 2], "position_sort_order": [5, 5],
    })
    for frame in (dp, dp.iloc[::-1]):
        monkeypatch.setattr(ps.da, "read_parquet", lambda _name, f=frame: f)
        out = ps._position_sort_order()
        assert out["position_group"].tolist() == ["DL"]
        assert out["position_sort_order"].tolist() == [5]
