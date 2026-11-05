"""The backfill of the real project (#135, B3): scripts/backfill_postgres.py,
the load / compare functions in notebooks/etl_storage_pg.py and
.github/workflows/backfill.yml.

The database cases run against TEST_DATABASE_URL only (the throwaway Postgres
of the storage-pg CI job, reached as etl_writer) and skip without it;
REQUIRE_TEST_DATABASE=1 makes that a failure. Nothing here reaches the real
project: the conftest autouse fixture removes SUPABASE_DB_URL, and a case that
needs it sets it to the test database.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest
import yaml

import backfill_postgres as backfill
import etl_helpers as etl
import etl_storage_pg as pg
from test_etl_storage import TABLES, database_url

SENTINEL = "SENTINEL-4471"
ENTRY = {"name": "t", "grain": "k", "columns": [
    {"name": "k", "dtype": "int64"}, {"name": "v", "dtype": "float64"}, {"name": "s", "dtype": "str"}]}


@pytest.fixture(scope="module")
def frames():
    return backfill.published_frames()


@pytest.fixture
def db(monkeypatch):
    """The test database with every football table empty, before and after,
    and SUPABASE_DB_URL (the script's input) pointing at it."""
    url = database_url()
    pg.clear_published(url, TABLES)
    monkeypatch.setenv(pg.URL_ENV, url)
    try:
        yield url
    finally:
        pg.clear_published(url, TABLES)


def held(url):
    import psycopg
    with psycopg.connect(url) as conn:
        return pg.nonempty(conn, TABLES)


def count(url, table):
    import psycopg
    with psycopg.connect(url) as conn:
        return conn.execute(f'SELECT count(*) FROM football."{table}"').fetchone()[0]


def said(capsys):
    seen = capsys.readouterr()
    return seen.out + seen.err


class TestTheDatabase:
    def test_an_empty_schema_loads_and_a_second_run_is_refused(self, db, frames, capsys):
        assert backfill.main([]) == 0
        out = said(capsys)
        assert f"committed {len(TABLES)} table(s)" in out
        for table in TABLES:
            assert count(db, table) == len(frames[table])
        assert held(db) == [t for t in TABLES if len(frames[t])]

        assert backfill.main([]) == 2
        out = said(capsys)
        assert "already holds rows" in out and "nothing was written" in out
        for table in TABLES:
            assert count(db, table) == len(frames[table])

        assert backfill.main(["--replace"]) == 0
        assert f"committed {len(TABLES)} table(s)" in said(capsys)
        for table in TABLES:
            assert count(db, table) == len(frames[table])

    def test_a_forced_mismatch_rolls_back_and_leaves_the_database_unchanged(self, db, monkeypatch, capsys):
        real = pg.read_on
        tampered = {}

        def read_on(conn, entry, columns=None):
            got = real(conn, entry, columns)
            if got is None or tampered:
                return got
            key = etl.table_grain(entry)
            text = [c["name"] for c in entry["columns"]
                    if str(c["dtype"]) in pg._TEXT_DTYPES and c["name"] not in key
                    and got[c["name"]].notna().any()]
            if not text:
                return got
            got = got.copy()
            got.loc[got.index[0], text[0]] = SENTINEL
            tampered.update(table=entry["name"], column=text[0])
            return got

        monkeypatch.setattr(pg, "read_on", read_on)
        assert backfill.main([]) == 1
        out = said(capsys)
        assert tampered, "no table with a text column to tamper with"
        assert f"{tampered['table']}.{tampered['column']}: 1 cell(s) differ" in out
        assert "rolled back; nothing was committed" in out
        assert SENTINEL not in out
        assert held(db) == []

    def test_a_forced_constraint_error_prints_no_values(self, db, frames, monkeypatch, capsys):
        state = pg._state()
        for name in sorted(frames):
            spec = state[name]
            loose = [c["name"] for c in spec["columns"] if c["not_null"] and c["name"] not in spec["pk"]
                     and c["sql_type"] == "text"]
            text = [c["name"] for c in spec["columns"] if c["sql_type"] == "text"
                    and c["name"] not in spec["pk"] and c["name"] not in loose]
            if len(frames[name]) and loose and text:
                break
        else:
            pytest.skip("no published table with a NOT NULL non-key column and a text column")
        bad = frames[name].copy()
        bad[loose[0]] = None
        bad[text[0]] = SENTINEL
        monkeypatch.setattr(backfill, "published_frames", lambda: {**frames, name: bad})
        assert backfill.main([]) == 1
        out = said(capsys)
        assert f"{name}: refused: NotNullViolation SQLSTATE 23502" in out
        assert f"NOT NULL {name}.{loose[0]}: {len(bad)} row(s)" in out
        assert SENTINEL not in out and "DETAIL" not in out and "Traceback" not in out
        assert held(db) == []

    def test_a_database_error_at_the_top_prints_no_value_and_no_traceback(self, db, monkeypatch, capsys):
        import psycopg
        seen = {}

        def failing(url, frames, **kwargs):
            with psycopg.connect(url) as conn:
                try:
                    conn.execute(f"SELECT '{SENTINEL}'::integer")
                except psycopg.Error as exc:
                    seen["carried"] = SENTINEL in str(exc)
                    raise

        monkeypatch.setattr(backfill, "run", failing)
        assert backfill.main([]) == 1
        out = said(capsys)
        assert seen["carried"] is True
        assert "InvalidTextRepresentation SQLSTATE 22P02" in out
        assert SENTINEL not in out and "Traceback" not in out

    def test_the_login_is_etl_writer_without_bypass_and_every_table_has_rls(self, db):
        import psycopg
        with psycopg.connect(db) as conn:
            facts = pg.login_facts(conn)
        assert facts["user"] == "etl_writer"
        assert facts["bypass_rls"] is False and facts["superuser"] is False
        assert set(TABLES) <= set(facts["rls"])
        assert all(facts["rls"].values())
        assert pg.login_problems(facts, TABLES) == []

    def test_another_login_is_refused_before_any_write(self, db, frames, monkeypatch, capsys):
        real = pg.login_facts
        monkeypatch.setattr(pg, "login_facts", lambda conn: {**real(conn), "user": "postgres", "superuser": True})
        assert backfill.main([]) == 2
        out = said(capsys)
        assert "connected as postgres, expected etl_writer" in out and "nothing was written" in out
        assert held(db) == []

    def test_the_loaded_counts_are_the_database_counts(self, db, frames):
        loaded = pg.load_published(db, frames, replace=True)
        assert loaded.problems == [] and not loaded.refused
        assert loaded.counts == {t: len(frames[t]) for t in TABLES}
        for table in TABLES:
            assert count(db, table) == loaded.counts[table]

    def test_empty_only_refuses_inside_the_load_and_writes_nothing(self, db, frames):
        assert pg.load_published(db, frames, replace=True).problems == []
        before = {t: count(db, t) for t in TABLES}
        again = pg.load_published(db, frames, replace=False, empty_only=True)
        assert again.refused and again.counts == {}
        assert any("already holds rows" in line for line in again.problems)
        assert {t: count(db, t) for t in TABLES} == before

    def test_the_clear_helper_deletes_in_the_test_database(self, db, frames):
        assert pg.load_published(db, frames, replace=True).problems == []
        assert held(db)
        pg.clear_published(db, TABLES)
        assert held(db) == []

    def test_a_load_without_replace_into_a_full_table_rolls_back(self, db, frames):
        assert pg.load_published(db, frames, replace=True).problems == []
        again = pg.load_published(db, frames, replace=False)
        assert any("refused: UniqueViolation SQLSTATE 23505" in line for line in again.problems)
        for table in TABLES:
            assert count(db, table) == len(frames[table])


class TestWithoutADatabase:
    def test_the_clear_helper_refuses_any_url_but_the_test_database(self, monkeypatch):
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="TEST_DATABASE_URL"):
            pg.clear_published("postgresql://u@h/d", ["dim_season"])
        monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u@test/d")
        with pytest.raises(RuntimeError, match="TEST_DATABASE_URL"):
            pg.clear_published("postgresql://u@live/d", ["dim_season"])

    def test_no_url_is_refused_before_anything_runs(self, capsys):
        assert backfill.main([]) == 2
        assert "SUPABASE_DB_URL is not set" in said(capsys)

    def test_a_bad_url_prints_neither_the_url_nor_the_password(self, monkeypatch, capsys):
        monkeypatch.setenv(pg.URL_ENV, f"postgresql://etl_writer:{SENTINEL}@/db?bogus=1")
        assert backfill.main([]) == 1
        out = said(capsys)
        assert SENTINEL not in out and "Traceback" not in out and "stopped, nothing was committed" in out

    def test_the_snapshot_must_name_the_registry_tables(self, tmp_path):
        pd.DataFrame({"a": [1]}).to_parquet(tmp_path / "dim_season.parquet")
        with pytest.raises(backfill.Refused, match="different tables"):
            backfill.published_frames(tmp_path)

    def test_the_published_snapshot_is_read_as_stored(self, frames):
        assert sorted(frames) == TABLES
        assert all(len(frames[t]) == len(pd.read_parquet(REPO / "data" / f"{t}.parquet")) for t in TABLES)

    def test_a_psycopg_error_is_described_by_its_names_only(self):
        import psycopg
        with pytest.raises(psycopg.Error) as raised:
            psycopg.connect(f"postgresql://u:{SENTINEL}@/d?bogus=1")
        assert pg.describe(raised.value) == type(raised.value).__name__

    @pytest.mark.parametrize("text", [
        f"bad value '{SENTINEL}",
        f'bad value "{SENTINEL}',
        f"bad value '{SENTINEL}' and then \"{SENTINEL}",
    ])
    def test_scrub_drops_a_quote_that_never_closes(self, text):
        assert SENTINEL not in pg.scrub(text)
        assert pg.scrub(text).startswith("bad value <quoted>")

    def test_a_non_database_error_with_an_open_quote_prints_no_value(self, monkeypatch, capsys):
        monkeypatch.setenv(pg.URL_ENV, "postgresql://u@h/d")
        monkeypatch.setattr(backfill, "published_frames", lambda: {})

        def failing(url, frames, **kwargs):
            raise ValueError(f"cannot cast 'x{SENTINEL}")

        monkeypatch.setattr(backfill, "run", failing)
        assert backfill.main([]) == 1
        out = said(capsys)
        assert "ValueError: cannot cast <quoted>" in out
        assert SENTINEL not in out and "Traceback" not in out

    def test_scrub_drops_quoted_values_and_keeps_the_first_line(self):
        text = f'invalid input syntax for type integer: "{SENTINEL}"\nDETAIL: Key (a)=(\'{SENTINEL}\')'
        assert pg.scrub(text) == "invalid input syntax for type integer: <quoted>"

    def test_a_value_out_of_a_whole_number_column_is_not_echoed(self):
        with pytest.raises(pg.WriteRefused) as raised:
            pg._python(1234567.5, "integer", "t.c")
        assert "1234567" not in str(raised.value)


