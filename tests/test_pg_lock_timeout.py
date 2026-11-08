"""Every lock wait on the seam's write paths is bounded (#425).

The replace DELETE, the foreign-key check and the lock step each fail within
the bound with a message naming the table and the wait; the bound is never
set to 0 (no limit) and the value in force after the lock step equals the one
before it. The database cases run against TEST_DATABASE_URL (the storage-pg CI
job) and skip without it; the others need no database.
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

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
BOUND_MS = 1000
SLACK_S = 5


class TestWithoutADatabase:
    def test_the_bound_is_set_in_milliseconds_as_the_first_statement(self):
        seen = []
        pg.bound_locks(SimpleNamespace(execute=seen.append))
        assert seen == [f"SET LOCAL lock_timeout = {pg.LOCK_TIMEOUT_MS}"]
        assert 0 < pg.LOCK_TIMEOUT_MS

    def test_the_module_never_sets_the_timeout_to_zero(self):
        source = PG_SOURCE.read_text(encoding="utf-8")
        assert "lock_timeout = 0" not in source and "lock_timeout=0" not in source

    def test_a_lock_timeout_names_the_table_and_the_wait(self):
        import psycopg
        with pytest.raises(pg.LockTimeout) as raised:
            with pg._waiting_on("football.dim_season"):
                raise psycopg.errors.LockNotAvailable("canceling statement due to lock timeout")
        assert str(raised.value) == "football.dim_season: waited 10s for a lock, gave up (lock_timeout); not retried"
        assert isinstance(raised.value, pg.WriteRefused)

    def test_another_database_error_passes_through_the_lock_wrapper(self):
        import psycopg
        with pytest.raises(psycopg.errors.UniqueViolation):
            with pg._waiting_on("football.dim_season"):
                raise psycopg.errors.UniqueViolation("duplicate key")

    def test_db_errors_names_a_lock_timeout_the_step_did_not(self):
        import psycopg
        with pytest.raises(pg.LockTimeout, match="football.dim_season: waited"):
            with pg._db_errors("football.dim_season"):
                raise psycopg.errors.LockNotAvailable("canceling statement due to lock timeout")

    def test_db_errors_still_reduces_other_errors_to_their_first_line(self):
        import psycopg
        with pytest.raises(pg.WriteRefused, match="^duplicate key$") as raised:
            with pg._db_errors("football.dim_season"):
                raise psycopg.errors.UniqueViolation("duplicate key\nDETAIL: a value")
        assert not isinstance(raised.value, pg.LockTimeout)

    def test_the_description_a_run_logs_carries_the_table_and_the_wait(self):
        text = pg.describe(pg.LockTimeout("football.dim_season"))
        assert text.startswith("LockTimeout: football.dim_season: waited 10s")
        assert "not retried" in text

    def test_the_longest_description_still_fits_the_scrubbed_line(self):
        where = "foreign-key check at commit on football.fact_nfl_combine_pro_day_metrics"
        assert "not retried" in pg.describe(pg.LockTimeout(where))

    def test_the_tables_a_foreign_key_check_reads_are_the_ones_outside_the_load(self):
        links = [("dim_division", "dim_season"), ("dim_scoring_period", "dim_season"),
                 ("fact_dead_money", "dim_contract")]
        assert pg._outside(links, ["dim_division"]) == ["dim_season"]
        assert pg._outside(links, ["dim_season"]) == ["dim_division", "dim_scoring_period"]
        assert pg._outside(links, ["dim_division", "dim_season"]) == ["dim_scoring_period"]
        assert pg._outside(links, ["dim_unrelated"]) == []

    def test_the_foreign_key_wait_names_the_tables_and_caps_the_list(self):
        def conn_with(links):
            return SimpleNamespace(execute=lambda *args: iter(links))

        one = pg._fk_where(conn_with([("dim_division", "dim_season")]), ["dim_division"])
        assert one == "foreign-key check at commit on football.dim_season"
        many = [(f"c{i}", "p") for i in range(5)]
        text = pg._fk_where(conn_with(many), ["p"])
        assert text == "foreign-key check at commit on football.c0, football.c1, football.c2 and 2 more"
        assert pg._fk_where(conn_with([]), ["x"]) == (
            "foreign-key check at commit on a table the foreign keys reference")


@pytest.fixture(scope="module")
def frames():
    return backfill.published_frames()


@pytest.fixture
def db(monkeypatch):
    url = database_url()
    pg.clear_published(url, TABLES)
    monkeypatch.setenv(pg.URL_ENV, url)
    monkeypatch.setattr(pg, "LOCK_TIMEOUT_MS", BOUND_MS)
    try:
        yield url
    finally:
        pg.clear_published(url, TABLES)


def waited(call):
    """Run `call`, which must raise LockTimeout, and return (error, seconds)."""
    start = time.monotonic()
    with pytest.raises(pg.LockTimeout) as raised:
        call()
    return raised.value, time.monotonic() - start


def expect_the_bound(error, seconds, where):
    assert where in str(error)
    assert "waited 1s for a lock, gave up (lock_timeout); not retried" in str(error)
    assert BOUND_MS / 1000 * 0.9 <= seconds < BOUND_MS / 1000 + SLACK_S


def with_options(url, options):
    from psycopg.conninfo import make_conninfo
    return make_conninfo(url, options=options)


class TestAHeldLockFailsEachStepWithinTheBound:
    def test_the_replace_write_fails_on_its_delete(self, db, frames):
        import psycopg
        name = sorted(frames)[0]
        entry = etl._table_entry(name)
        batch = etl._check_batch(frames[name], entry)
        with psycopg.connect(db) as holder:
            holder.execute(f'LOCK TABLE football."{name}" IN SHARE MODE')
            error, seconds = waited(lambda: pg.write(entry, batch, "replace", None, None))
        expect_the_bound(error, seconds, f"football.{name}")

    def test_the_replace_load_fails_on_its_delete_and_waits_once(self, db, frames):
        import psycopg
        names = sorted(frames)[:3]
        with psycopg.connect(db) as holder:
            holder.execute(f'LOCK TABLE football."{names[1]}" IN SHARE MODE')
            error, seconds = waited(lambda: pg.load_published(
                db, {n: frames[n] for n in names}, replace=True))
        expect_the_bound(error, seconds, f"football.{names[1]}")
        with psycopg.connect(db) as conn:
            assert pg.nonempty(conn, names) == []

    def test_the_lock_step_of_an_empty_only_load_fails_naming_the_table(self, db, frames):
        import psycopg
        name = sorted(frames)[0]
        with psycopg.connect(db) as holder:
            holder.execute(f'LOCK TABLE football."{name}" IN ACCESS EXCLUSIVE MODE')
            error, seconds = waited(lambda: pg.load_published(db, frames, empty_only=True))
        expect_the_bound(error, seconds, f"football.{name}")

    def test_the_lock_step_of_write_all_empty_fails_naming_the_table(self, db, frames):
        import psycopg
        name = sorted(frames)[0]
        entry = etl._table_entry(name)
        batch = etl._check_batch(frames[name], entry)
        with psycopg.connect(db) as holder:
            holder.execute(f'LOCK TABLE football."{name}" IN ACCESS EXCLUSIVE MODE')
            error, seconds = waited(lambda: pg.write_all_empty({name: (entry, batch)}))
        expect_the_bound(error, seconds, f"football.{name}")

    def test_the_foreign_key_check_fails_naming_the_parent_it_waited_on(self, db, frames, monkeypatch):
        import psycopg
        assert pg.load_published(db, frames, replace=True).problems == []
        with psycopg.connect(db) as conn:
            pairs = conn.execute(
                "SELECT c.conrelid::regclass::text, c.confrelid::regclass::text FROM pg_constraint c "
                "WHERE c.contype = 'f' AND c.connamespace = %s::regnamespace "
                "AND c.conrelid <> c.confrelid ORDER BY c.conname", (pg.SCHEMA,)).fetchall()
        links = [(child.split(".")[-1].strip('"'), parent.split(".")[-1].strip('"'))
                 for child, parent in pairs]
        usable = [(c, p) for c, p in links if c in frames and p in frames and len(frames[c])
                  and pg._outside(links, [c]) == [p]]
        assert usable, "no foreign key to one parent only, from a published table with rows"
        child, parent = usable[0]
        marks = {}
        real_orphans, real_where = pg.orphans, pg._fk_where

        def orphans(conn):
            found = real_orphans(conn)
            marks["in_force"] = conn.execute("SHOW lock_timeout").fetchone()[0]
            marks["waiting_from"] = time.monotonic()
            return found

        def fk_where(conn, loaded):
            marks["gave_up"] = time.monotonic()
            return real_where(conn, loaded)

        monkeypatch.setattr(pg, "orphans", orphans)
        monkeypatch.setattr(pg, "_fk_where", fk_where)
        start = time.monotonic()
        with psycopg.connect(db) as holder:
            holder.execute(f'LOCK TABLE football."{parent}" IN EXCLUSIVE MODE')
            error, seconds = waited(lambda: pg.load_published(db, {child: frames[child]}, replace=True))
        before, wait = marks["waiting_from"] - start, marks["gave_up"] - marks["waiting_from"]
        assert f"foreign-key check at commit on football.{parent}" in str(error)
        assert "waited 1s for a lock, gave up (lock_timeout); not retried" in str(error)
        assert marks["in_force"] == "1s"
        assert BOUND_MS / 1000 * 0.9 <= wait < BOUND_MS / 1000 + SLACK_S, (
            f"the foreign-key check waited {wait:.1f}s; the load took {before:.1f}s before it and "
            f"{seconds:.1f}s in all")
        with psycopg.connect(db) as conn:
            assert conn.execute(f'SELECT count(*) FROM football."{child}"').fetchone()[0] == len(frames[child])


class TestTheBoundHoldsAfterTheLockStep:
    def values_seen(self, monkeypatch):
        seen = {"before": [], "after": []}
        real_bound, real_nonempty, real_read = pg.bound_locks, pg.nonempty, pg.read_on

        def show(conn):
            return conn.execute("SHOW lock_timeout").fetchone()[0]

        def bound(conn):
            real_bound(conn)
            seen["before"].append(show(conn))

        def nonempty(conn, tables):
            seen["after"].append(show(conn))
            return real_nonempty(conn, tables)

        def read_on(conn, entry, columns=None):
            seen["after"].append(show(conn))
            return real_read(conn, entry, columns)

        monkeypatch.setattr(pg, "bound_locks", bound)
        monkeypatch.setattr(pg, "nonempty", nonempty)
        monkeypatch.setattr(pg, "read_on", read_on)
        return seen

    def test_the_value_after_the_lock_step_equals_the_value_before_it(self, db, frames, monkeypatch):
        seen = self.values_seen(monkeypatch)
        loaded = pg.load_published(db, frames, empty_only=True, verify=True)
        assert loaded.problems == []
        assert seen["before"] == ["1s"]
        assert seen["after"] and set(seen["after"]) == set(seen["before"])

    def test_a_session_whose_default_is_no_limit_is_bounded_and_stays_so(self, db, frames, monkeypatch):
        seen = self.values_seen(monkeypatch)
        url = with_options(db, "-c lock_timeout=0")
        loaded = pg.load_published(url, frames, empty_only=True, verify=True)
        assert loaded.problems == []
        assert seen["before"] == ["1s"]
        assert seen["after"] and set(seen["after"]) == {"1s"}
