"""#93 brief 6 on the throwaway Postgres: the loader writes the three private
tables through the seam, and 02d and 04z read back what the parquet route reads.
Synthetic payloads only. Skips without TEST_DATABASE_URL (REQUIRE_TEST_DATABASE=1
makes that a failure).
"""
import importlib
import json
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
from test_supply_private_tables import NOTE, crosswalk, grid, payload, scorer

loader = importlib.import_module("load_draft_and_overrides")
rt = importlib.import_module("02d_fact_roster_transactions")

pytestmark = pytest.mark.pg
NOW = pd.Timestamp("2026-11-07 12:00:00.123456", tz="UTC")


def empty_private(url):
    import psycopg
    with psycopg.connect(url) as conn:
        for name in loader.TABLES:
            conn.execute(f"DELETE FROM ops.{name}")


@pytest.fixture
def db(monkeypatch, tmp_path):
    url = database_url()
    empty_private(url)
    monkeypatch.setenv("ETL_STORAGE", "postgres")
    monkeypatch.setenv(pg.URL_ENV, url)
    monkeypatch.setattr(etl.CFG, "data_dir", str(tmp_path))
    try:
        yield url
    finally:
        empty_private(url)


@pytest.fixture
def raw(tmp_path, monkeypatch):
    folder = tmp_path / "raw"
    folder.mkdir()
    (folder / "fantrax_draftresults_2026.json").write_text(
        json.dumps(payload(grid(), [scorer(f"s{i:03d}") for i in range(2, 13)])), encoding="utf-8")
    pd.DataFrame({"scorer_id": ["a", "n"], "gsis_id": ["G1", "new"], "note": [NOTE, None]}
                 ).to_csv(folder / loader.OVERRIDES_FILE, index=False)
    for name, value in (("SLOTS", 12), ("MADE", 11), ("UNMADE", 1), ("MANUAL", 1), ("NEW", 1)):
        monkeypatch.setattr(loader, name, value)
    return folder


def run_loader(raw):
    lines = []
    code = loader.load(raw, decisions={}, crosswalk=crosswalk([("a", "G1")], ["n"]),
                       now=NOW, out=lines.append)
    return code, lines


class TestLoaderThroughTheSeam:
    def test_the_three_tables_read_back_as_written(self, db, raw):
        code, lines = run_loader(raw)
        assert code == 0, lines
        want = loader.slots_from_payloads([json.loads(
            (raw / "fantrax_draftresults_2026.json").read_text(encoding="utf-8"))])
        got = etl.read_table("fact_startup_draft_slot")
        entry = etl._table_entry("fact_startup_draft_slot")
        assert pg.differences(got, want, entry) == []
        assert got["picked_at"].isna().sum() == 1 and got["scorer_id"].isna().sum() == 1
        over = etl.read_table("dim_fantrax_crosswalk_override").set_index("scorer_id")
        assert over.loc["a", "note"] == NOTE and pd.isna(over.loc["n", "note"])
        assert (over["recorded_at"] == NOW).all() and over["origin"].eq("csv").all()
        assert len(etl.read_table("dim_startup_draft_scorer")) == 11

    def test_a_second_run_is_refused_and_changes_nothing(self, db, raw):
        assert run_loader(raw)[0] == 0
        code, lines = run_loader(raw)
        assert code == 1 and "already holds rows" in "\n".join(lines)
        assert len(etl.read_table("fact_startup_draft_slot")) == 12

    def test_the_origin_check_refuses_another_origin(self, db):
        bad = pd.DataFrame({"scorer_id": ["a"], "gsis_id": ["G1"], "note": [None],
                            "recorded_at": [NOW], "origin": ["elsewhere"]})
        with pytest.raises(etl.StorageError):
            etl.write_table("dim_fantrax_crosswalk_override", bad)


class TestTheReadersSeeTheSameInput:
    def test_02d_gets_the_slots_the_parquet_route_gets(self, db, raw, tmp_path, monkeypatch):
        assert run_loader(raw)[0] == 0
        from_pg = rt.parse_draft_results(rt.load_draft())
        monkeypatch.delenv("ETL_STORAGE")
        folder = tmp_path / "parquet"
        folder.mkdir()
        monkeypatch.setattr(etl.CFG, "data_dir", str(folder))
        expected = loader.slots_from_payloads([json.loads(
            (raw / "fantrax_draftresults_2026.json").read_text(encoding="utf-8"))])
        etl.write_table("fact_startup_draft_slot", expected)
        from_parquet = rt.parse_draft_results(rt.load_draft())
        key = ["divisionId", "round", "pickNumber"]
        pd.testing.assert_frame_equal(from_pg.sort_values(key).reset_index(drop=True),
                                      from_parquet.sort_values(key).reset_index(drop=True),
                                      check_dtype=False)

    def test_04z_gets_the_overrides_and_draft_scorers(self, db, raw):
        assert run_loader(raw)[0] == 0
        over = etl.read_table("dim_fantrax_crosswalk_override")
        assert dict(zip(over["scorer_id"], over["gsis_id"])) == {"a": "G1", "n": "new"}
        scorers = etl.read_table("dim_startup_draft_scorer").set_index("scorer_id")
        assert scorers.loc["s002", "position_raw"] == "WR,DB" and bool(scorers.loc["s002", "is_rookie"])