class TestLoginProblems:
    GOOD = {"user": "etl_writer", "bypass_rls": False, "superuser": False, "rls": {"a": True, "b": True}}

    def test_the_expected_login_has_no_problem(self):
        assert pg.login_problems(self.GOOD, ["a", "b"]) == []

    @pytest.mark.parametrize("change, expected", [
        ({"user": "postgres"}, "connected as postgres, expected etl_writer"),
        ({"bypass_rls": True}, "the login has BYPASSRLS"),
        ({"superuser": True}, "the login is a superuser"),
        ({"rls": {"a": True, "b": False}}, "football.b: row-level security is off"),
        ({"rls": {"a": True}}, "football.b: no such table"),
        ({"rls": {"a": True, "b": True, "c": False}}, "football.c: row-level security is off"),
    ])
    def test_each_departure_is_named(self, change, expected):
        assert expected in pg.login_problems({**self.GOOD, **change}, ["a", "b"])


class TestDifferences:
    PUBLISHED = pd.DataFrame({"k": [1, 2, 3], "v": [1.5, float("nan"), 3.5],
                              "s": pd.array(["a", None, "c"], dtype="string")})

    def read_back(self):
        return pd.DataFrame({"k": [3, 1, 2], "v": [3.5, 1.5, float("nan")],
                             "s": pd.Series(["c", "a", None], dtype="str")})

    def test_equal_frames_in_any_order_and_text_flavour_have_no_difference(self):
        assert pg.differences(self.read_back(), self.PUBLISHED, ENTRY) == []

    def test_an_empty_table_is_compared_not_skipped(self):
        empty = self.PUBLISHED.iloc[:0]
        assert pg.differences(None, empty, ENTRY) == []
        assert pg.differences(None, self.PUBLISHED, ENTRY) == ["t: 0 row(s) read back, 3 published"]
        assert pg.differences(self.PUBLISHED, empty, ENTRY) == ["t: 3 row(s) read back, 0 published"]

    def test_a_changed_cell_is_counted_and_never_shown(self):
        got = self.read_back()
        got.loc[0, "s"] = SENTINEL
        got.loc[1, "v"] = 99.25
        lines = pg.differences(got, self.PUBLISHED, ENTRY)
        assert lines == ["t.v: 1 cell(s) differ", "t.s: 1 cell(s) differ"]
        assert SENTINEL not in " ".join(lines) and "99.25" not in " ".join(lines)

    def test_a_null_against_a_value_differs(self):
        got = self.read_back()
        got.loc[0, "s"] = None
        assert pg.differences(got, self.PUBLISHED, ENTRY) == ["t.s: 1 cell(s) differ"]

    def test_a_different_dtype_is_named(self):
        got = self.read_back().astype({"v": "object"})
        assert pg.differences(got, self.PUBLISHED, ENTRY) == ["t.v: object read back, float64 published"]


