"""The owner's --publish-manual command (#616, ADR-0008 decision 3).

The allowlist is pure and is tested on a fake registry and on the real one.
The publish runs against a real throwaway git repo with a bare `origin`;
the store (etl_storage_pg), the Gate suite, the run log and `gh` are fakes.
Nothing here reaches GitHub, a database or Discord.
"""
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_run_log as rl  # noqa: E402
import run_pipeline as rp  # noqa: E402
from conftest import git  # noqa: E402
from test_data_pr import ALL_PASS, TESTS_FAIL, FakeGh  # noqa: E402

TODAY = date.today().isoformat()
RUN_ID = "11111111-2222-3333-4444-555555555555"
REGISTRY = {
    "man_a": {"grain": "a"},
    "man_b": {"grain": "a"},
    "fresh": {"grain": "a"},
    "chained": {"grain": "a", "chain": "fantrax_core"},
    "secret": {"grain": "a", "schema": "ops"},
}


def _write(repo, table, n):
    pd.DataFrame({"a": range(n)}).to_parquet(repo / "data" / f"{table}.parquet")


def _rows(repo, table):
    return len(pd.read_parquet(repo / "data" / f"{table}.parquet"))


class TestAllowlist:
    def test_a_chain_table_is_refused(self):
        out = rp.manual_refusals(["chained"], REGISTRY, {"data/chained.parquet"})
        assert out == ["chained: in Chain fantrax_core, which publishes it"]

    def test_an_undeclared_table_is_refused(self):
        out = rp.manual_refusals(["nope"], REGISTRY, {"data/nope.parquet"})
        assert out == ["nope: not declared in docs/data_model.yml"]

    def test_a_private_table_is_refused(self):
        out = rp.manual_refusals(["secret"], REGISTRY, {"data/secret.parquet"})
        assert out == ["secret: private, never published"]

    def test_a_table_with_no_snapshot_at_head_is_refused(self):
        out = rp.manual_refusals(["fresh"], REGISTRY, set())
        assert out == ["fresh: no snapshot tracked at HEAD (a new table goes by its own PR)"]

    def test_a_tracked_manual_only_table_passes(self):
        assert rp.manual_refusals(["man_a", "man_b"], REGISTRY,
                                  {"data/man_a.parquet", "data/man_b.parquet"}) == []

    def test_the_real_registry(self):
        names = ["fact_salary_price_list", "dim_pick_value_curve", "fact_team_cap",
                 "dim_fantasy_teams", "not_a_table", "etl_run_log"]
        out = rp.manual_refusals(names, rp.etl_checks.load_registry(), rp.tracked_at_head(names))
        refused = sorted(line.split(":")[0] for line in out)
        assert refused == ["dim_fantasy_teams", "etl_run_log", "fact_team_cap", "not_a_table"]


class FakeRunLog:
    instances = []

    def __init__(self, trigger):
        self.trigger, self.run_id, self.warning = trigger, RUN_ID, None
        self.started, self.finished = False, None
        FakeRunLog.instances.append(self)

    def start(self, git_sha):
        self.started = True

    def finish(self, status, snapshot_commit_sha=None, rows_written=None, error=None,
               cadence=None, column_changes=None, fantrax_logins=None):
        self.finished = dict(status=status, snapshot_commit_sha=snapshot_commit_sha,
                             rows_written=rows_written, error=error)


def _gate(table, ok=True, tier="gate", check="grain"):
    return SimpleNamespace(table=table, ok=ok, tier=tier, check=check, detail="" if ok else "2 dupes")


