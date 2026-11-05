"""Doubles read back from Postgres are exact whatever extra_float_digits is (#349).

Supabase sessions show extra_float_digits = 0, which prints a double to 15
significant digits in the text format, so a text read returns a float that
differs from the parquet float64 in the last bits. The first backfill failed
its golden compare on four double precision columns because of it. These
cases force 0 on the connection (a libpq startup option, on the throwaway
Postgres of the storage-pg job) and read through every path of the seam.
They skip without TEST_DATABASE_URL; REQUIRE_TEST_DATABASE=1 makes that a
failure.
"""
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

NAMED = ["dim_position_ceiling", "fact_rookie_rankings"]


@pytest.fixture(scope="module")
def frames():
    return backfill.published_frames()


@pytest.fixture
def zero_digits(monkeypatch):
    """The test database, empty before and after, and a connection string whose
    sessions run with extra_float_digits = 0 (SUPABASE_DB_URL points at it)."""
    import psycopg
    from psycopg.conninfo import make_conninfo
    url = database_url()
    pg.clear_published(url, TABLES)
    forced = make_conninfo(url, options="-c extra_float_digits=0")
    with psycopg.connect(forced) as conn:
        assert conn.execute("SHOW extra_float_digits").fetchone()[0] == "0"
    monkeypatch.setenv(pg.URL_ENV, forced)
    try:
        yield url, forced
    finally:
        pg.clear_published(url, TABLES)


def float_tables(frames):
    state = pg._state()
    return [t for t in sorted(frames)
            if any(c["sql_type"] == "double precision" for c in state[t]["columns"])]


class TestExactDoubles:
    def test_the_named_tables_hold_doubles(self, frames):
        assert set(NAMED) <= set(float_tables(frames))

    def test_a_verified_load_under_zero_digits_finds_no_difference(self, zero_digits, frames):
        _, forced = zero_digits
        loaded = pg.load_published(forced, frames, replace=True, verify=True)
        assert loaded.problems == []
        assert loaded.counts == {t: len(frames[t]) for t in TABLES}

    def test_read_returns_every_double_exactly(self, zero_digits, frames):
        url, _ = zero_digits
        assert pg.load_published(url, frames, replace=True).problems == []
        for name in float_tables(frames):
            entry = etl._table_entry(name)
            got = etl._coerce(pg.read(entry), entry)
            assert pg.differences(got, frames[name], entry) == [], name

    def test_read_on_returns_every_double_exactly(self, zero_digits, frames):
        import psycopg
        url, forced = zero_digits
        assert pg.load_published(url, frames, replace=True).problems == []
        with psycopg.connect(forced) as conn:
            for name in float_tables(frames):
                entry = etl._table_entry(name)
                got = etl._coerce(pg.read_on(conn, entry), entry)
                assert pg.differences(got, frames[name], entry) == [], name


class TestWithoutADatabase:
    def test_read_on_asks_for_the_binary_format(self, monkeypatch):
        seen = {}

        class Conn:
            def execute(self, query, *args, **kwargs):
                seen.update(kwargs)
                return self

            def fetchall(self):
                return []

        entry = etl._table_entry("dim_position_ceiling")
        assert pg.read_on(Conn(), entry) is None
        assert seen.get("binary") is True
