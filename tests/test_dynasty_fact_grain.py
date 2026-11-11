"""The dynasty fact's grain on the published table (#110; ADR-0018 decision 5).

Composite rows are cross-source, so 04y keys them by gsis_id: source_player_id
is the gsis_id and source_uid is `Composite|<gsis_id>`. Before #110 both were
null, which left 1,812 rows outside the declared grain.
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import etl_checks as ec

TABLE = "fact_dynasty_ranking_metrics"


def fact():
    return pd.read_parquet(REPO / "data" / f"{TABLE}.parquet")


def test_the_grain_is_non_null_and_unique():
    key = ec.table_key(ec.load_registry()[TABLE])
    assert ec.check_grain(fact(), key) == (0, 0)


def test_composite_rows_are_keyed_by_gsis_id():
    comp = fact().query("source_name == 'Composite'")
    assert len(comp) and comp["gsis_id"].notna().all()
    assert (comp["source_player_id"] == comp["gsis_id"]).all()
    assert (comp["source_uid"] == "Composite|" + comp["gsis_id"]).all()


def test_every_other_row_keeps_its_source_uid():
    rest = fact().query("source_name != 'Composite'")
    assert (rest["source_uid"] == rest["source_name"] + "|" + rest["source_player_id"]).all()
