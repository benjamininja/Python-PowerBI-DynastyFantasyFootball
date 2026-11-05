"""ops.etl_run_log, written by scripts/run_pipeline.py (#137, ADR-0018
decision 11).

The unit cases need no server. The [pg] cases run main() against the
throwaway database in TEST_DATABASE_URL, as the etl_writer login; with it
unset they skip, and REQUIRE_TEST_DATABASE=1 (the storage-pg CI job) makes a
skip a failure. A case never touches a row it did not insert.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_run_log as rl  # noqa: E402
import run_pipeline as rp  # noqa: E402

SENTINEL = "SENTINEL-CELL-VALUE-91827"
UNREACHABLE = "postgresql://runlog_user:hunter2-pw@127.0.0.1:1/none"
HEAD = "a" * 40


def database_url():
    required = bool(os.environ.get("REQUIRE_TEST_DATABASE"))
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if required:
            pytest.fail("REQUIRE_TEST_DATABASE is set but TEST_DATABASE_URL is not", pytrace=False)
        pytest.skip("TEST_DATABASE_URL is not set")
    try:
        import psycopg  # noqa: F401
    except ImportError:
        if required:
            pytest.fail("REQUIRE_TEST_DATABASE is set but psycopg is not installed", pytrace=False)
        pytest.skip("psycopg is not installed")
    return url


class Pipeline:
    """main() with the steps, checks, commit and Discord stubbed out."""

    def __init__(self, monkeypatch, tmp_path):
        self.mp = monkeypatch
        self.notified = []
        self.committed = []
        self.results = [{"name": "s1", "status": "ok", "detail": ""}]
        self.commit_line = "committed + pushed 1 parquet file(s) to main"
        self.mid_run = None
        self.counts = {"dim_a": 3}
        mp = monkeypatch
        mp.setattr(rp, "_load_04a", lambda: SimpleNamespace(
            CFG=None, derive_week_label=lambda cfg: "PRE"))
        mp.setattr(rp, "derive_phase", lambda: "OFFSEASON")
        mp.setattr(rp, "build_steps", lambda profile: [{"name": "s1", "chain": "c1"}])
        mp.setattr(rp, "run_steps", self._run_steps)
        mp.setattr(rp.etl_checks, "load_registry", lambda: {})
        mp.setattr(rp.etl_checks, "chain_tables", lambda reg: {"c1": ["dim_a"]})
        mp.setattr(rp.etl_checks, "run_suite", lambda tables=None, accept=None: [])
        mp.setattr(rp.etl_checks, "file_review",
                   lambda results, run_id: {"open": 0, "opened": 0, "cleared": 0, "repeated": 0})
        mp.setattr(rp, "review_counts", lambda: {})
        mp.setattr(rp, "commit_data", self._commit_data)
        mp.setattr(rp, "notify", self.notified.append)
        mp.setattr(rp, "OUT_DIR", tmp_path)
        mp.setattr(rl, "head_sha", lambda repo: HEAD)
        mp.setattr(rl, "row_counts", lambda tables: {t: self.counts[t] for t in tables})
        self.summary_file = tmp_path / "pipeline_summary.md"

    def _run_steps(self, steps, phase, only, dry_run, groups=None):
        if self.mid_run:
            self.mid_run()
        if isinstance(self.results, BaseException):
            raise self.results
        return self.results

    def _commit_data(self, *args, **kwargs):
        self.committed.append(kwargs)
        return self.commit_line

    def run(self, *argv):
        self.mp.setattr(sys, "argv", ["run_pipeline.py", *argv])
        return rp.main()


@pytest.fixture
def pipe(monkeypatch, tmp_path):
    return Pipeline(monkeypatch, tmp_path)


class TestHelpers:
    def test_first_line_is_one_line_without_the_url_or_password(self, monkeypatch):
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)
        exc = RuntimeError(f"bad {UNREACHABLE} for hunter2-pw\nDETAIL: Failing row contains ({SENTINEL})")
        line = rl.first_line(exc)
        assert "\n" not in line
        for hidden in (UNREACHABLE, "hunter2-pw", "DETAIL", SENTINEL):
            assert hidden not in line

    def test_first_line_of_an_empty_message_names_the_error_type(self):
        assert rl.first_line(KeyError()) == "KeyError"

    def test_status(self):
        assert rl.final_status(1, "committed + pushed 2 parquet file(s) to main") == "failed"
        assert rl.final_status(0, "committed + pushed 2 parquet file(s) to main") == "published"
        assert rl.final_status(0, "committed 2 file(s), push skipped (--no-push)") == "published"
        assert rl.final_status(0, "no data changes — commit skipped") == "committed"
        assert rl.final_status(0, "commit skipped (flag)") == "committed"
        assert rl.final_status(0, "commit skipped: on branch 'x', not main") == "committed"

    def test_failure_summary_names_steps_and_checks_but_no_detail(self):
        results = [{"name": "s_core", "status": "failed", "detail": SENTINEL},
                   {"name": "s_two", "status": "skipped", "detail": SENTINEL},
                   {"name": "s_ok", "status": "ok", "detail": ""}]
        plan = {"failed": {"fantrax_core": ["step s_core failed", f"grain dim_a: {SENTINEL}"]}}
        text = rl.failure_summary(results, plan, f"ABORTED: push failed: {SENTINEL}")
        assert text == ("step s_core failed; step s_two skipped; Chain fantrax_core held; "
                        "grain dim_a; ABORTED: push failed")
        assert SENTINEL not in text

    def test_failure_summary_with_no_reason_still_says_something(self):
        assert rl.failure_summary([], None, "") == "run exited non-zero"

    def test_row_counts_marks_an_unreadable_table(self, monkeypatch):
        import etl_helpers as etl

        def read_table(name):
            if name == "gone":
                raise etl.TableNotFound(name)
            return [1, 2, 3]
        monkeypatch.setattr(etl, "read_table", read_table)
        assert rl.row_counts(["there", "gone"]) == {"there": 3, "gone": -1}


class TestNoRunLog:
    @pytest.fixture
    def connects(self, monkeypatch):
        calls = []
        monkeypatch.setattr(rl, "_connect", lambda: calls.append(1))
        return calls

    def test_no_url_writes_nothing_and_the_run_is_unchanged(self, pipe, connects, capsys):
        assert pipe.run() == 0
        assert connects == []
        assert pipe.committed
        assert not pipe.notified[0].startswith("⚠️")
        assert f"{rl.URL_ENV} not set - run log skipped" in capsys.readouterr().out

    def test_dry_run_writes_nothing(self, pipe, connects, monkeypatch):
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)
        assert pipe.run("--dry-run") == 0
        assert connects == []

    def test_check_only_writes_nothing(self, pipe, connects, monkeypatch):
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)
        monkeypatch.setattr(rp, "check_only", lambda accepted: 0)
        assert pipe.run("--check-only") == 0
        assert connects == []

    def test_a_trigger_outside_the_list_is_refused(self, pipe):
        with pytest.raises(SystemExit) as stopped:
            pipe.run("--trigger", "hourly")
        assert stopped.value.code == 2


class TestEnvFileFallback:
    def write_env(self, monkeypatch, tmp_path, text):
        path = tmp_path / "fallback.env"
        path.write_text(text, encoding="utf-8")
        monkeypatch.setattr(rl, "ENV_FILE", path)

    def test_pytest_cannot_find_the_live_url(self):
        assert rl.URL_ENV not in os.environ
        assert rl.ENV_FILE != REPO / ".env"
        assert not rl.ENV_FILE.exists()
        assert rl.database_url() is None
        assert not rl.enabled()

    def test_the_file_line_is_read_the_way_notify_reads_its_key(self, monkeypatch, tmp_path):
        self.write_env(monkeypatch, tmp_path,
                       f"# {rl.URL_ENV}=postgresql://commented.invalid/x\n"
                       "OTHER=1\n"
                       f"  {rl.URL_ENV}=\"postgresql://file.invalid/db\"  \n")
        assert rl.database_url() == "postgresql://file.invalid/db"

    def test_the_environment_wins_over_the_file(self, monkeypatch, tmp_path):
        self.write_env(monkeypatch, tmp_path, f"{rl.URL_ENV}=postgresql://file.invalid/db\n")
        monkeypatch.setenv(rl.URL_ENV, "postgresql://env.invalid/db")
        assert rl.database_url() == "postgresql://env.invalid/db"

    @pytest.mark.parametrize("text", ["", "OTHER=1\n", f"{rl.URL_ENV}=\n"])
    def test_a_file_without_the_key_is_not_a_url(self, monkeypatch, tmp_path, text):
        self.write_env(monkeypatch, tmp_path, text)
        assert rl.database_url() is None

    def test_a_run_uses_the_file_url_and_prints_nothing_of_it(self, pipe, monkeypatch, tmp_path, capsys):
        self.write_env(monkeypatch, tmp_path, f"{rl.URL_ENV}={UNREACHABLE}\n")
        seen = []

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                seen.append(sql.split()[0])
        monkeypatch.setattr(rl, "_connect", Conn)
        assert pipe.run() == 0
        assert seen == ["SET", "INSERT", "SET", "UPDATE"]
        shown = capsys.readouterr()
        assert "hunter2-pw" not in shown.out + shown.err + "".join(pipe.notified)

    def test_an_error_with_the_file_url_in_it_is_scrubbed(self, monkeypatch, tmp_path):
        self.write_env(monkeypatch, tmp_path, f"{rl.URL_ENV}={UNREACHABLE}\n")
        line = rl.first_line(RuntimeError(f"cannot use {UNREACHABLE}"))
        assert UNREACHABLE not in line and "hunter2-pw" not in line


class TestUnreachable:
    def test_the_run_goes_on_and_the_summary_leads_with_the_warning(self, pipe, monkeypatch, capsys):
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)
        assert pipe.run() == 0
        assert len(pipe.committed) == 1
        first = pipe.notified[0].splitlines()[0]
        assert first.startswith("⚠️ run log not written: ")
        assert first.endswith("The Supabase project may be paused; resume it from the dashboard.")
        assert pipe.summary_file.read_text(encoding="utf-8").splitlines()[0] == first
        shown = capsys.readouterr()
        assert "hunter2-pw" not in shown.out + shown.err + "".join(pipe.notified)

    def test_a_failed_run_keeps_its_exit_code(self, pipe, monkeypatch):
        import psycopg
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)

        def refused():
            raise psycopg.OperationalError("connection failed: Connection refused")
        monkeypatch.setattr(rl, "_connect", refused)
        pipe.results = [{"name": "s1", "status": "failed", "detail": "boom"}]
        assert pipe.run() == 1
        assert pipe.notified[0].startswith("⚠️ run log not written")

    def test_the_connection_gives_up_after_ten_seconds(self, monkeypatch):
        import psycopg
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)
        asked = {}

        def connect(url, **kwargs):
            asked.update(kwargs)
            raise psycopg.OperationalError("connection failed")
        monkeypatch.setattr(psycopg, "connect", connect)
        log = rl.RunLog("manual")
        log.start(HEAD)
        assert asked["connect_timeout"] == 10
        assert log.run_id is None and log.warning

    def test_a_missing_driver_is_a_warning_too(self, pipe, monkeypatch):
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)

        def no_driver():
            raise ImportError("No module named 'psycopg'")
        monkeypatch.setattr(rl, "_connect", no_driver)
        assert pipe.run() == 0
        assert "No module named 'psycopg'" in pipe.notified[0].splitlines()[0]

    def test_a_failed_update_warns_and_leaves_the_exit_code(self, pipe, monkeypatch):
        monkeypatch.setenv(rl.URL_ENV, UNREACHABLE)
        seen = []

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                seen.append(sql)
                if sql.startswith("UPDATE"):
                    raise OSError("server closed the connection")
        monkeypatch.setattr(rl, "_connect", Conn)
        assert pipe.run() == 0
        assert [s.split()[0] for s in seen] == ["SET", "INSERT", "SET", "UPDATE"]
        assert seen[0] == f"SET LOCAL statement_timeout = {rl.STATEMENT_TIMEOUT_MS}"
        assert rl.STATEMENT_TIMEOUT_MS == 10000
        assert pipe.notified[0].startswith("⚠️ run log not written: server closed the connection")


class TestDotenvGuard:
    def test_load_dotenv_cannot_set_the_database_url(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(f"{rl.URL_ENV}=postgresql://live.invalid/none\n", encoding="utf-8")
        from dotenv import load_dotenv
        import dotenv.main
        load_dotenv(env_file, override=True)
        dotenv.main.load_dotenv(env_file, override=True)
        assert rl.URL_ENV not in os.environ


@pytest.fixture
def pg(monkeypatch):
    """The test database as the SUPABASE_DB_URL of the run, and its rows."""
    import psycopg
    url = database_url()
    monkeypatch.setenv(rl.URL_ENV, url)

    def rows():
        with psycopg.connect(url) as conn:
            return conn.execute(
                "SELECT run_id::text, trigger, status, git_sha, snapshot_commit_sha, "
                "rows_written, error, started_at, finished_at FROM ops.etl_run_log").fetchall()
    before = {r[0] for r in rows()}

    def mine():
        return [r for r in rows() if r[0] not in before]
    yield SimpleNamespace(url=url, mine=mine)
    with psycopg.connect(url) as conn:
        for row in mine():
            conn.execute("DELETE FROM ops.etl_run_log WHERE run_id = %s::uuid", (row[0],))


class TestPostgres:
    def test_a_published_run_inserts_running_and_finishes_published(self, pipe, pg, capsys):
        seen = []
        pipe.mid_run = lambda: seen.extend(pg.mine())
        assert pipe.run("--trigger", "weekly") == 0
        assert [r[2] for r in seen] == ["running"]
        assert seen[0][1] == "weekly" and seen[0][3] == HEAD and seen[0][8] is None
        (row,) = pg.mine()
        run_id, trigger, status, git_sha, snapshot, rows_written, error, started, finished = row
        assert (trigger, status, git_sha, snapshot) == ("weekly", "published", HEAD, HEAD)
        assert rows_written == {"dim_a": 3}
        assert error is None
        assert started.tzinfo is not None and started <= finished
        assert not pipe.notified[0].startswith("⚠️")
        assert run_id in capsys.readouterr().out

    def test_the_trigger_defaults_to_manual(self, pipe, pg):
        pipe.run()
        assert [r[1] for r in pg.mine()] == ["manual"]

    def test_a_run_with_no_data_commit_finishes_committed(self, pipe, pg):
        pipe.commit_line = "no data changes — commit skipped"
        assert pipe.run("--trigger", "daily") == 0
        (row,) = pg.mine()
        assert (row[2], row[4], row[5], row[6]) == ("committed", None, {"dim_a": 3}, None)

    def test_a_no_commit_run_finishes_committed(self, pipe, pg):
        assert pipe.run("--no-commit") == 0
        assert pipe.committed == []
        assert [r[2] for r in pg.mine()] == ["committed"]

    def test_a_failed_run_finishes_failed_with_names_only(self, pipe, pg, capsys):
        pipe.results = [{"name": "s1", "status": "failed", "detail": SENTINEL}]
        pipe.commit_line = "no data changes — commit skipped"
        assert pipe.run() == 1
        (row,) = pg.mine()
        assert row[2] == "failed"
        assert row[6] == "step s1 failed; Chain c1 held"
        shown = capsys.readouterr()
        assert SENTINEL not in row[6]
        assert SENTINEL not in "".join(l for l in (shown.out + shown.err).splitlines()
                                       if "run log" in l)

    def test_a_crash_finishes_the_row_failed_and_raises(self, pipe, pg):
        pipe.results = RuntimeError(SENTINEL)
        with pytest.raises(RuntimeError):
            pipe.run()
        (row,) = pg.mine()
        assert row[2] == "failed"
        assert row[6] == "RuntimeError raised before the run finished"
        assert row[8] is not None

    def test_a_stalled_statement_is_a_write_error(self, pipe, pg, monkeypatch):
        import psycopg
        monkeypatch.setattr(rl, "STATEMENT_TIMEOUT_MS", 500)
        holder = psycopg.connect(pg.url)

        def lock_the_row():
            (row,) = pg.mine()
            holder.execute("SELECT 1 FROM ops.etl_run_log WHERE run_id = %s::uuid FOR UPDATE", (row[0],))
        pipe.mid_run = lock_the_row
        try:
            assert pipe.run() == 0
        finally:
            holder.close()
        assert len(pipe.committed) == 1
        first = pipe.notified[0].splitlines()[0]
        assert first.startswith("⚠️ run log not written: ")
        assert "statement timeout" in first
        assert [r[2] for r in pg.mine()] == ["running"]

    def test_a_database_error_prints_no_row_values(self, pg, capsys):
        log = rl.RunLog(f"bogus-{SENTINEL}")
        log.start(HEAD)
        shown = capsys.readouterr()
        assert log.run_id is None
        assert log.warning.startswith("⚠️ run log not written: ")
        assert "violates check constraint" in log.warning
        assert SENTINEL not in log.warning + shown.out + shown.err
        assert "\n" not in log.warning
        assert pg.mine() == []