@pytest.fixture
def world(git_repo, tmp_path, monkeypatch):
    """A work repo on main holding man_a, man_b and chained at HEAD, pushed to
    a bare origin; a fake store whose export writes `store_rows` rows."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    for t in ("man_a", "man_b", "chained"):
        _write(git_repo, t, 5)
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "-q", "-m", "seed")
    git(git_repo, "remote", "add", "origin", str(origin))
    git(git_repo, "push", "-q", "origin", "main")

    w = SimpleNamespace(repo=git_repo, origin=origin, store_rows={"man_a": 9, "man_b": 9},
                        suite=[], exported=[], suite_calls=[], read_only=[], fail_export=False)

    @contextmanager
    def session_read_only():
        w.read_only.append(True)
        try:
            yield
        finally:
            w.read_only.pop()

    def export_published(names, data_dir, changes=None):
        assert w.read_only, "export outside a read-only session"
        w.exported.append(list(names))
        if w.fail_export:
            _write(w.repo, names[0], 1)
            raise RuntimeError("boom")
        for n in names:
            if w.store_rows.get(n) is None:
                path = Path(data_dir) / f"{n}.parquet"
                path.write_bytes(path.read_bytes())
            else:
                _write(w.repo, n, w.store_rows[n])
        return {n: w.store_rows.get(n) or 5 for n in names}

    def run_suite(tables=None, accepted_shrink=(), data_dir="unset", **kw):
        assert w.read_only, "Gate checks outside a read-only session"
        assert data_dir is None, "Gate checks must read the store"
        w.suite_calls.append(list(tables))
        return w.suite or [_gate(t) for t in tables]

    fake_pg = SimpleNamespace(URL_ENV="SUPABASE_DB_URL", session_read_only=session_read_only,
                              export_published=export_published,
                              describe=lambda exc: f"{type(exc).__name__}: {exc}")
    monkeypatch.setitem(sys.modules, "etl_storage_pg", fake_pg)
    monkeypatch.setattr(rp.etl_checks, "load_registry", lambda: REGISTRY)
    monkeypatch.setattr(rp.etl_checks, "run_suite", run_suite)
    monkeypatch.setenv("ETL_STORAGE", "postgres")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake")
    FakeRunLog.instances = []
    monkeypatch.setattr(rl, "RunLog", FakeRunLog)
    monkeypatch.setattr(rl, "head_sha", lambda repo: "a" * 40)

    def gh(checks=(ALL_PASS,), **kw):
        fake = FakeGh(origin, checks, **kw)
        monkeypatch.setattr(rp, "_gh", fake)
        return fake
    w.gh = gh
    return w


def publish(world, *names, dry_run=False, push=True):
    return rp.publish_manual(list(names), [], push=push, dry_run=dry_run, cwd=world.repo)


def data_is_clean(repo):
    return git(repo, "status", "--porcelain", "--", "data").stdout == ""


class TestRefusedBeforeAnyRead:
    @pytest.mark.parametrize("name", ["chained", "nope", "secret", "fresh"])
    def test_refusal_reads_nothing_and_lands_nothing(self, world, name, capsys):
        gh = world.gh()
        assert publish(world, "man_a", name) == 2
        assert world.suite_calls == [] and world.exported == []
        assert gh.calls == [] and FakeRunLog.instances == []
        assert capsys.readouterr().out.startswith(f"refused: {name}: ")

    def test_a_store_that_is_not_postgres_is_refused(self, world, monkeypatch):
        gh = world.gh()
        monkeypatch.setenv("ETL_STORAGE", "parquet")
        assert publish(world, "man_a") == 2
        assert world.suite_calls == [] and world.exported == [] and gh.calls == []

    def test_no_database_url_is_refused(self, world, monkeypatch):
        world.gh()
        monkeypatch.delenv("SUPABASE_DB_URL")
        assert publish(world, "man_a") == 2
        assert world.suite_calls == [] and FakeRunLog.instances == []

    def test_dry_run_reads_nothing(self, world, capsys):
        gh = world.gh()
        assert publish(world, "man_a", "man_b", dry_run=True) == 0
        assert world.suite_calls == [] and world.exported == [] and gh.calls == []
        assert FakeRunLog.instances == []
        assert "would publish 2 manual-only table(s): man_a, man_b" in capsys.readouterr().out


class TestPublish:
    def test_it_lands_by_the_data_pr_and_logs_published(self, world):
        gh = world.gh()
        assert publish(world, "man_a") == 0
        assert world.suite_calls == [["man_a"]] and world.exported == [["man_a"]]
        assert gh.verbs() == ["pr create", "pr checks", "pr merge", "pr view"]
        create = gh.calls[0]
        assert create[create.index("--head") + 1] == f"data/{TODAY}-manual"
        assert create[create.index("--title") + 1] == f"data: manual publish {TODAY} (man_a)"
        body = create[create.index("--body") + 1]
        assert body.startswith(rp.MANUAL_INTRO) and RUN_ID in body and "- man_a: 9" in body
        assert git(world.origin, "log", "-1", "--format=%s", "main").stdout.strip() == (
            f"data: manual publish {TODAY} (man_a)")
        changed = git(world.origin, "show", "--name-only", "--format=", "main").stdout.split()
        assert changed == ["data/man_a.parquet"]
        log = FakeRunLog.instances[-1]
        assert log.trigger == "manual"
        assert log.finished == dict(status="published",
                                    snapshot_commit_sha=git(world.origin, "rev-parse", "main").stdout.strip(),
                                    rows_written={"man_a": 9}, error=None)
        assert _rows(world.repo, "man_a") == 9 and data_is_clean(world.repo)

    def test_a_failed_check_leaves_the_pr_open_and_logs_failed(self, world):
        gh = world.gh(checks=[TESTS_FAIL])
        assert publish(world, "man_a") == 1
        assert "pr merge" not in gh.verbs()
        assert FakeRunLog.instances[-1].finished["status"] == "failed"
        assert git(world.origin, "log", "-1", "--format=%s", "main").stdout.strip() == "seed"

    def test_a_gate_failure_exports_nothing(self, world):
        gh = world.gh()
        world.suite = [_gate("man_a", ok=False)]
        assert publish(world, "man_a") == 1
        assert world.exported == [] and gh.calls == []
        done = FakeRunLog.instances[-1].finished
        assert done["status"] == "failed"
        assert done["error"] == "ABORTED: Gate failed, nothing exported: grain man_a"
        assert data_is_clean(world.repo)

    def test_a_review_finding_does_not_block(self, world):
        world.gh()
        world.suite = [_gate("man_a", ok=False, tier="review", check="grain_null_key")]
        assert publish(world, "man_a") == 0
        assert world.exported == [["man_a"]]

    def test_a_failed_export_puts_data_back_to_head(self, world):
        gh = world.gh()
        world.fail_export = True
        assert publish(world, "man_a") == 1
        assert gh.calls == []
        assert data_is_clean(world.repo) and _rows(world.repo, "man_a") == 5
        assert FakeRunLog.instances[-1].finished["error"] == "ABORTED: export failed: RuntimeError: boom"


class TestChangeDetection:
    def test_an_export_equal_to_head_opens_nothing(self, world):
        gh = world.gh()
        world.store_rows = {}
        assert publish(world, "man_a", "man_b") == 0
        assert world.exported == [["man_a", "man_b"]]
        assert gh.calls == []
        assert git(world.repo, "log", "-1", "--format=%s").stdout.strip() == "seed"
        done = FakeRunLog.instances[-1].finished
        assert (done["status"], done["snapshot_commit_sha"]) == ("committed", None)

    def test_only_the_changed_table_is_committed(self, world):
        gh = world.gh()
        world.store_rows = {"man_a": 9}
        assert publish(world, "man_a", "man_b") == 0
        assert "pr create" in gh.verbs()
        changed = git(world.origin, "show", "--name-only", "--format=", "main").stdout.split()
        assert changed == ["data/man_a.parquet"]

    def test_a_staged_file_off_the_allowlist_is_refused_before_any_read(self, world):
        gh = world.gh()
        (world.repo / "notes.txt").write_text("x")
        git(world.repo, "add", "notes.txt")
        assert publish(world, "man_a") == 2
        assert world.suite_calls == [] and world.exported == []
        assert gh.calls == [] and FakeRunLog.instances == []

    def test_a_staged_chain_parquet_is_refused_before_any_read(self, world, capsys):
        gh = world.gh()
        _write(world.repo, "chained", 7)
        git(world.repo, "add", "data/chained.parquet")
        assert publish(world, "man_a") == 2
        assert world.suite_calls == [] and world.exported == []
        assert gh.calls == [] and FakeRunLog.instances == []
        assert "staged path(s) that are not named tables: data/chained.parquet" in capsys.readouterr().out
        assert git(world.origin, "log", "-1", "--format=%s", "main").stdout.strip() == "seed"

    def test_a_staged_named_table_is_not_refused(self, world):
        world.gh()
        _write(world.repo, "man_a", 7)
        git(world.repo, "add", "data/man_a.parquet")
        assert publish(world, "man_a") == 0
        changed = git(world.origin, "show", "--name-only", "--format=", "main").stdout.split()
        assert changed == ["data/man_a.parquet"]

    def test_a_checkout_off_main_is_refused_before_any_read(self, world, capsys):
        gh = world.gh()
        git(world.repo, "switch", "-q", "-c", "side")
        assert publish(world, "man_a") == 2
        assert world.suite_calls == [] and world.exported == []
        assert gh.calls == [] and FakeRunLog.instances == []
        assert "on branch 'side', not main" in capsys.readouterr().out
        assert data_is_clean(world.repo)

    def test_no_push_commits_locally_and_opens_no_pr(self, world):
        gh = world.gh()
        assert publish(world, "man_a", push=False) == 0
        assert gh.calls == []
        assert git(world.repo, "log", "-1", "--format=%s").stdout.strip() == (
            f"data: manual publish {TODAY} (man_a)")
        assert git(world.origin, "log", "-1", "--format=%s", "main").stdout.strip() == "seed"


class TestMain:
    @pytest.fixture
    def run(self, monkeypatch):
        seen = []
        monkeypatch.setattr(rp, "resolve_storage_env", lambda *a, **k: "postgres")
        monkeypatch.setattr(rp, "publish_manual", lambda *a, **k: seen.append((a, k)) or 0)

        def go(*argv):
            monkeypatch.setattr(sys, "argv", ["run_pipeline.py", *argv])
            return rp.main()
        go.seen = seen
        return go

    def test_it_dispatches_and_runs_no_step(self, run, monkeypatch):
        monkeypatch.setattr(rp, "run_steps", lambda *a, **k: pytest.fail("a step ran"))
        monkeypatch.setattr(rp, "open_fantrax_session", lambda: pytest.fail("a Fantrax session opened"))
        assert run("--publish-manual", "man_a", "man_b", "--dry-run") == 0
        (args, kwargs), = run.seen
        assert args == (["man_a", "man_b"], []) and kwargs == {"push": True, "dry_run": True}

    @pytest.mark.parametrize("flag", [["--steps", "01a"], ["--group", "rookie"],
                                      ["--profile", "dynasty"], ["--check-only"], ["--no-commit"]])
    def test_run_flags_are_refused(self, run, flag):
        assert run("--publish-manual", "man_a", *flag) == 2
        assert run.seen == []
