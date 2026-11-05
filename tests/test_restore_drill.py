"""The restore drill (#138): scripts/restore_drill.py.

The database cases run against TEST_DATABASE_URL only (the throwaway Postgres
of the storage-pg CI job, reached as etl_writer) and skip without it;
REQUIRE_TEST_DATABASE=1 makes that a failure. The cases that need no database
(the checksum query's shape, --print-sql, the refusals before a connection)
always run. Nothing here reaches the real project: the conftest autouse
fixture removes SUPABASE_DB_URL and the script never reads it.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pandas as pd
import pytest

import backfill_postgres as backfill
import etl_helpers as etl
import etl_storage_pg as pg
import restore_drill as drill
from test_etl_storage import TABLES, database_url

pytestmark = pytest.mark.pg

SENTINEL = "SENTINEL-6203"
LINE = re.compile(r"^(\w+) (\d+) ([0-9a-f]{32})$")
FORBIDDEN = re.compile(r"\b(SET|CREATE|TEMP|TEMPORARY|INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b")


@pytest.fixture(scope="module")
def frames():
    return backfill.published_frames()


@pytest.fixture
def db():
    """The test database with every football table empty, before and after."""
    url = database_url()
    pg.clear_published(url, TABLES)
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


def drilled(url, frames):
    lines = []
    code = drill.run(url, frames, out=lines.append)
    return code, lines


def sums(lines):
    found = {}
    for line in lines:
        hit = LINE.match(line)
        if hit:
            found[hit.group(1)] = (int(hit.group(2)), hit.group(3))
    return found


def a_loose_text_cell(frames):
    """(table, column, row label) of a text cell in a column no key, check,
    index or foreign key mentions, so changing it still loads."""
    state = pg._state()
    tied = json.dumps([[s["pk"], s["fks"], s["checks"], s["indexes"]] for s in state.values()])
    for name in sorted(frames):
        spec, frame = state[name], frames[name]
        for col in spec["columns"]:
            if col["sql_type"] != "text" or f'"{col["name"]}"' in tied or col["name"] in spec["pk"]:
                continue
            live = frame[col["name"]].dropna()
            if len(live):
                return name, col["name"], live.index[0]
    pytest.skip("no published table has a loose text cell")


class TestTheDrillOnTheDatabase:
    def test_the_published_snapshot_drills_clean_and_prints_a_line_per_table(self, db, frames, capsys):
        lines = []

        def out(text):
            lines.append(text)
            print(text)

        with capsys.disabled():
            print()
            code = drill.run(db, frames, out=out)
        assert code == 0
        found = sums(lines)
        assert sorted(found) == TABLES
        for table in TABLES:
            rows = len(pd.read_parquet(REPO / "data" / f"{table}.parquet"))
            assert found[table][0] == rows
        assert lines[-1].startswith("snapshot ") and f"{len(TABLES)} table(s)" in lines[-1]
        assert held(db) == []

    def test_the_checksum_does_not_depend_on_row_order(self, db, frames):
        first = drilled(db, frames)
        shuffled = {name: frame.sample(frac=1, random_state=7).reset_index(drop=True)
                    for name, frame in frames.items()}
        second = drilled(db, shuffled)
        assert first[0] == second[0] == 0
        assert sums(first[1]) == sums(second[1])

    def test_one_changed_cell_changes_that_tables_checksum_and_no_other(self, db, frames):
        name, column, label = a_loose_text_cell(frames)
        base = drilled(db, frames)
        edited = frames[name].copy()
        edited.loc[label, column] = str(edited.loc[label, column]) + "~"
        after = drilled(db, {**frames, name: edited})
        assert base[0] == after[0] == 0
        before, now = sums(base[1]), sums(after[1])
        assert before[name][0] == now[name][0]
        assert before[name][1] != now[name][1]
        assert {t: v for t, v in before.items() if t != name} == {t: v for t, v in now.items() if t != name}

    def test_an_empty_table_has_a_count_of_zero_and_the_fixed_value(self, db):
        import psycopg
        with psycopg.connect(db) as conn:
            lines = drill.checksum_lines(conn, TABLES)
        assert sorted(sums(lines)) == TABLES
        assert all(v == (0, drill.EMPTY) for v in sums(lines).values())

    def test_the_printed_sql_run_on_the_database_gives_the_lines_the_drill_printed(self, db, frames, monkeypatch, capsys):
        import psycopg
        real = pg.clear_published
        monkeypatch.setattr(pg, "clear_published", lambda url, names: None)
        try:
            code, lines = drilled(db, frames)
            assert code == 0 and held(db)
            capsys.readouterr()
            assert drill.main(["--print-sql"]) == 0
            statement = capsys.readouterr().out
            with psycopg.connect(db) as conn:
                conn.read_only = True
                rows = conn.execute(statement).fetchall()
            assert sorted(f"{t} {n} {c}" for t, n, c in rows) == sorted(l for l in lines if LINE.match(l))
        finally:
            monkeypatch.undo()
            real(db, TABLES)

    def test_a_non_empty_table_is_refused_and_nothing_is_written_or_cleared(self, db, frames):
        assert pg.load_published(db, frames, replace=False).problems == []
        code, lines = drilled(db, frames)
        assert code == 2
        assert any("already holds rows" in line for line in lines) and lines[-1] == "nothing was written"
        for table in TABLES:
            assert count(db, table) == len(frames[table])

    def test_another_url_is_refused_before_any_write(self, db, frames):
        other = db + ("&" if "?" in db else "?") + "application_name=other"
        code, lines = drilled(other, frames)
        assert code == 2 and lines[-1] == "nothing was written"
        assert held(db) == []

    def test_another_login_is_refused_before_any_write(self, db, frames, monkeypatch):
        real = pg.login_facts
        monkeypatch.setattr(pg, "login_facts", lambda conn: {**real(conn), "user": "postgres", "superuser": True})
        code, lines = drilled(db, frames)
        assert code == 2
        assert any("connected as postgres, expected etl_writer" in line for line in lines)
        assert held(db) == []

    def test_a_refused_load_exits_1_prints_no_value_and_leaves_the_database_empty(self, db, frames, monkeypatch, capsys):
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
        monkeypatch.setenv(pg.TEST_URL_ENV, db)
        assert drill.main([]) == 1
        seen = capsys.readouterr()
        out = seen.out + seen.err
        assert f"{name}: refused: NotNullViolation SQLSTATE 23502" in out
        assert "rolled back; nothing was committed" in out
        assert SENTINEL not in out and "DETAIL" not in out and "Traceback" not in out
        assert held(db) == []

    def test_an_error_after_the_load_prints_one_scrubbed_line_and_still_empties_the_database(
            self, db, frames, monkeypatch, capsys):
        def failing(conn, tables):
            raise RuntimeError(f"cannot read '{SENTINEL}' today")

        monkeypatch.setattr(drill, "checksum_lines", failing)
        monkeypatch.setattr(backfill, "published_frames", lambda: frames)
        monkeypatch.setenv(pg.TEST_URL_ENV, db)
        assert drill.main([]) == 1
        seen = capsys.readouterr()
        out = seen.out + seen.err
        assert out.strip() == "stopped: RuntimeError: cannot read <quoted> today"
        assert held(db) == []


class TestWithoutADatabase:
    def test_print_sql_connects_to_nothing_and_prints_one_read_only_statement(self, monkeypatch, capsys):
        import psycopg

        def no_connection(*args, **kwargs):
            raise AssertionError("--print-sql opened a connection")

        monkeypatch.setattr(psycopg, "connect", no_connection)
        for name in (pg.TEST_URL_ENV, pg.URL_ENV, "GITHUB_SHA"):
            monkeypatch.delenv(name, raising=False)
        assert drill.main(["--print-sql"]) == 0
        statement = capsys.readouterr().out.strip()
        assert statement.startswith("SELECT ")
        assert ";" not in statement
        assert statement.count("\nUNION ALL\n") == len(TABLES) - 1
        assert not FORBIDDEN.search(statement)
        for table in TABLES:
            assert f'FROM "football"."{table}"' in statement

    def test_the_query_renders_every_column_without_a_session_setting(self):
        state = pg._state()
        statement = drill.checksum_sql(TABLES)
        typed = [(c["name"], c["sql_type"], c["name"] in state[t]["pk"])
                 for t in TABLES for c in state[t]["columns"]]
        keys = sum(len(state[t]["pk"]) for t in TABLES)
        for sql_type, marker in (("double precision", "float8send"), ("timestamptz", "AT TIME ZONE 'UTC'")):
            assert statement.count(marker) == sum(2 if key else 1 for _, kind, key in typed if kind == sql_type)
        assert statement.count('COLLATE "C"') == keys
        for table in TABLES:
            for column in etl._table_entry(table)["columns"]:
                assert f'"{column["name"]}"' in statement
        assert drill.EMPTY == hashlib.md5(b"").hexdigest()

    def test_columns_run_in_registry_order(self):
        table = next(t for t in TABLES if len(etl._table_entry(t)["columns"]) > 2)
        names = [c["name"] for c in etl._table_entry(table)["columns"]]
        branch = drill.checksum_sql([table])
        positions = [branch.index(f'"{n}"') for n in names]
        assert positions == sorted(positions)

    def test_a_url_other_than_the_test_database_is_refused_without_a_connection(self, monkeypatch):
        import psycopg
        monkeypatch.setattr(psycopg, "connect", lambda *a, **k: pytest.fail("a connection was opened"))
        lines = []
        monkeypatch.setenv(pg.TEST_URL_ENV, "postgresql://u@test/d")
        assert drill.run("postgresql://u@live/d", {"dim_season": pd.DataFrame()}, out=lines.append) == 2
        assert lines[-1] == "nothing was written"
        monkeypatch.delenv(pg.TEST_URL_ENV)
        assert drill.run("postgresql://u@test/d", {"dim_season": pd.DataFrame()}, out=lines.append) == 2

    def test_no_test_database_url_is_refused(self, monkeypatch, capsys):
        monkeypatch.delenv(pg.TEST_URL_ENV, raising=False)
        assert drill.main([]) == 2
        assert "TEST_DATABASE_URL is not set" in capsys.readouterr().out

    def test_the_script_never_names_the_live_login_or_takes_a_url(self):
        text = Path(drill.__file__).read_text(encoding="utf-8")
        assert "SUPABASE_DB_URL" not in text and "URL_ENV" not in text.replace("TEST_URL_ENV", "")
        assert "--url" not in text
        assert text.count("add_argument(") == 1

    def test_the_snapshot_commit_is_a_hash_or_unknown(self, monkeypatch):
        monkeypatch.setenv("GITHUB_SHA", "a" * 40)
        assert drill.snapshot_commit() == "a" * 40
        monkeypatch.setenv("GITHUB_SHA", "not a hash; echo hi")
        assert re.fullmatch(r"[0-9a-f]{7,64}|unknown", drill.snapshot_commit())
