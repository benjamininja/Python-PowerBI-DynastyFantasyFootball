"""Seam reads and the load's lock timeout (#352).

A: timestamptz columns read back unchanged under a non-UTC session TimeZone.
C: no function of the seam but the known ones fetches rows, so a table read
cannot bypass read_on (binary format).
A2: the load's lock_timeout stays in force after the lock step (#425).
The database cases skip without TEST_DATABASE_URL (REQUIRE_TEST_DATABASE=1
makes that a failure); the guard runs everywhere.
"""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pytest

import backfill_postgres as backfill
import etl_helpers as etl
import etl_storage_pg as pg
from test_etl_storage import TABLES, database_url

pytestmark = pytest.mark.pg

PG_SOURCE = REPO / "notebooks" / "etl_storage_pg.py"
ROW_FETCHERS = {"read_on", "breaks", "orphans", "login_facts"}
ZONE = "Asia/Kolkata"


class TestNoReadBypassesReadOn:
    def fetching_functions(self):
        tree = ast.parse(PG_SOURCE.read_text(encoding="utf-8"))
        found = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr in ("fetchall", "fetchmany")):
                        found.add(fn.name)
        return found

    def test_only_read_on_and_the_catalog_probes_fetch_rows(self):
        assert self.fetching_functions() <= ROW_FETCHERS

    def test_read_on_reads_in_binary(self):
        source = PG_SOURCE.read_text(encoding="utf-8")
        body = source.split("def read_on", 1)[1].split("\ndef ", 1)[0]
        assert "binary=True" in body and "fetchall" in body

    def test_the_guard_sees_a_new_fetching_function(self, monkeypatch, tmp_path):
        fake = tmp_path / "etl_storage_pg.py"
        fake.write_text("def sneaky(conn):\n    return conn.execute('SELECT 1').fetchall()\n")
        monkeypatch.setattr(sys.modules[__name__], "PG_SOURCE", fake)
        assert self.fetching_functions() == {"sneaky"}


@pytest.fixture(scope="module")
def frames():
    return backfill.published_frames()


@pytest.fixture
def db(monkeypatch):
    url = database_url()
    pg.clear_published(url, TABLES)
    monkeypatch.setenv(pg.URL_ENV, url)
    try:
        yield url
    finally:
        pg.clear_published(url, TABLES)


def with_options(url, options):
    from psycopg.conninfo import make_conninfo
    return make_conninfo(url, options=options)


class TestTimestamptzUnderAnotherZone:
    def test_every_timestamptz_column_round_trips_under_a_non_utc_session(self, db, frames):
        import psycopg
        assert pg.load_published(with_options(db, "-c TimeZone=UTC"), frames, replace=True).problems == []
        state = pg._state()
        tables = [t for t in sorted(frames)
                  if any(c["sql_type"] == "timestamptz" for c in state[t]["columns"])]
        assert tables, "no table holds a timestamptz column"
        with psycopg.connect(with_options(db, f"-c TimeZone={ZONE}")) as conn:
            assert conn.execute("SHOW TimeZone").fetchone()[0] == ZONE
            for name in tables:
                entry = etl._table_entry(name)
                got = etl._coerce(pg.read_on(conn, entry), entry)
                assert pg.differences(got, frames[name], entry) == [], name

    def test_a_verified_load_under_a_non_utc_session_finds_no_difference(self, db, frames):
        loaded = pg.load_published(with_options(db, f"-c TimeZone={ZONE}"), frames,
                                   replace=True, verify=True)
        assert loaded.problems == []


class TestLockTimeoutStaysInForce:
    def timeouts_seen(self, monkeypatch):
        seen = []
        real = pg.read_on

        def spy(conn, entry, columns=None):
            seen.append(conn.execute("SHOW lock_timeout").fetchone()[0])
            return real(conn, entry, columns)

        monkeypatch.setattr(pg, "read_on", spy)
        return seen

    def test_statements_after_the_lock_keep_the_bound(self, db, frames, monkeypatch):
        seen = self.timeouts_seen(monkeypatch)
        loaded = pg.load_published(db, frames, empty_only=True, verify=True)
        assert loaded.problems == []
        assert seen and set(seen) == {f"{pg.LOCK_TIMEOUT_MS // 1000}s"}

    def test_the_lock_itself_is_still_bounded(self, db, frames, monkeypatch):
        import psycopg
        monkeypatch.setattr(pg, "LOCK_TIMEOUT_MS", 1000)
        name = sorted(frames)[0]
        with psycopg.connect(db) as holder:
            holder.execute(f'LOCK TABLE football."{name}" IN ACCESS EXCLUSIVE MODE')
            with pytest.raises(pg.LockTimeout):
                pg.load_published(db, frames, empty_only=True)

    def test_replace_runs_under_the_same_bound(self, db, frames, monkeypatch):
        seen = self.timeouts_seen(monkeypatch)
        loaded = pg.load_published(db, frames, replace=True, verify=True)
        assert loaded.problems == []
        assert seen and set(seen) == {f"{pg.LOCK_TIMEOUT_MS // 1000}s"}
