"""#431 on the throwaway Postgres: the form's row goes through the seam and the
widened origin CHECK allows it. Skips without TEST_DATABASE_URL
(REQUIRE_TEST_DATABASE=1 makes that a failure). Synthetic ids only.
"""
import importlib
import sys
import threading
import time
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


EMPTY = pd.DataFrame({"scorer_id": pd.Series(dtype=str), "gsis_id": pd.Series(dtype=str)})
READS = {TABLE: ["scorer_id", "gsis_id"]}
WAIT_S = 1.5
JOIN_S = 30


def claim(scorer, gsis, *, entered=None, release=None):
    """One form submission at the seam: the checks of `validate` against the
    override table as read in the transaction. `entered` is set when the check
    starts, and `release` (if given) holds the transaction open until it is set."""
    def check(stored):
        if entered is not None:
            entered.set()
        if release is not None:
            assert release.wait(JOIN_S), "the test never released the first writer"
        held = EMPTY if stored[TABLE] is None else stored[TABLE]
        return rec.validate(scorer, gsis, False, XW, PLAYERS, held, None)

    return etl.write_table_checked(TABLE, rec.row(scorer, gsis, "1", NOW), reads=READS, check=check)


def in_thread(call, box):
    def target():
        try:
            box["got"] = call()
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


class TestTwoWritersAreSerialized:
    def test_the_second_writer_waits_then_is_refused_and_only_the_first_row_is_stored(self, db):
        entered, release = threading.Event(), threading.Event()
        first, second = {}, {}
        t1 = in_thread(lambda: claim("aaaaa", "G1", entered=entered, release=release), first)
        assert entered.wait(JOIN_S), "the first writer never reached its check"
        entered2 = threading.Event()
        t2 = in_thread(lambda: claim("bbbbb", "G1", entered=entered2), second)
        time.sleep(WAIT_S)
        assert t2.is_alive() and not entered2.is_set(), "the second writer ran its check while the first held the lock"
        release.set()
        t1.join(JOIN_S)
        t2.join(JOIN_S)
        assert "error" not in first and "error" not in second, (first, second)
        assert first["got"].problems == [] and first["got"].total == 1
        assert second["got"].problems == [
            "gsis_id G1 is already claimed by scorer_id aaaaa in dim_fantrax_crosswalk_override"]
        assert second["got"].total is None
        assert etl.read_table(TABLE)[["scorer_id", "gsis_id"]].to_dict("records") == [
            {"scorer_id": "aaaaa", "gsis_id": "G1"}]

    def test_a_second_writer_that_waits_past_the_bound_gives_up_naming_the_table(self, db, monkeypatch):
        monkeypatch.setattr(pg, "LOCK_TIMEOUT_MS", 1000)
        entered, release = threading.Event(), threading.Event()
        first = {}
        t1 = in_thread(lambda: claim("aaaaa", "G1", entered=entered, release=release), first)
        assert entered.wait(JOIN_S)
        started = time.monotonic()
        with pytest.raises(etl.LockWaitTimeout) as raised:
            claim("bbbbb", "G1")
        waited = time.monotonic() - started
        assert "ops.dim_fantrax_crosswalk_override: waited 1s for a lock, gave up (lock_timeout)" in str(raised.value)
        assert 0.9 <= waited < 1 + 10
        release.set()
        t1.join(JOIN_S)
        assert first["got"].total == 1
        assert etl.read_table(TABLE)["scorer_id"].tolist() == ["aaaaa"]

    def test_a_refused_check_takes_the_lock_and_gives_it_back_with_no_write(self, db):
        assert claim("aaaaa", "G1").problems == []
        assert claim("bbbbb", "G1").problems != []
        assert claim("ccccc", "G3").problems == []
        assert sorted(etl.read_table(TABLE)["scorer_id"]) == ["aaaaa", "ccccc"]

    def test_a_table_that_holds_no_rows_reads_as_none_inside_the_transaction(self, db):
        seen = []
        got = etl.write_table_checked(TABLE, rec.row("aaaaa", "G1", "1", NOW), reads=READS,
                                      check=lambda stored: seen.append(stored[TABLE]) or [])
        assert seen == [None] and got.total == 1


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
