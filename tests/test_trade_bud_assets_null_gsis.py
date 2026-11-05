import sys
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parent.parent / "mouserat_trade-bud" / "backend"
sys.path.insert(0, str(_BACKEND))

try:
    import fastapi  # noqa: F401
except ImportError:
    import types

    class _Router:
        def __init__(self, *a, **k):
            pass

        def get(self, *a, **k):
            return lambda fn: fn

    _stub = types.ModuleType("fastapi")
    _stub.APIRouter = _Router
    sys.modules["fastapi"] = _stub

from routers import assets  # noqa: E402


def _tables():
    return {
        "dim_nfl_players": pd.DataFrame({
            "gsis_id": ["g1", None],
            "display_name": ["Real Player", "Null Key Player"],
            "position": ["QB", "WR"],
            "position_group": ["QB", "WR"],
            "team_abbr": ["AAA", "BBB"],
            "birth_date": ["2000-01-01", "2000-01-01"],
        }),
        "dim_fantrax_crosswalk": pd.DataFrame({
            "scorer_id": ["s1", "s2"],
            "gsis_id": ["g1", None],
            "position_raw": ["QB", "DL,LB"],
            "resolved_date": ["2026-01-01", "2026-01-01"],
        }),
        "dim_position": pd.DataFrame({
            "position_raw": ["QB", "WR"],
            "position_group": ["QB", "WR"],
            "side_of_ball_sort_order": [1, 1],
            "position_sort_order": [1, 2],
        }),
    }


def test_roster_row_without_gsis_id_takes_no_dim_or_crosswalk_values(monkeypatch):
    tables = _tables()
    roster = pd.DataFrame({
        "team_key": ["t1", "t1"],
        "gsis_id": ["g1", None],
        "cap_hit": [1.0, 1.0],
        "cap_exempt": [False, False],
        "roster_slot": ["active", "active"],
        "contract_value": [1, 1],
    })
    monkeypatch.setattr(assets.da, "read_parquet", lambda name: tables[name])
    monkeypatch.setattr(assets.da, "roster_with_cap_hit", lambda: roster)
    monkeypatch.setattr(assets, "_values_by_stance", lambda: {s: {} for s in assets.da.STANCES})
    monkeypatch.setattr(
        assets.da, "draft_pick_inventory",
        lambda: pd.DataFrame({
            "current_owner": [], "is_made": [], "is_slotted": [],
            "pick_ref": [], "draft_season": [], "round": [],
        }),
    )

    players = assets.team_assets("t1")["players"]
    by_id = {p["asset_id"]: p for p in players}
    real = by_id["g1"]
    orphan = [p for p in players if p["asset_id"] is None or pd.isna(p["asset_id"])][0]

    assert real["position"] == "QB"
    assert real["name"] == "Real Player"
    assert pd.isna(orphan["position"])
    assert pd.isna(orphan["name"])
    assert pd.isna(orphan["nfl_team"])
