"""#451: etl.write_table_checked on the parquet backend. It reads the tables the
check names, runs the check, then writes only if the check found nothing. No
lock and no database; the locked transaction is in test_record_crosswalk_override_pg.py.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd
import pytest

import etl_helpers as etl

TABLE = "dim_fantrax_crosswalk_override"
LINKS = etl.GSIS_LINK_TABLE
NOW = pd.Timestamp("2026-11-08 12:00:00", tz="UTC")
READS = {TABLE: ["scorer_id", "gsis_id"], LINKS: None}


def row(scorer="aaaaa", gsis="G1"):
    return pd.DataFrame({"scorer_id": [scorer], "gsis_id": [gsis], "note": ["run 1"],
                         "recorded_at": [NOW], "origin": ["form"]})


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("ETL_STORAGE", raising=False)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    return tmp_path


def test_a_clean_check_writes_the_row_and_returns_the_count(store):
    got = etl.write_table_checked(TABLE, row(), reads=READS, check=lambda stored: [])
    assert got == etl.Checked([], 1)
    assert etl.read_table(TABLE)["scorer_id"].tolist() == ["aaaaa"]


def test_a_problem_is_returned_and_nothing_is_written(store):
    got = etl.write_table_checked(TABLE, row(), reads=READS, check=lambda stored: ["stop"])
    assert got == etl.Checked(["stop"], None)
    assert not etl.table_exists(TABLE)


def test_a_table_with_no_data_reads_as_none_and_a_stored_one_as_its_projection(store):
    seen = []
    etl.write_table_checked(TABLE, row(), reads=READS, check=lambda stored: seen.append(stored) or [])
    assert seen[0][TABLE] is None and seen[0][LINKS] is None
    etl.write_table_checked(TABLE, row("bbbbb", "G2"), reads=READS, check=lambda stored: seen.append(stored) or [])
    assert list(seen[1][TABLE].columns) == ["scorer_id", "gsis_id"]
    assert seen[1][TABLE]["scorer_id"].tolist() == ["aaaaa"]


def test_the_check_sees_the_row_a_first_call_wrote(store):
    def claimed(stored):
        held = stored[TABLE]
        return [] if held is None else [f"{s} holds it" for s in held["scorer_id"]]

    assert etl.write_table_checked(TABLE, row("aaaaa"), reads=READS, check=claimed).problems == []
    assert etl.write_table_checked(TABLE, row("bbbbb"), reads=READS, check=claimed).problems == ["aaaaa holds it"]
    assert etl.read_table(TABLE)["scorer_id"].tolist() == ["aaaaa"]


def test_an_existing_scorer_is_replaced_not_duplicated(store):
    etl.write_table_checked(TABLE, row("aaaaa", "G1"), reads=READS, check=lambda stored: [])
    got = etl.write_table_checked(TABLE, row("aaaaa", "G3"), reads=READS, check=lambda stored: [])
    assert got.total == 1
    assert etl.read_table(TABLE)["gsis_id"].tolist() == ["G3"]


def test_an_undeclared_table_is_refused_before_any_write(store):
    with pytest.raises(etl.StorageError):
        etl.write_table_checked(TABLE, row(), reads={"not_a_table": None}, check=lambda stored: [])
    assert not etl.table_exists(TABLE)


def test_capture_mode_writes_the_copy_and_not_the_store(store, tmp_path_factory):
    copy = tmp_path_factory.mktemp("capture")
    with etl.capturing(copy):
        got = etl.write_table_checked(TABLE, row(), reads=READS, check=lambda stored: [])
    assert got.total == 1
    assert (copy / f"{TABLE}.parquet").exists()
    assert not (store / f"{TABLE}.parquet").exists()
