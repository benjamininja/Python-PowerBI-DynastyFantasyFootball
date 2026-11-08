"""#431 on the throwaway Postgres: the form's row goes through the seam and the
widened origin CHECK allows it. Skips without TEST_DATABASE_URL
(REQUIRE_TEST_DATABASE=1 makes that a failure). Synthetic ids only.
"""
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest

import etl_helpers as etl
import etl_storage_pg as pg
from test_etl_storage import database_url

rec = importlib.import_module("record_crosswalk_override")

pytestmark = pytest.mark.pg
NOW = pd.Timestamp("2026-11-08 12:00:00.123456", tz="UTC")
TABLE = rec.OVERRIDE_TABLE
XW = pd.DataFrame({"scorer_id": ["aaaaa", "bbbbb", "ccccc"], "gsis_id": [None, "G2", None]})
PLAYERS = pd.DataFrame({"gsis_id": ["G1", "G2", "G3"]})


def empty(url):
    import psycopg
    with psycopg.connect(url) as conn:
        conn.execute(f"DELETE FROM ops.{TABLE}")


@pytest.fixture
def db(monkeypatch, tmp_path):
    url = database_url()
    empty(url)
    monkeypatch.setenv("ETL_STORAGE", "postgres")
    monkeypatch.setenv(pg.URL_ENV, url)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    try:
        yield url
    finally:
        empty(url)


def go(env, held=None):
    lines = []
    over = pd.DataFrame({"scorer_id": pd.Series(dtype=str), "gsis_id": pd.Series(dtype=str)}) if held is None else held
    code = rec.run(env, out=lines.append, now=NOW, inputs=(XW, PLAYERS, over, None))
    return code, lines


def env(scorer="aaaaa", gsis="G1", replace="false", run="777"):
    return {"SCORER_ID": scorer, "GSIS_ID": gsis, "REPLACE": replace, "GITHUB_RUN_ID": run}


class TestTheFormRowThroughTheSeam:
    def test_a_good_write_reads_back_as_a_form_row(self, db):
        code, lines = go(env())
        assert code == 0, lines
        got = etl.read_table(TABLE).set_index("scorer_id")
        assert got.loc["aaaaa", "origin"] == "form" and got.loc["aaaaa", "note"] == "run 777"
        assert got.loc["aaaaa", "gsis_id"] == "G1" and got.loc["aaaaa", "recorded_at"] == NOW

    def test_the_new_mark_and_a_second_scorer_land_beside_the_first(self, db):
        assert go(env())[0] == 0
        held = pd.DataFrame({"scorer_id": ["aaaaa"], "gsis_id": ["G1"]})
        assert go(env(scorer="ccccc", gsis="new", run="778"), held)[0] == 0
        got = etl.read_table(TABLE).set_index("scorer_id")
        assert got["gsis_id"].to_dict() == {"aaaaa": "G1", "ccccc": "new"}

    def test_a_replace_updates_the_one_row(self, db):
        assert go(env())[0] == 0
        held = pd.DataFrame({"scorer_id": ["aaaaa"], "gsis_id": ["G1"]})
        assert go(env(gsis="G3", replace="true", run="900"), held)[0] == 0
        got = etl.read_table(TABLE)
        assert got[["scorer_id", "gsis_id", "note"]].to_dict("records") == [
            {"scorer_id": "aaaaa", "gsis_id": "G3", "note": "run 900"}]

    def test_a_refused_check_leaves_the_table_empty(self, db):
        code, lines = go(env(gsis="G2"))
        assert code == 1 and lines[-1] == "nothing was written"
        assert not etl.table_exists(TABLE)

    def test_the_widened_check_allows_form_and_still_refuses_another_origin(self, db):
        bad = rec.row("aaaaa", "G1", "1", NOW).assign(origin="elsewhere")
        with pytest.raises(etl.StorageError):
            etl.write_table(TABLE, bad, mode="upsert")
        etl.write_table(TABLE, rec.row("aaaaa", "G1", "1", NOW), mode="upsert")
        for scorer, origin in (("bbbbb", "csv"), ("ccccc", "apply_script")):
            etl.write_table(TABLE, rec.row(scorer, "G2", "1", NOW).assign(origin=origin), mode="upsert")
        assert sorted(etl.read_table(TABLE)["origin"]) == ["apply_script", "csv", "form"]
