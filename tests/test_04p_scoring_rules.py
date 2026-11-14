"""04p: the Fantrax scoring rules table (#473 brief 2, ADR-0023).

Runs on the committed league_info fixture, cut from the real payload by
scripts/make_fixtures.py: the default fill, an override, the category listed
in two groups, and each way the parse fails loud.
"""
import copy
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import pandas as pd
import pytest

lg = importlib.import_module("04p_fantrax_league_info")

FIXTURE = Path(__file__).parent / "fixtures" / "fantrax" / "league_info.json"
CAPTURED = pd.Timestamp("2026-11-12T12:00:00Z")
SEASON = "2026-2027"


@pytest.fixture
def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def rules(raw):
    return lg.parse_scoring_rules(raw, SEASON, CAPTURED)


def points(rules, category_id, position):
    row = rules[(rules["category_id"] == category_id) & (rules["position"] == position)]
    assert len(row) == 1
    return row["points"].iloc[0]


class TestShape:
    def test_every_category_for_every_position(self, rules):
        assert rules["category_id"].nunique() == 26
        assert len(rules) == 26 * len(lg.LEAGUE_POSITIONS)
        assert set(rules["position"]) == set(lg.LEAGUE_POSITIONS)

    def test_key_is_unique_and_columns_match_the_registry(self, rules):
        assert not rules.duplicated(["season_id", "category_id", "position"]).any()
        assert list(rules.columns) == lg.RULE_COLUMNS
        assert (rules["season_id"] == SEASON).all()
        assert str(rules["points"].dtype) == "float64"
        assert str(rules["captured_at"].dtype) == "datetime64[us, UTC]"

    def test_category_ids_keep_their_letters(self, rules):
        assert {"256g", "3218"} <= set(rules["category_id"])

    def test_groups_are_fantrax_blocks(self, rules):
        by_cat = rules.drop_duplicates("category_id").set_index("category_id")
        assert by_cat.loc["2900", "scoring_group"] == "Offense"
        assert by_cat.loc["3060", "scoring_group"] == "Defense"
        assert by_cat.loc["256g", "scoring_group"] == "Defense"


class TestDefaultFill:
    def test_a_category_without_an_override_scores_the_default_at_every_position(self, rules):
        for position in lg.LEAGUE_POSITIONS:
            assert points(rules, "3060", position) == 3.0      # Sacks
            assert points(rules, "2870", position) == 0.04     # Passing yards

    def test_short_names_that_collide_stay_apart(self, rules):
        assert points(rules, "2860", "QB") == 4.0      # TD: passing
        assert points(rules, "2880", "QB") == 6.0      # TD: receiving
        assert points(rules, "2870", "QB") == 0.04     # YDS: passing
        assert points(rules, "2890", "QB") == 0.1      # YDS: receiving


class TestOverride:
    def test_override_replaces_the_default_for_its_position_only(self, rules):
        assert points(rules, "2900", "TE") == 1.5      # Receptions
        for position in ("QB", "RB", "WR", "DL", "LB", "DB"):
            assert points(rules, "2900", position) == 1.0

    def test_defense_overrides_by_position(self, rules):
        assert points(rules, "3120", "DL") == 3.5      # Tackles, solo
        assert points(rules, "3120", "DB") == 2.5
        assert points(rules, "3120", "LB") == 2.0
        assert points(rules, "3110", "DL") == 1.75     # Tackles, assisted
        assert points(rules, "3110", "DB") == 1.25
        assert points(rules, "3110", "LB") == 1.0
        assert points(rules, "2770", "DB") == 3.0      # Passes defensed
        assert points(rules, "2770", "DL") == 2.0


class TestReturnYardsListedInBothGroups:
    def test_one_row_per_position(self, rules):
        assert (rules["category_id"] == "3218").sum() == len(lg.LEAGUE_POSITIONS)
        assert points(rules, "3218", "WR") == 0.1

    def test_the_first_block_names_the_group(self, rules):
        assert set(rules.loc[rules["category_id"] == "3218", "scoring_group"]) == {"Offense"}

    def test_different_points_in_the_second_group_fail(self, raw):
        bad = copy.deepcopy(raw)
        for block in bad["scoringSystem"]["scoringCategorySettings"]:
            for cfg in block["configs"]:
                if cfg["scoringCategory"]["id"] == "3218" and block["group"]["id"] == "1020":
                    cfg["points"] = 0.2
        with pytest.raises(ValueError, match="3218.*listed twice"):
            lg.parse_scoring_rules(bad, SEASON, CAPTURED)


class TestFailsLoud:
    def test_no_scoring_system(self, raw):
        bad = {k: v for k, v in raw.items() if k != "scoringSystem"}
        with pytest.raises(ValueError, match="scoringCategorySettings"):
            lg.parse_scoring_rules(bad, SEASON, CAPTURED)

    def test_unknown_position_code(self, raw):
        bad = copy.deepcopy(raw)
        bad["scoringSystem"]["scoringCategorySettings"][0]["configs"][0]["position"]["code"] = "KICKER"
        with pytest.raises(ValueError, match="unknown position code KICKER"):
            lg.parse_scoring_rules(bad, SEASON, CAPTURED)

    def test_unknown_group(self, raw):
        bad = copy.deepcopy(raw)
        bad["scoringSystem"]["scoringCategorySettings"][0]["group"]["id"] = "1030"
        with pytest.raises(ValueError, match="unknown group 1030"):
            lg.parse_scoring_rules(bad, SEASON, CAPTURED)

    def test_category_with_no_default(self, raw):
        bad = copy.deepcopy(raw)
        for block in bad["scoringSystem"]["scoringCategorySettings"]:
            block["configs"] = [c for c in block["configs"] if not (
                c["scoringCategory"]["id"] == "3120" and c["position"]["code"] == "DEFAULT")]
        with pytest.raises(ValueError, match="no DEFAULT points.*3120"):
            lg.parse_scoring_rules(bad, SEASON, CAPTURED)

    def test_points_that_are_not_a_number(self, raw):
        bad = copy.deepcopy(raw)
        bad["scoringSystem"]["scoringCategorySettings"][0]["configs"][0]["points"] = "1.5"
        with pytest.raises(ValueError, match="not a number"):
            lg.parse_scoring_rules(bad, SEASON, CAPTURED)
