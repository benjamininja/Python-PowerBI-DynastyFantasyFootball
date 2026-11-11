"""The owner's delete of the rejected sources (#459, B10):
scripts/delete_rejected_sources.py, run on a fake connection. Nothing here
reaches a database: the fake answers the script's SQL from a dict of counts, and
conftest removes SUPABASE_DB_URL before every case.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "notebooks"))
sys.path.insert(0, str(REPO / "scripts"))

import pytest

import delete_rejected_sources as delete
import etl_helpers as etl
import etl_storage_pg as pg

SENTINEL = "SENTINEL-4471"
COUNT = re.compile(r'SELECT count\(\*\) FROM football\."(\w+)" WHERE "(\w+)" = %s')
DELETE = re.compile(r'DELETE FROM football\."(\w+)" WHERE "(\w+)" = ANY\(%s\)')


def expected():
    return {(t.table, source): n for t in delete.TARGETS for source, n in t.sources}


class Cursor:
    def __init__(self, rows=(), rowcount=-1):
        self.rows, self.rowcount = list(rows), rowcount

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


class FakeConnection:
    """What the script asks of a psycopg connection, over a dict of counts.
    A commit keeps the counts, a rollback puts back those of the last commit.
    `stuck` rows survive a DELETE, as a row a concurrent writer added would."""

    def __init__(self, held=None, stuck=None, user="etl_writer", bypass=False,
                 superuser=False, rls=True):
        self.state = dict(held if held is not None else expected())
        self.saved = dict(self.state)
        self.stuck = stuck or {}
        self.facts = (user, bypass, superuser)
        self.rls = rls
        self.read_only = False
        self.log = []
        self.events = []
        self.deleted = []

    def __enter__(self):
        return self

    def __exit__(self, kind, value, trace):
        if kind:
            self.rollback()
        return False

    def commit(self):
        self.events.append("commit")
        self.saved = dict(self.state)

    def rollback(self):
        self.events.append("rollback")
        self.state = dict(self.saved)

    def execute(self, query, params=None):
        self.log.append(query)
        if "pg_roles" in query:
            return Cursor([self.facts])
        if "pg_class" in query:
            return Cursor([(t.table, self.rls) for t in delete.TARGETS])
        found = COUNT.match(query)
        if found:
            table, column = found.groups()
            target = next(t for t in delete.TARGETS if t.table == table)
            assert column == target.column, f"{table} counted on {column}"
            return Cursor([(self.state[(table, params[0])],)])
        found = DELETE.match(query)
        if found:
            table, column = found.groups()
            target = next(t for t in delete.TARGETS if t.table == table)
            assert column == target.column, f"{table} deleted on {column}"
            assert list(params[0]) == [s for s, _ in target.sources]
            self.deleted.append(table)
            removed = 0
            for source in params[0]:
                left = self.stuck.get((table, source), 0)
                removed += self.state[(table, source)] - left
                self.state[(table, source)] = left
            return Cursor(rowcount=removed)
        assert query.startswith("SET "), query
        return Cursor()


def run(conn, apply=False):
    lines = []
    code = delete.run("postgresql://unused", apply=apply, out=lines.append, connector=lambda url: conn)
    return code, "\n".join(lines)


class TestTheTargets:
    def test_each_table_and_column_is_in_the_registry(self):
        registry = etl._registry()
        for t in delete.TARGETS:
            assert t.table in registry, t.table
            assert t.column in [c["name"] for c in registry[t.table]["columns"]], (t.table, t.column)

    def test_the_fact_rows_come_before_the_metric_dim_which_comes_last(self):
        tables = [t.table for t in delete.TARGETS]
        assert tables[-1] == "dim_dynasty_metric"
        assert tables.index("fact_dynasty_ranking_metrics") < tables.index("dim_dynasty_metric")

    def test_the_expected_counts_are_459s(self):
        assert expected() == {
            ("fact_dynasty_ranking_metrics", "KTC"): 15730, ("fact_dynasty_ranking_metrics", "FantasyPros"): 3966,
            ("dim_dynasty_metric", "KTC"): 17, ("dim_dynasty_metric", "FantasyPros"): 6,
            ("fact_rookie_rankings", "KeepTradeCut"): 54, ("fact_rookie_rankings", "FantasyPros"): 422,
            ("dim_dynasty_crosswalk", "KTC"): 464, ("dim_dynasty_crosswalk", "FantasyPros"): 661,
            ("dim_pick_value_curve", "KTC"): 36}


class TestTheDryRun:
    def test_it_prints_each_count_beside_the_expected_one_and_deletes_nothing(self):
        conn = FakeConnection()
        code, out = run(conn)
        assert code == 0
        assert conn.read_only
        assert conn.deleted == [] and conn.events == []
        assert not any(q.startswith(("DELETE", "SET LOCAL")) for q in conn.log)
        assert conn.state == expected()
        assert "fact_dynasty_ranking_metrics where source_name = KTC: 15730 row(s) would be deleted " \
               "(#459 expects 15730: match)" in out
        assert "fact_rookie_rankings where source_site = KeepTradeCut: 54 row(s)" in out
        assert "dim_pick_value_curve where source_name = KTC: 36 row(s)" in out
        assert len([line for line in out.splitlines() if "#459 expects" in line]) == 9
        assert "counts match #459's" in out and "dry run: nothing was deleted" in out

    def test_a_count_that_differs_exits_1_after_printing_every_table_with_DIFFERS_beside_it(self):
        held = {**expected(), ("dim_dynasty_crosswalk", "FantasyPros"): 660}
        conn = FakeConnection(held=held)
        code, out = run(conn)
        assert code == 1
        assert len([line for line in out.splitlines() if "#459 expects" in line]) == 9
        assert [line for line in out.splitlines() if "DIFFERS)" in line] == [
            "dim_dynasty_crosswalk where source = FantasyPros: 660 row(s) would be deleted "
            "(#459 expects 661: DIFFERS)"]
        assert "counts DIFFER from #459's: do not --apply" in out
        assert conn.deleted == [] and conn.state == held

    def test_main_with_no_flag_is_a_dry_run(self, monkeypatch, capsys):
        conn = FakeConnection()
        monkeypatch.setenv(pg.URL_ENV, "postgresql://unused")
        monkeypatch.setattr(delete, "connect", lambda url: conn)
        assert delete.main([]) == 0
        assert conn.deleted == [] and "dry run" in capsys.readouterr().out


class TestTheApply:
    def test_it_deletes_the_facts_before_the_metric_dim_and_commits_at_zero(self):
        conn = FakeConnection()
        code, out = run(conn, apply=True)
        assert code == 0
        assert not conn.read_only
        assert conn.deleted == [t.table for t in delete.TARGETS]
        assert conn.deleted[-1] == "dim_dynasty_metric"
        assert conn.events == ["commit"]
        assert all(n == 0 for n in conn.state.values())
        assert "fact_dynasty_ranking_metrics: 19696 row(s) deleted" in out
        assert "committed: 21356 row(s) deleted from 5 table(s); every count is zero" in out

    def test_the_locks_are_bounded_and_the_keys_checked_inside_the_transaction(self):
        conn = FakeConnection()
        run(conn, apply=True)
        first_delete = next(i for i, q in enumerate(conn.log) if q.startswith("DELETE"))
        last_delete = max(i for i, q in enumerate(conn.log) if q.startswith("DELETE"))
        recount = max(i for i, q in enumerate(conn.log) if q.startswith("SELECT count"))
        assert conn.log.index("SET CONSTRAINTS ALL IMMEDIATE") > last_delete
        assert conn.log.index("SET CONSTRAINTS ALL IMMEDIATE") < recount
        assert any(q.startswith("SET LOCAL lock_timeout") for q in conn.log[:first_delete])

    def test_a_count_that_differs_from_459s_rolls_back_before_any_delete(self):
        held = {**expected(), ("fact_dynasty_ranking_metrics", "KTC"): 15729}
        conn = FakeConnection(held=held)
        code, out = run(conn, apply=True)
        assert code == 1
        assert conn.deleted == []
        assert not any(q.startswith(("DELETE", "SET ")) for q in conn.log)
        assert conn.events == ["rollback"]
        assert conn.state == held
        assert "fact_dynasty_ranking_metrics where source_name = KTC: 15729 row(s) found " \
               "(#459 expects 15730: DIFFERS)" in out
        assert "counts DIFFER from #459's; rolled back; nothing was deleted" in out
        assert "committed" not in out

    def test_a_count_that_is_not_zero_after_the_delete_rolls_everything_back(self):
        conn = FakeConnection(stuck={("fact_rookie_rankings", "FantasyPros"): 2})
        code, out = run(conn, apply=True)
        assert code == 1
        assert conn.events == ["rollback"]
        assert conn.state == expected()
        assert "fact_rookie_rankings where source = FantasyPros: 2 row(s) left" in out
        assert "rolled back; nothing was deleted" in out
        assert "committed" not in out

    def test_an_error_inside_the_transaction_rolls_back_and_prints_no_value(self, monkeypatch, capsys):
        conn = FakeConnection()
        real = conn.execute

        def failing(query, params=None):
            if query.startswith("SET CONSTRAINTS"):
                raise RuntimeError(f"insert or update violates 'metric_key' = '{SENTINEL}'")
            return real(query, params)

        conn.execute = failing
        monkeypatch.setenv(pg.URL_ENV, "postgresql://unused")
        monkeypatch.setattr(delete, "connect", lambda url: conn)
        assert delete.main(["--apply"]) == 1
        out = capsys.readouterr()
        assert "stopped, nothing was committed: RuntimeError" in out.out
        assert SENTINEL not in out.out + out.err and "Traceback" not in out.out + out.err
        assert conn.events == ["rollback"]
        assert conn.state == expected()


class TestTheUrlIsNeverPrinted:
    URL = "postgresql://etl_writer.projref:hunter2-pw@aws-0.pooler.example.com:5432/postgres"

    @pytest.mark.parametrize("message", [
        f"could not reach {URL}",
        f"{URL} refused the connection",
        "password hunter2-pw rejected for etl_writer.projref@aws-0.pooler.example.com:5432",
        f"bad dsn 'x'\nsecond line {URL}",
    ])
    @pytest.mark.parametrize("flag", [[], ["--apply"]])
    def test_an_error_that_holds_the_url_prints_neither_it_nor_its_password(self, monkeypatch, capsys,
                                                                            message, flag):
        def failing(url):
            raise RuntimeError(message)

        monkeypatch.setenv(pg.URL_ENV, self.URL)
        monkeypatch.setattr(delete, "connect", failing)
        assert delete.main(flag) == 1
        seen = capsys.readouterr()
        shown = seen.out + seen.err
        assert shown.startswith("stopped, nothing was committed: RuntimeError")
        for secret in (self.URL, "hunter2-pw", "etl_writer.projref", "pooler.example.com"):
            assert secret not in shown
        assert "Traceback" not in shown

    def test_a_refusal_or_a_result_line_never_holds_it(self, monkeypatch, capsys):
        conn = FakeConnection(bypass=True)
        monkeypatch.setenv(pg.URL_ENV, self.URL)
        monkeypatch.setattr(delete, "connect", lambda url: conn)
        assert delete.main([]) == 2
        shown = capsys.readouterr().out
        assert "hunter2-pw" not in shown and "pooler.example.com" not in shown


class TestTheRefusal:
    @pytest.mark.parametrize("kwargs, said", [
        ({"bypass": True}, "the login has BYPASSRLS"),
        ({"superuser": True}, "the login is a superuser"),
        ({"user": "postgres"}, "connected as postgres, expected etl_writer"),
        ({"rls": False}, "row-level security is off"),
    ])
    @pytest.mark.parametrize("apply", [False, True])
    def test_a_login_that_is_not_etl_writer_without_bypass_is_refused_before_any_count_or_write(
            self, kwargs, said, apply):
        conn = FakeConnection(**kwargs)
        code, out = run(conn, apply=apply)
        assert code == 2
        assert said in out and "nothing was deleted" in out
        assert not any(q.startswith(("DELETE", "SELECT count", "SET ")) for q in conn.log)
        assert conn.events == [] and conn.state == expected()

    def test_no_url_is_a_refusal(self, monkeypatch, capsys):
        monkeypatch.setattr(delete, "connect", lambda url: pytest.fail("connected"))
        assert delete.main(["--apply"]) == 2
        assert f"refused: {pg.URL_ENV} is not set" in capsys.readouterr().out

    def test_the_url_comes_from_the_variable_the_seam_uses(self):
        assert pg.URL_ENV == "SUPABASE_DB_URL"
        assert delete.database_url() is None
