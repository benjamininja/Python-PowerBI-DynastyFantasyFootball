"""dim_scoring_category: the Category Groups and the nflverse map (#473 brief 3, ADR-0023).

Runs on the published tables. Every category of the rules table has a row
here; every nflverse_columns entry is plus-joined column names; the groups are
the seven, sorted 1 to 7. A group with no scored category is reported, not
failed.
"""
import re
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "notebooks"))

import etl_helpers as etl

GROUPS = ["Passing", "Rushing", "Receiving", "Special teams",
          "Defense, tackles", "Defense, big plays", "Other"]
COLUMN_LIST = re.compile(r"^[a-z][a-z0-9_]*(\+[a-z][a-z0-9_]*)*$")


@pytest.fixture(scope="module")
def categories():
    return etl.read_table("dim_scoring_category")


@pytest.fixture(scope="module")
def rules():
    return etl.read_table("dim_fantrax_scoring_rule")


def test_every_rules_category_has_a_row(categories, rules):
    missing = sorted(set(rules["category_id"]) - set(categories["category_id"]))
    assert missing == [], f"rules categories with no dim_scoring_category row: {missing}"


def test_every_row_is_a_rules_category(categories, rules):
    extra = sorted(set(categories["category_id"]) - set(rules["category_id"]))
    assert extra == [], f"rows no rules season holds: {extra}"


def test_category_id_is_unique(categories):
    assert not categories["category_id"].duplicated().any()


def test_every_nflverse_columns_entry_parses(categories):
    entries = categories["nflverse_columns"].dropna()
    bad = sorted(e for e in entries if not COLUMN_LIST.match(e))
    assert bad == [], f"nflverse_columns not plus-joined column names: {bad}"


def test_no_column_is_named_twice_in_one_entry(categories):
    for entry in categories["nflverse_columns"].dropna():
        names = entry.split("+")
        assert len(names) == len(set(names)), entry


def test_the_groups_are_the_seven_in_order(categories):
    assert set(categories["category_group"]) <= set(GROUPS)
    order = dict(zip(categories["category_group"], categories["group_sort_order"]))
    assert all(order[g] == GROUPS.index(g) + 1 for g in order)


def test_the_unit_follows_context_md(categories, rules):
    block = rules.drop_duplicates("category_id").set_index("category_id")["scoring_group"]
    for row in categories.itertuples():
        expected = "Special Teams" if row.category_group == "Special teams" else block[row.category_id]
        assert row.unit == expected, row.category_id


def test_code_and_name_are_read_from_the_rules(categories, rules):
    newest = (rules.sort_values("season_id", ascending=False, kind="stable")
                   .drop_duplicates("category_id").set_index("category_id"))
    for row in categories.itertuples():
        assert row.category_code == newest.at[row.category_id, "category_code"]
        assert row.category_name == newest.at[row.category_id, "category_name"]


def test_each_group_holds_a_scored_category(categories, rules):
    scored = set(rules.loc[rules["points"] != 0, "category_id"])
    held = set(categories.loc[categories["category_id"].isin(scored), "category_group"])
    empty = [g for g in GROUPS if g not in held]
    if empty:
        warnings.warn(f"Category Groups with no scored category: {empty}")