class TestTheWorkflow:
    @pytest.fixture
    def workflow(self):
        text = (REPO / ".github" / "workflows" / "backfill.yml").read_text(encoding="utf-8")
        return text, yaml.safe_load(text)

    def test_only_the_owner_can_start_it_and_it_takes_no_input(self, workflow):
        _, doc = workflow
        triggers = doc.get("on", doc.get(True))
        assert set(triggers) == {"workflow_dispatch"}
        assert not (triggers["workflow_dispatch"] or {}).get("inputs")

    def test_it_reads_the_repo_and_runs_in_the_etl_environment(self, workflow):
        _, doc = workflow
        assert doc["permissions"] == {"contents": "read"}
        (job,) = doc["jobs"].values()
        assert job["environment"] == "etl"

    def test_every_action_is_pinned_to_a_commit(self, workflow):
        text, _ = workflow
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", text, flags=re.M)
        assert uses
        for ref in uses:
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), ref

    def test_it_runs_the_script_without_replace_and_only_that_step_holds_the_secret(self, workflow):
        _, doc = workflow
        (job,) = doc["jobs"].values()
        runs = [s["run"] for s in job["steps"] if "run" in s]
        assert "python scripts/backfill_postgres.py" in runs
        assert not any("--replace" in r for r in runs)
        holders = [s for s in job["steps"] if "SUPABASE_DB_URL" in (s.get("env") or {})]
        assert len(holders) == 1 and holders[0]["run"] == "python scripts/backfill_postgres.py"
        assert holders[0]["env"]["SUPABASE_DB_URL"] == "${{ secrets.SUPABASE_DB_URL }}"
        assert holders[0]["env"]["ETL_STORAGE"] == "postgres"
        assert "env" not in job
