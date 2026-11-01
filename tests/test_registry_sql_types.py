"""`sql_type` on every registry column (#110, #108; ADR-0018 decision 8).

Every column declares the Postgres type of its table. A column that holds no
value yet reads back from parquet as `object`, which names no SQL type, so its
`sql_type` is the only record of what its values will be. `check_data_model.py`
fails a column that declares none, or one that does not fit its dtype.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import check_data_model as cdm

TABLES = cdm.load_yaml()["tables"]


def table(*columns):
    return {"name": "t", "columns": list(columns)}


class TestTheRule:
    def test_an_object_column_needs_a_sql_type(self):
        assert cdm.sql_type_errors(table({"name": "a", "dtype": "object"})) == [
            "[t] a: needs a sql_type"]

    def test_a_typed_column_needs_one_too(self):
        assert cdm.sql_type_errors(table({"name": "a", "dtype": "str"},
                                         {"name": "b", "dtype": "float64"})) == [
            "[t] a: needs a sql_type", "[t] b: needs a sql_type"]

    @pytest.mark.parametrize("dtype, sql_type", [
        ("str", "text"), ("str", "date"), ("string", "text"),
        ("int32", "integer"), ("int64", "integer"), ("Int64", "integer"),
        ("float64", "double precision"), ("float64", "integer"),
        ("bool", "boolean"),
        ("datetime64[us]", "timestamp"), ("datetime64[ms]", "timestamp"),
        ("datetime64[us, UTC]", "timestamptz"),
    ])
    def test_a_sql_type_that_fits_its_dtype_passes(self, dtype, sql_type):
        assert cdm.sql_type_errors(table({"name": "a", "dtype": dtype, "sql_type": sql_type})) == []

    @pytest.mark.parametrize("dtype, sql_type", [
        ("str", "integer"), ("int64", "double precision"), ("int64", "text"),
        ("float64", "text"), ("bool", "integer"),
        ("datetime64[us]", "timestamptz"), ("datetime64[us, UTC]", "timestamp"),
        ("datetime64[us]", "date"),
    ])
    def test_a_sql_type_that_does_not_fit_its_dtype_fails(self, dtype, sql_type):
        errs = cdm.sql_type_errors(table({"name": "a", "dtype": dtype, "sql_type": sql_type}))
        assert len(errs) == 1 and "does not fit" in errs[0]

    @pytest.mark.parametrize("sql_type", sorted(cdm.SQL_TYPES))
    def test_a_known_sql_type_passes(self, sql_type):
        assert cdm.sql_type_errors(
            table({"name": "a", "dtype": "object", "sql_type": sql_type})) == []

    def test_an_unknown_sql_type_fails_on_any_column(self):
        errs = cdm.sql_type_errors(table({"name": "a", "dtype": "str", "sql_type": "varchar"}))
        assert len(errs) == 1 and "'varchar'" in errs[0]


class TestTheRegistry:
    def test_it_passes_the_rule(self):
        assert [e for t in TABLES for e in cdm.sql_type_errors(t)] == []

    def test_every_all_null_untyped_column_is_declared(self):
        # Read from the published tables, so a new empty column cannot slip by.
        declared = {(t["name"], c["name"]) for t in TABLES for c in t["columns"]
                    if "sql_type" in c}
        for t in TABLES:
            df = pd.read_parquet(REPO / "data" / f"{t['name']}.parquet")
            for col in df.columns:
                if len(df) and str(df[col].dtype) == "object" and df[col].isna().all():
                    assert (t["name"], col) in declared, (t["name"], col)

    def test_a_pick_slot_is_typed_like_the_made_picks(self):
        future = {c["name"]: c for t in TABLES if t["name"] == "fact_draft_pick_future"
                  for c in t["columns"]}
        made = pd.read_parquet(REPO / "data" / "fact_draft_pick.parquet")
        for col in ("pick_in_round", "overall_slot"):
            assert future[col]["sql_type"] == "integer"
            assert pd.api.types.is_integer_dtype(made[col])
