"""Keys and types on the registry (#108; ADR-0018 decisions 4, 6, 7, 8, 11).

`pk`, `fk`, `checks` and `other_tables` are what the migration generator turns
into DDL. The rule tests run on small dicts. The registry tests run on the
published `data/*.parquet`: every key is whole, every declared foreign key has
no orphan, every `integer` column is a whole number in range, every `date`
column is an ISO date. A failure here is a check failing on real data: fix the
data or park it, never drop the key.
"""
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import check_data_model as cdm

DATA = cdm.load_yaml()
TABLES = DATA["tables"]
OTHERS = DATA["other_tables"]
BY_NAME = {t["name"]: t for t in TABLES + OTHERS}
INT_MIN, INT_MAX = -(2 ** 31), 2 ** 31 - 1
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

FKS = [(t["name"], fk) for t in TABLES for fk in t.get("fk") or []]
INTEGERS = [(t["name"], c["name"]) for t in TABLES for c in t["columns"] if c["sql_type"] == "integer"]
DATES = [(t["name"], c["name"]) for t in TABLES for c in t["columns"] if c["sql_type"] == "date"]


@lru_cache(maxsize=None)
def published(name):
    return pd.read_parquet(REPO / "data" / f"{name}.parquet")


def fk_id(item):
    table, fk = item
    return f"{table}.{'+'.join(fk['columns'])}->{fk['to']}"


def col_id(item):
    return f"{item[0]}.{item[1]}"


def small(**fields):
    base = {"name": "t", "columns": [{"name": "a", "sql_type": "text"},
                                     {"name": "b", "sql_type": "integer"}], "pk": ["a"]}
    return {**base, **fields}


PARENT = {"name": "p", "columns": [{"name": "id", "sql_type": "text"},
                                   {"name": "n", "sql_type": "integer"}], "pk": ["id"]}


class TestTheRules:
    def test_a_sound_table_passes(self):
        assert cdm.key_errors(small(), {}) == []

    def test_pk_must_be_a_list(self):
        assert cdm.key_errors(small(pk="a"), {}) == ["[t] pk must be a list of columns"]

    def test_pk_must_name_columns(self):
        assert cdm.key_errors(small(pk=["z"]), {}) == [
            "[t] pk column 'z' is not a column of the table"]

    def test_pk_must_equal_the_grain(self):
        errs = cdm.key_errors(small(pk=["a"], grain="(a, b)"), {})
        assert errs == ["[t] pk ['a'] differs from grain ['a', 'b']"]

    def test_pk_equal_to_the_grain_passes(self):
        assert cdm.key_errors(small(pk=["a", "b"], grain="(a, b)"), {}) == []

    def test_required_keys_must_name_columns(self):
        assert cdm.key_errors(small(required_keys=["z"]), {}) == [
            "[t] required_keys column 'z' is not a column of the table"]

    def test_an_fk_that_resolves_passes(self):
        fk = {"columns": ["a"], "to": "p", "ref": ["id"]}
        assert cdm.key_errors(small(fk=[fk]), {"p": PARENT}) == []

    def test_an_fk_to_an_undeclared_table_fails(self):
        fk = {"columns": ["a"], "to": "nope", "ref": ["id"]}
        errs = cdm.key_errors(small(fk=[fk]), {})
        assert len(errs) == 1 and "not a declared table" in errs[0]

    def test_an_fk_to_a_column_that_is_not_the_target_pk_fails(self):
        fk = {"columns": ["b"], "to": "p", "ref": ["n"]}
        errs = cdm.key_errors(small(fk=[fk]), {"p": PARENT})
        assert len(errs) == 1 and "not the primary key" in errs[0]

    def test_an_fk_whose_types_differ_fails(self):
        fk = {"columns": ["b"], "to": "p", "ref": ["id"]}
        errs = cdm.key_errors(small(fk=[fk]), {"p": PARENT})
        assert len(errs) == 1 and "b is integer, p.id is text" in errs[0]

    def test_an_fk_on_a_missing_column_fails(self):
        fk = {"columns": ["z"], "to": "p", "ref": ["id"]}
        errs = cdm.key_errors(small(fk=[fk]), {"p": PARENT})
        assert errs == ["[t] fk column 'z' is not a column of the table"]

    def test_an_fk_with_columns_and_ref_of_different_length_fails(self):
        fk = {"columns": ["a", "b"], "to": "p", "ref": ["id"]}
        errs = cdm.key_errors(small(fk=[fk]), {"p": PARENT})
        assert len(errs) == 1 and "differ in length" in errs[0]

    def test_a_check_must_be_an_expression(self):
        assert cdm.key_errors(small(checks=[""]), {}) == ["[t] a check must be a SQL expression"]

    def test_an_index_must_name_columns(self):
        assert cdm.key_errors(small(indexes=[{"columns": ["z"]}]), {}) == [
            "[t] index column 'z' is not a column of the table"]


class TestOtherTables:
    def test_a_table_needs_its_fields(self):
        errs = cdm.other_table_errors({"name": "x"}, set())
        assert [e for e in errs if "missing required field" in e] == [
            f"[x] missing required field '{f}'" for f in ("schema", "columns", "pk")]

    def test_the_schema_must_be_one_of_three(self):
        errs = cdm.other_table_errors({"name": "x", "schema": "public", "columns": [], "pk": ["a"]}, set())
        assert len(errs) == 1 and "schema must be one of" in errs[0]

    def test_a_name_may_not_repeat(self):
        errs = cdm.other_table_errors({"name": "x", "schema": "ops", "columns": [], "pk": ["a"]}, {"x"})
        assert errs == ["[x] duplicate name"]


