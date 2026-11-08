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
ZONE = "Asia/Kolkata"

FETCH_METHODS = {"fetchone", "fetchall", "fetchmany", "stream", "stream_dict",
                 "read_sql", "read_sql_query", "read_sql_table"}
CURSOR_MAKERS = {"execute", "cursor", "stream"}
MODULE = "<module>"

# The functions of each psycopg module that may fetch. A scalar probe (a
# count, an EXISTS, a catalog row, a checksum) or read_on, which reads a table
# in binary. A new fetching function, or a fetch at module level, fails.
PG_MODULES = {
    "notebooks/etl_storage_pg.py": {
        "read_on", "breaks", "orphans", "login_facts", "nonempty", "has_rows",
        "write", "write_all_empty", "_copy", "load_published", "_fk_where"},
    "notebooks/etl_run_log.py": {"_count", "_rows"},
    "scripts/backfill_postgres.py": set(),
    "scripts/restore_drill.py": {"checksum_lines"},
}


def fetching_functions(source):
    """Every function (or MODULE) in `source` that reads rows through psycopg:
    fetchone/fetchall/fetchmany/stream, pd.read_sql*, cursor.copy(<args>), or a
    loop over a cursor or an execute() result."""
    tree = ast.parse(source)
    found = set()

    def attr(node):
        return node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else None)

    def cursor_names(scope):
        names = set()
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and attr(node.value) in CURSOR_MAKERS:
                names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
            if isinstance(node, ast.With):
                for item in node.items:
                    if (isinstance(item.context_expr, ast.Call) and attr(item.context_expr) in CURSOR_MAKERS
                            and isinstance(item.optional_vars, ast.Name)):
                        names.add(item.optional_vars.id)
        return names

    def visit(scope, name):
        cursors = cursor_names(scope)
        stack = list(ast.iter_child_nodes(scope))
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(node, node.name)
                continue
            stack.extend(ast.iter_child_nodes(node))
            if isinstance(node, ast.Call):
                called = attr(node)
                if called in FETCH_METHODS or (called == "copy" and (node.args or node.keywords)):
                    found.add(name)
            iters = []
            if isinstance(node, (ast.For, ast.AsyncFor)):
                iters.append(node.iter)
            if isinstance(node, ast.comprehension):
                iters.append(node.iter)
            for it in iters:
                if (isinstance(it, ast.Call) and attr(it) in CURSOR_MAKERS) or (
                        isinstance(it, ast.Name) and it.id in cursors):
                    found.add(name)

    visit(tree, MODULE)
    return found


class TestNoReadBypassesReadOn:
    @pytest.mark.parametrize("rel", sorted(PG_MODULES))
    def test_only_the_known_functions_fetch_rows(self, rel):
        source = (REPO / rel).read_text(encoding="utf-8")
        assert sorted(fetching_functions(source) - PG_MODULES[rel]) == [], rel

    def test_read_on_reads_in_binary(self):
        source = PG_SOURCE.read_text(encoding="utf-8")
        body = source.split("def read_on", 1)[1].split("\ndef ", 1)[0]
        assert "binary=True" in body and "fetchall" in body

    @pytest.mark.parametrize("body", [
        "def sneaky(conn):\n    return conn.execute('SELECT 1').fetchall()\n",
        "def sneaky(conn):\n    return conn.execute('SELECT 1').fetchone()\n",
        "def sneaky(cur):\n    return cur.fetchmany(5)\n",
        "def sneaky(conn):\n    return [r for r in conn.execute('SELECT 1')]\n",
        "def sneaky(conn):\n    cur = conn.execute('SELECT 1')\n    for r in cur:\n        print(r)\n",
        "def sneaky(conn):\n    with conn.cursor() as cur:\n        return [r for r in cur]\n",
        "def sneaky(cur):\n    return list(cur.stream('SELECT 1'))\n",
        "def sneaky(cur):\n    with cur.copy('COPY t TO STDOUT') as c:\n        return c.read()\n",
        "def sneaky(conn):\n    import pandas as pd\n    return pd.read_sql('SELECT 1', conn)\n",
    ])
    def test_the_guard_sees_a_new_fetching_function(self, body):
        assert fetching_functions(body) == {"sneaky"}

    def test_the_guard_sees_a_module_level_read(self):
        assert fetching_functions("import psycopg\nROWS = psycopg.connect('').execute('x').fetchall()\n") == {MODULE}

    def test_the_guard_ignores_a_dataframe_copy_and_a_plain_loop(self):
        assert fetching_functions("def fine(df, xs):\n    for x in xs:\n        pass\n    return df.copy()\n") == set()


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

    def test_every_ops_timestamptz_column_round_trips_under_a_non_utc_session(self):
        import datetime as dt
        import psycopg
        from psycopg import sql
        url = database_url()
        ops = {f"{spec['schema']}.{spec['name']}": spec
               for spec in pg._state().values() if spec["schema"] == "ops"}
        stamped = {key: [c["name"] for c in spec["columns"] if c["sql_type"] == "timestamptz"]
                   for key, spec in ops.items()}
        stamped = {key: cols for key, cols in stamped.items() if cols}
        assert {"ops.etl_run_log", "ops.review_check", "ops.review_fantrax_crosswalk"} <= set(stamped)
        want = dt.datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=dt.timezone.utc)
        with psycopg.connect(with_options(url, f"-c TimeZone={ZONE}")) as conn:
            assert conn.execute("SHOW TimeZone").fetchone()[0] == ZONE
            for key, cols in sorted(stamped.items()):
                table = sql.Identifier(ops[key]["schema"], ops[key]["name"])
                idents = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
                conn.execute(sql.SQL("CREATE TEMP TABLE probe ON COMMIT DROP AS "
                                     "SELECT {} FROM {} WITH NO DATA").format(idents, table))
                conn.execute(sql.SQL("INSERT INTO probe ({}) VALUES ({})").format(
                    idents, sql.SQL(", ").join(sql.SQL("'2026-01-02 03:04:05.678+00'::timestamptz") for _ in cols)))
                got = conn.execute("SELECT * FROM probe", binary=True).fetchall()
                assert got == [tuple(want for _ in cols)], key
                conn.execute("DROP TABLE probe")

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
