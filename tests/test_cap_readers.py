"""The bot's cap readers (#97, ADR-0016 decisions 1 and 4): capmath reads the
published tables and recomputes nothing. Every frame here holds figures that
match no sum of its sources, so a reader that did any arithmetic would fail.
The cap rules themselves are tested where they live, in
tests/test_02h_fact_team_cap.py."""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "discord_bot"))

import pandas as pd
import pytest

import capmath
from config import Config

CFG = Config(discord_bot_token="x", discord_guild_id=1, github_pat="x", github_owner="o",
             github_repo="r", github_ref="main", command_prefix="!")

THIS, NEXT = "2026-2027", "2027-2028"

TEAMS = pd.DataFrame({"team_key": ["A01", "B01"],
                      "original_cap": [300.0, 310.0],
                      "reinvestment_cap": [7.0, 0.0]})

# Neither row's cap_room is original_cap less its other figures, and the
# table's original_cap and reinvestment_cap differ from the dimension's.
CAP = pd.DataFrame({
    "season_id":        [THIS, THIS, NEXT, NEXT],
    "team_key":         ["A01", "B01", "A01", "B01"],
    "is_current_season": [True, True, False, False],
    "original_cap":     [1.0, 1.0, 1.0, 1.0],
    "reinvestment_cap": [2.0, 2.0, 2.0, 2.0],
    "charged_salary":   [111.0, 222.0, 333.0, 444.0],
    "ir_salary":        [11.0, 22.0, 0.0, 0.0],
    "minors_salary":    [5.0, 6.0, 0.0, 0.0],
    "dead_money":       [10.0, 20.0, 8.0, 4.0],
    "cap_room":         [1001.0, 1002.0, 1003.0, 1004.0],
})

ROSTER = pd.DataFrame({
    "team_key":       ["A01", "A01", "A01"],
    "contract_id":    ["1st", "Minor", "1st"],
    "contract_value": [10.0, 2.0, 6.0],
    "roster_status":  ["Active", "Minors", "Inj Res"],
    "cap_hit":        [7.0, 99.0, 3.0],
    "cap_exempt":     [False, False, True],
})


@pytest.fixture
def tables(monkeypatch):
    frames = {"dim_fantasy_teams.parquet": TEAMS, "fact_fantasy_teams.parquet": ROSTER,
              "fact_team_cap.parquet": CAP}

    def serve(**swap):
        frames.update({f"{k}.parquet": v for k, v in swap.items()})
        monkeypatch.setattr(capmath, "fetch_parquet",
                            lambda path, _cfg: frames[Path(path).name].copy())
    serve()
    return serve


class TestRosterWithCapHit:
    def test_the_stored_roster_comes_back_whole(self, tables):
        pd.testing.assert_frame_equal(capmath.roster_with_cap_hit(CFG), ROSTER)

    def test_a_stored_cap_hit_is_not_the_contract_value_or_a_slot_rule(self, tables):
        got = capmath.roster_with_cap_hit(CFG)
        assert got["cap_hit"].tolist() == [7.0, 99.0, 3.0]          # none equals contract_value
        assert got["cap_exempt"].tolist() == [False, False, True]   # not derived from the slot

    def test_editing_the_result_leaves_the_cached_frame_alone(self, monkeypatch):
        cached = ROSTER.copy()
        monkeypatch.setattr(capmath, "fetch_parquet", lambda path, _cfg: cached)
        got = capmath.roster_with_cap_hit(CFG)
        assert got is not cached
        got.loc[0, "cap_hit"] = -1.0
        assert cached["cap_hit"].tolist() == [7.0, 99.0, 3.0]

    def test_an_empty_roster_comes_back_empty(self, tables):
        tables(fact_fantasy_teams=ROSTER.iloc[0:0])
        assert capmath.roster_with_cap_hit(CFG).empty


class TestTeamsWithCap:
    def rows(self):
        return capmath.teams_with_cap(CFG).set_index("team_key")

    def test_this_seasons_row_maps_to_the_current_names(self, tables):
        a = self.rows().loc["A01"]
        assert a["active_roster_salary"] == 111.0
        assert a["remaining_cap_current_yr"] == 1001.0
        assert a["dead_money"] == 10.0
        assert a["ir_salary"] == 11.0
        assert a["minors_salary"] == 5.0

    def test_the_other_row_maps_to_the_next_year_names(self, tables):
        a = self.rows().loc["A01"]
        assert a["remaining_cap_next_yr"] == 1003.0
        assert a["dead_money_next_yr"] == 8.0
        b = self.rows().loc["B01"]
        assert (b["remaining_cap_current_yr"], b["remaining_cap_next_yr"]) == (1002.0, 1004.0)
        assert (b["ir_salary"], b["dead_money_next_yr"]) == (22.0, 4.0)

    def test_the_next_seasons_charge_is_not_read_as_this_seasons(self, tables):
        a = self.rows().loc["A01"]
        assert a["active_roster_salary"] != 333.0
        assert a["dead_money"] != a["dead_money_next_yr"]

    def test_the_dimensions_caps_stay(self, tables):
        t = self.rows()
        assert t["original_cap"].to_dict() == {"A01": 300.0, "B01": 310.0}
        assert t["reinvestment_cap"].to_dict() == {"A01": 7.0, "B01": 0.0}
        assert not [c for c in t.columns if c.endswith(("_x", "_y"))]

    def test_only_the_named_columns_are_added(self, tables):
        got = set(capmath.teams_with_cap(CFG).columns) - set(TEAMS.columns)
        assert got == {"active_roster_salary", "remaining_cap_current_yr", "dead_money",
                       "ir_salary", "minors_salary", "remaining_cap_next_yr",
                       "dead_money_next_yr"}

    def test_the_season_comes_from_the_flag_not_the_row_order_or_the_label(self, tables):
        tables(fact_team_cap=CAP.iloc[::-1].assign(season_id=lambda d: d["season_id"].str[::-1]))
        a = self.rows().loc["A01"]
        assert (a["remaining_cap_current_yr"], a["remaining_cap_next_yr"]) == (1001.0, 1003.0)

    def test_nothing_is_filled_in_for_a_missing_row(self, tables):
        tables(fact_team_cap=CAP[~((CAP["team_key"] == "B01") & ~CAP["is_current_season"])])
        b = self.rows().loc["B01"]
        assert pd.isna(b["remaining_cap_next_yr"]) and pd.isna(b["dead_money_next_yr"])
        assert b["remaining_cap_current_yr"] == 1002.0

    def test_a_team_twice_on_one_season_fails(self, tables):
        tables(fact_team_cap=pd.concat([CAP, CAP.iloc[[0]]]))
        with pytest.raises(pd.errors.MergeError):
            capmath.teams_with_cap(CFG)

    def test_no_teams_come_back_empty(self, tables):
        tables(dim_fantasy_teams=TEAMS.iloc[0:0])
        assert capmath.teams_with_cap(CFG).empty


class TestNoArithmetic:
    def test_capmath_holds_no_arithmetic(self):
        tree = ast.parse((REPO / "discord_bot" / "capmath.py").read_text(encoding="utf-8"))
        ops = [type(n).__name__ for n in ast.walk(tree)
               if isinstance(n, (ast.BinOp, ast.AugAssign, ast.UnaryOp))]
        assert ops == []

    def test_capmath_reads_no_table_but_the_three(self):
        text = (REPO / "discord_bot" / "capmath.py").read_text(encoding="utf-8")
        assert "fact_dead_money" not in text and "cap_hit_pct" not in text