class TestTheRegistry:
    def test_it_passes_the_key_rules(self):
        assert [e for t in TABLES + OTHERS for e in cdm.key_errors(t, BY_NAME)] == []

    def test_it_passes_the_other_table_rules(self):
        seen = {t["name"] for t in TABLES}
        errs = []
        for t in OTHERS:
            errs += cdm.other_table_errors(t, seen)
            seen.add(t["name"])
        assert errs == []

    def test_every_table_has_a_pk_equal_to_its_grain(self):
        assert len(TABLES) == 35
        for t in TABLES:
            assert t["pk"] == [c.strip() for c in t["grain"].strip("()").split(",")], t["name"]

    def test_the_other_tables_are_the_ones_the_adr_names(self):
        assert sorted((t["schema"], t["name"]) for t in OTHERS) == [
            ("ops", "change_poll_state"), ("ops", "etl_run_log"), ("ops", "review_check"),
            ("ops", "review_dynasty_crosswalk"), ("ops", "review_fantrax_crosswalk"),
            ("ops", "review_fuzzy_matches"), ("shared", "owner")]

    def test_no_table_is_declared_twice(self):
        names = [t["name"] for t in TABLES + OTHERS]
        assert len(names) == len(set(names))

    def test_the_seam_never_sees_an_other_table(self):
        import etl_helpers as etl
        assert not set(etl._registry()) & {t["name"] for t in OTHERS}

    def test_the_eav_fact_needs_a_value(self):
        eav = BY_NAME["fact_dynasty_ranking_metrics"]
        assert eav["checks"] == ["metric_num IS NOT NULL OR metric_text IS NOT NULL"]

    def test_review_check_has_one_open_row_per_finding(self):
        (idx,) = BY_NAME["review_check"]["indexes"]
        assert idx["unique"] is True
        assert idx["columns"] == ["check_name", "table_name", "row_key"]
        assert idx["where"] == "resolved_at IS NULL"

    def test_the_foreign_keys_are_the_clean_edges_of_decision_6(self):
        targets = {"gsis_id": "dim_nfl_players", "team_key": "dim_fantasy_teams",
                   "contract_id": "dim_contract", "metric_key": "dim_dynasty_metric",
                   "asset_id": "dim_roster_asset", "season_id": "dim_season"}
        for table, fk in FKS:
            assert fk["to"] in targets.values(), (table, fk)
            assert fk["ref"][0] in targets and targets[fk["ref"][0]] == fk["to"], (table, fk)
        edges = {(t, tuple(fk["columns"]), fk["to"]) for t, fk in FKS}
        for dirty in ("player_key", "position_raw", "scorer_id", "school_raw", "team_abbr"):
            assert not any(dirty in cols for _, cols, _ in edges), dirty
        assert not any(len(cols) > 1 for _, cols, _ in edges)
        assert len(edges) == 47

    def test_the_zone_aware_columns_are_timestamptz(self):
        aware = {(t["name"], c["name"]) for t in TABLES for c in t["columns"]
                 if "," in str(c["dtype"])}
        assert aware == {("dim_scoring_period", "start_at"), ("dim_scoring_period", "end_at"),
                         ("dim_scoring_period", "closed_at"),
                         ("fact_fantasy_teams", "roster_captured_at"),
                         ("fact_fantasy_teams", "ledger_captured_at"),
                         ("fact_team_cap", "roster_captured_at"),
                         ("fact_team_cap", "fantrax_captured_at")}
        for t in TABLES:
            for c in t["columns"]:
                if (t["name"], c["name"]) in aware:
                    assert c["sql_type"] == "timestamptz", (t["name"], c["name"])
                elif str(c["dtype"]).startswith("datetime64"):
                    assert c["sql_type"] == "timestamp", (t["name"], c["name"])


class TestThePublishedTables:
    @pytest.mark.parametrize("table", [t["name"] for t in TABLES])
    def test_the_pk_has_no_null_and_no_repeat(self, table):
        pk = BY_NAME[table]["pk"]
        df = published(table)
        assert int(df[pk].isna().any(axis=1).sum()) == 0, f"{table}: null in {pk}"
        assert int(df.duplicated(subset=pk).sum()) == 0, f"{table}: repeat in {pk}"

    @pytest.mark.parametrize("item", FKS, ids=fk_id)
    def test_the_fk_has_no_orphan(self, item):
        table, fk = item
        cols, ref = fk["columns"], fk["ref"]
        child = published(table)[cols].dropna().drop_duplicates()
        parent = published(fk["to"])[ref].drop_duplicates()
        parent.columns = cols
        merged = child.merge(parent, on=cols, how="left", indicator=True)
        orphans = merged[merged["_merge"] == "left_only"][cols]
        assert orphans.empty, f"{len(orphans)} orphan key(s), first: {orphans.head(5).values.tolist()}"

    @pytest.mark.parametrize("item", INTEGERS, ids=col_id)
    def test_an_integer_column_is_whole_and_in_range(self, item):
        table, col = item
        values = pd.to_numeric(published(table)[col]).dropna()
        assert (values % 1 == 0).all(), f"{table}.{col}: a value with a fraction"
        assert values.between(INT_MIN, INT_MAX).all(), f"{table}.{col}: a value past the integer range"

    @pytest.mark.parametrize("item", DATES, ids=col_id)
    def test_a_date_column_is_an_iso_date(self, item):
        table, col = item
        for value in published(table)[col].dropna().unique():
            assert ISO_DATE.match(str(value)), f"{table}.{col}: {value!r} is not YYYY-MM-DD"
            date.fromisoformat(str(value))
