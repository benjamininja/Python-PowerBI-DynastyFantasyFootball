"""`division_id` on the two pick tables (#110; ADR-0018 decision 8).

Fantrax's payload key is `divisionId`. The pick tables spell the column
`division_id`, the only name that was not snake_case. The rename happens
where the table's columns are made, so the parsed payload keeps Fantrax's key.
"""
import importlib
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "mouserat_trade-bud" / "backend"))

import etl_helpers as etl

rt = importlib.import_module("02d_fact_roster_transactions")

# Two divisions of two teams, two rounds: the parsed getDraftResults shape.
PICKS = pd.DataFrame({
    "divisionId": ["d1"] * 4 + ["d2"] * 4,
    "round": [1, 1, 2, 2] * 2,
    "pickNumber": [1, 2, 1, 2] * 2,
    "teamId": ["tA", "tB", "tB", "tA", "tC", "tD", "tD", "tC"],
    "scorerId": ["p1", "p2", "p3", None, "p5", "p6", "p7", "p8"],
    "overall_slot": [1, 2, 3, 4] * 2,
})
TEAMS = {"tA": "A01", "tB": "A02", "tC": "B01", "tD": "B02"}


class TestTheGrid:
    def test_the_grid_spells_it_division_id(self):
        grid = rt.build_draft_picks(PICKS, TEAMS, "2026-2027")
        assert "division_id" in grid.columns and "divisionId" not in grid.columns
        assert grid["division_id"].tolist() == ["d1"] * 4 + ["d2"] * 4

    def test_the_pick_ref_still_carries_the_division(self):
        grid = rt.build_draft_picks(PICKS, TEAMS, "2026-2027")
        assert grid["pick_ref"].tolist()[:2] == ["2026-2027|d1|S001", "2026-2027|d1|S002"]
        assert (grid["pick_ref"].str.split("|").str[1] == grid["division_id"]).all()

    def test_the_parsed_payload_keeps_fantraxs_key(self):
        before = PICKS.copy()
        grid = rt.build_draft_picks(PICKS, TEAMS, "2026-2027")
        pd.testing.assert_frame_equal(PICKS, before)
        assert rt.pick_refs("2026-2027", PICKS).tolist() == grid["pick_ref"].tolist()

    def test_the_snake_runs_inside_each_division(self):
        grid = rt.build_draft_picks(PICKS, TEAMS, "2026-2027")
        round2 = grid[grid["round"] == 2].set_index(["division_id", "pick_in_round"])
        assert round2["original_owner"].to_dict() == {
            ("d1", 1): "A02", ("d1", 2): "A01", ("d2", 1): "B02", ("d2", 2): "B01"}

    def test_the_snake_helper_keys_on_division_id(self):
        order = pd.DataFrame({"division_id": ["d1", "d1"], "pick_in_round": [1, 2],
                              "team_key": ["A01", "A02"]})
        out = etl.expand_snake_draft_order(order, 2)
        assert list(out.columns) == ["division_id", "round", "pick_in_round", "team_key"]


class TestThePublishedTables:
    def test_both_tables_carry_division_id(self):
        for name in ("fact_draft_pick", "fact_draft_pick_future"):
            cols = pd.read_parquet(REPO / "data" / f"{name}.parquet").columns
            assert "division_id" in cols and "divisionId" not in cols, name

    def test_trade_bud_values_a_pick_from_the_inventory(self):
        import data_access as da
        import pick_value

        inventory = da.draft_pick_inventory()
        assert inventory["division_id"].notna().all()
        for slotted in (True, False):
            row = inventory[inventory["is_slotted"] == slotted].iloc[0]
            assert pick_value.value_for_pick_row(row, inventory) > 0
