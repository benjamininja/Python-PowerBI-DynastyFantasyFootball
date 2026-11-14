"""The pipeline lands its data by its own data PR (#361, #336 final task 1).

commit_data runs against a real throwaway git repo with a bare repo as
`origin`; only `gh` is faked (FakeGh), and its `pr merge` fast-forwards the
bare repo's main the way a rebase-merge of a one-commit PR does. Nothing here
reaches GitHub, a database or Discord. The main() cases stub the steps, the
checks, the run log and commit_data, to pin how the outcome line becomes the
run-log status, the exit code and the notice.
"""
import json
import subprocess
import sys
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

TODAY = date.today().isoformat()
BRANCH = f"data/{TODAY}-offseason-wk03"
TITLE = f"data: pipeline refresh {TODAY} (offseason, wk 03)"
RUN_ID = "11111111-2222-3333-4444-555555555555"


def _write(repo, table, n):
    pd.DataFrame({"a": range(n)}).to_parquet(repo / "data" / f"{table}.parquet")


def _rows(**buckets):
    return [{"name": name, "bucket": bucket} for name, bucket in buckets.items()]


ALL_PASS = _rows(**{"pii-scan": "pass", "tests": "pass", "bot-tests": "pass"})
TESTS_FAIL = _rows(**{"pii-scan": "pass", "tests": "fail", "bot-tests": "pass"})
NOT_YET = _rows(**{"pii-scan": "pass", "tests": "pending"})


class FakeGh:
    """gh as the pipeline calls it. `checks` is the list of check reads to
    return in order (the last one repeats). `pr merge` lands the pushed
    branch on the bare origin's main, as a rebase-merge of one commit does."""

    def __init__(self, origin, checks, create_ok=True, merge_ok=True, pr=42, missing_reads=0):
        self.origin, self.checks, self.create_ok = origin, list(checks), create_ok
        self.merge_ok, self.pr, self.missing_reads = merge_ok, pr, missing_reads
        self.calls, self.merged_sha, self.head = [], None, None

    def __call__(self, *args, cwd=None):
        self.calls.append(args)
        if args[:2] == ("pr", "create"):
            self.head = args[args.index("--head") + 1]
            if not self.create_ok:
                return subprocess.CompletedProcess(args, 1, "", "GraphQL: not allowed")
            return subprocess.CompletedProcess(args, 0, f"https://github.com/o/r/pull/{self.pr}\n", "")
        if args[:2] == ("pr", "checks"):
            read = self.checks.pop(0) if len(self.checks) > 1 else self.checks[0]
            return subprocess.CompletedProcess(args, 0, json.dumps(read), "")
        if args[:2] == ("pr", "merge"):
            if not self.merge_ok:
                return subprocess.CompletedProcess(args, 1, "", "the base branch policy prohibits the merge")
            self.merged_sha = git(self.origin, "rev-parse", self.head).stdout.strip()
            git(self.origin, "update-ref", "refs/heads/main", self.merged_sha)
            git(self.origin, "update-ref", "-d", f"refs/heads/{self.head}")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ("pr", "view"):
            oid = self.merged_sha
            if self.missing_reads > 0:
                self.missing_reads -= 1
                oid = None
            body = ({"state": "MERGED", "mergeCommit": {"oid": oid} if oid else None} if self.merged_sha
                    else {"state": "OPEN", "mergeCommit": None})
            return subprocess.CompletedProcess(args, 0, json.dumps(body), "")
        raise AssertionError(f"unexpected gh call: {args}")

    def verbs(self):
        return [" ".join(c[:2]) for c in self.calls]


@pytest.fixture
def world(git_repo, tmp_path, monkeypatch):
    """A work repo on main with seeded tables, pushed to a bare origin."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    for t in ("fa", "ra"):
        _write(git_repo, t, 5)
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "-q", "-m", "seed")
    git(git_repo, "remote", "add", "origin", str(origin))
    git(git_repo, "push", "-q", "origin", "main")
    for t in ("fa", "ra"):
        _write(git_repo, t, 9)

    def make(checks=(ALL_PASS,), **kw):
        gh = FakeGh(origin, checks, **kw)
        monkeypatch.setattr(rp, "_gh", gh)
        return gh
    return SimpleNamespace(repo=git_repo, origin=origin, gh=make)


def land(world, **kw):
    kw.setdefault("poll_s", 0)
    return rp.commit_data("OFFSEASON", "03", push=True, publish=["ra", "fa"], restore=[],
                          cwd=world.repo, run_id=RUN_ID, rows={"ra": 9, "fa": 9}, **kw)


def branch_now(repo):
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def origin_main_subject(origin):
    return git(origin, "log", "-1", "--format=%s", "main").stdout.strip()


class TestHappyPath:
    def test_branch_pr_checks_merge_and_the_landed_sha(self, world):
        gh = world.gh(checks=[NOT_YET, ALL_PASS])
        landed = {}
        line = land(world, landed=landed)
        assert line == "committed + merged 2 parquet file(s) via data PR #42"
        assert gh.verbs() == ["pr create", "pr checks", "pr checks", "pr merge", "pr view"]
        create = gh.calls[0]
        assert create[create.index("--base") + 1] == "main"
        assert create[create.index("--head") + 1] == BRANCH
        assert create[create.index("--title") + 1] == TITLE
        body = create[create.index("--body") + 1]
        assert RUN_ID in body and "- ra: 9" in body and "- fa: 9" in body
        assert gh.calls[3] == ("pr", "merge", "42", "--rebase", "--delete-branch")
        flat = " ".join(" ".join(c) for c in gh.calls)
        assert "--auto" not in flat and "--admin" not in flat
        assert origin_main_subject(world.origin) == TITLE
        landed_sha = git(world.origin, "rev-parse", "main").stdout.strip()
        assert landed == {"pr": 42, "sha": landed_sha}

    def test_the_commit_sits_on_the_data_branch_off_an_up_to_date_main(self, world):
        gh = world.gh()
        line = land(world)
        assert line.startswith("committed + merged")
        assert git(world.origin, "rev-parse", "main").stdout == git(world.repo, "rev-parse", "HEAD").stdout
        parents = git(world.origin, "log", "--format=%s", "main").stdout.split("\n")
        assert parents[:2] == [TITLE, "seed"]
        assert ("pr", "merge") == gh.calls[-2][:2]

    def test_local_main_is_back_and_holds_the_landed_data(self, world):
        world.gh()
        land(world)
        assert branch_now(world.repo) == "main"
        assert len(pd.read_parquet(world.repo / "data" / "ra.parquet")) == 9
        assert git(world.repo, "status", "--porcelain", "--", "data").stdout == ""

    def test_it_rebases_on_a_main_that_moved(self, world):
        world.gh()
        other = world.repo.parent / "other"
        git(world.repo.parent, "clone", "-q", str(world.origin), str(other))
        git(other, "config", "user.name", "t")
        git(other, "config", "user.email", "t@example.com")
        (other / "README.txt").write_text("x")
        git(other, "add", "README.txt")
        git(other, "commit", "-q", "-m", "someone else")
        git(other, "push", "-q", "origin", "main")
        line = land(world)
        assert line.startswith("committed + merged")
        assert git(world.origin, "log", "--format=%s", "main").stdout.split("\n")[:3] == [
            TITLE, "someone else", "seed"]


class TestChecksFail:
    def test_a_failed_check_leaves_the_pr_open(self, world):
        gh = world.gh(checks=[TESTS_FAIL])
        landed = {}
        line = land(world, landed=landed)
        assert line == "ABORTED: data PR #42 left open, required check failed (tests)"
        assert "pr merge" not in gh.verbs()
        assert landed == {}
        assert origin_main_subject(world.origin) == "seed"
        assert git(world.origin, "rev-parse", "--verify", f"refs/heads/{BRANCH}").returncode == 0

    def test_main_is_left_at_its_own_data(self, world):
        world.gh(checks=[TESTS_FAIL])
        land(world)
        assert branch_now(world.repo) == "main"
        assert len(pd.read_parquet(world.repo / "data" / "ra.parquet")) == 5
        assert git(world.repo, "status", "--porcelain", "--", "data").stdout == ""

    def test_a_cancelled_check_is_a_failure_too(self, world):
        world.gh(checks=[_rows(**{"pii-scan": "cancel", "tests": "pass", "bot-tests": "pass"})])
        assert land(world) == "ABORTED: data PR #42 left open, required check failed (pii-scan)"


def local_branches(repo):
    return git(repo, "branch", "--format=%(refname:short)").stdout.split()


def data_is_clean(repo):
    return git(repo, "status", "--porcelain", "--", "data").stdout == ""


class TestRerun:
    def test_every_stop_after_the_branch_leaves_no_local_data_branch(self, world, monkeypatch):
        world.gh(checks=[TESTS_FAIL])
        land(world)
        assert local_branches(world.repo) == ["main"]
        world.gh(checks=[NOT_YET])
        _write(world.repo, "ra", 9)
        _write(world.repo, "fa", 9)
        land(world, checks_timeout_s=0)
        assert local_branches(world.repo) == ["main"]
        world.gh(merge_ok=False)
        _write(world.repo, "ra", 9)
        _write(world.repo, "fa", 9)
        assert "merge refused" in land(world)
        assert local_branches(world.repo) == ["main"]
        world.gh(create_ok=False)
        _write(world.repo, "ra", 9)
        _write(world.repo, "fa", 9)
        assert "no data PR was opened" in land(world)
        assert local_branches(world.repo) == ["main"]
        assert data_is_clean(world.repo)

    def test_a_rerun_after_a_failed_run_takes_a_suffixed_branch(self, world):
        world.gh(checks=[TESTS_FAIL])
        assert land(world).startswith("ABORTED: data PR #42 left open")
        assert git(world.origin, "rev-parse", "--verify", f"refs/heads/{BRANCH}").returncode == 0
        assert data_is_clean(world.repo)
        _write(world.repo, "ra", 9)
        _write(world.repo, "fa", 9)
        gh = world.gh()
        landed = {}
        line = land(world, landed=landed)
        assert line == "committed + merged 2 parquet file(s) via data PR #42"
        create = gh.calls[0]
        assert create[create.index("--head") + 1] == f"{BRANCH}-2"
        assert origin_main_subject(world.origin) == TITLE
        assert local_branches(world.repo) == ["main"]
        assert data_is_clean(world.repo)
        assert len(pd.read_parquet(world.repo / "data" / "ra.parquet")) == 9

    def test_a_stale_local_branch_is_not_reused_or_touched(self, world):
        git(world.repo, "branch", BRANCH)
        gh = world.gh()
        assert land(world).startswith("committed + merged")
        assert gh.head == f"{BRANCH}-2"
        assert BRANCH in local_branches(world.repo)
        assert data_is_clean(world.repo)

    def test_the_suffix_keeps_counting_while_names_are_taken(self, world):
        git(world.repo, "branch", BRANCH)
        git(world.repo, "branch", f"{BRANCH}-2")
        git(world.repo, "push", "-q", "origin", f"main:refs/heads/{BRANCH}-3")
        gh = world.gh()
        land(world)
        assert gh.head == f"{BRANCH}-4"

    def test_a_branch_that_cannot_be_made_puts_data_back_to_head(self, world, monkeypatch):
        gh = world.gh()
        monkeypatch.setattr(rp, "_free_branch", lambda stem, cwd: "main")
        line = land(world)
        assert line.startswith("ABORTED: could not create branch main")
        assert gh.calls == []
        assert data_is_clean(world.repo)
        assert len(pd.read_parquet(world.repo / "data" / "ra.parquet")) == 5
        assert git(world.repo, "diff", "--cached", "--name-only").stdout == ""
        assert branch_now(world.repo) == "main"


class TestLandedSha:
    def test_a_missing_merge_commit_is_read_again_once(self, world):
        gh = world.gh(missing_reads=1)
        landed = {}
        line = land(world, landed=landed)
        assert line == "committed + merged 2 parquet file(s) via data PR #42"
        assert gh.verbs().count("pr view") == 2
        assert landed["sha"] == git(world.origin, "rev-parse", "main").stdout.strip()

    def test_still_missing_takes_origin_main_and_says_so(self, world):
        gh = world.gh(missing_reads=2)
        landed = {}
        line = land(world, landed=landed)
        assert line == ("committed + merged 2 parquet file(s) via data PR #42; "
                        "landed sha taken from origin/main")
        assert gh.verbs().count("pr view") == 2
        assert landed["sha"] == git(world.origin, "rev-parse", "main").stdout.strip()
        assert rl.final_status(0, line) == "published"


class TestFastForward:
    def test_a_failed_local_pull_is_in_the_line_and_the_run_stays_published(self, world, monkeypatch):
        world.gh()
        real = rp._git

        def flaky(*args, **kwargs):
            if "--ff-only" in args:
                return subprocess.CompletedProcess(args, 1, "", "fatal: Not possible to fast-forward")
            return real(*args, **kwargs)
        monkeypatch.setattr(rp, "_git", flaky)
        landed = {}
        line = land(world, landed=landed)
        assert line == ("committed + merged 2 parquet file(s) via data PR #42; "
                        "local main not fast-forwarded, run git pull")
        assert rl.final_status(0, line) == "published"
        assert landed["sha"] == git(world.origin, "rev-parse", "main").stdout.strip()


class TestTimeout:
    def test_checks_still_pending_at_the_deadline_leave_the_pr_open(self, world):
        gh = world.gh(checks=[NOT_YET])
        line = land(world, checks_timeout_s=0)
        assert line == ("ABORTED: data PR #42 left open, checks not done after 0 min "
                        "(waiting on tests, bot-tests)")
        assert "pr merge" not in gh.verbs()
        assert origin_main_subject(world.origin) == "seed"
        assert branch_now(world.repo) == "main"

    def test_it_polls_until_the_deadline_not_forever(self, world, monkeypatch):
        gh = world.gh(checks=[NOT_YET])
        clock = iter(range(0, 1000, 10))
        slept = []
        monkeypatch.setattr(rp, "time", SimpleNamespace(monotonic=lambda: next(clock), sleep=slept.append))
        line = land(world, checks_timeout_s=35, poll_s=7)
        assert "checks not done" in line
        assert slept == [7, 7, 7]
        assert gh.verbs().count("pr checks") == 4


class TestNoPush:
    def test_no_push_commits_locally_and_opens_no_pr(self, world):
        gh = world.gh()
        line = rp.commit_data("OFFSEASON", "03", push=False, publish=["ra", "fa"], restore=[],
                              cwd=world.repo)
        assert line == "committed 2 file(s), push skipped (--no-push)"
        assert gh.calls == []
        assert branch_now(world.repo) == "main"
        assert git(world.repo, "log", "-1", "--format=%s").stdout.strip() == TITLE
        assert origin_main_subject(world.origin) == "seed"
        assert git(world.origin, "branch", "--format=%(refname:short)").stdout.split() == ["main"]
        assert git(world.repo, "branch", "--format=%(refname:short)").stdout.split() == ["main"]


class TestOtherStops:
    def test_a_refused_merge_leaves_the_pr_open(self, world):
        gh = world.gh(merge_ok=False)
        landed = {}
        line = land(world, landed=landed)
        assert line == ("ABORTED: data PR #42 left open, merge refused "
                        "(the base branch policy prohibits the merge)")
        assert gh.verbs()[-2:] == ["pr merge", "pr view"]
        assert landed == {}
        assert branch_now(world.repo) == "main"

    def test_a_pr_that_will_not_open_leaves_the_pushed_branch(self, world):
        world.gh(create_ok=False)
        line = land(world)
        assert line.startswith(f"ABORTED: {BRANCH} pushed but no data PR was opened")
        assert branch_now(world.repo) == "main"
        assert git(world.origin, "rev-parse", "--verify", f"refs/heads/{BRANCH}").returncode == 0

    def test_no_data_changes_opens_nothing(self, world):
        gh = world.gh()
        git(world.repo, "checkout", "--", "data")
        assert land(world) == "no data changes — commit skipped"
        assert gh.calls == []

    def test_a_missing_gh_is_a_failed_call_not_a_crash(self, monkeypatch):
        def no_gh(*a, **k):
            raise FileNotFoundError("gh")
        monkeypatch.setattr(rp.subprocess, "run", no_gh)
        done = rp._gh("pr", "view", "1")
        assert done.returncode == 1 and "FileNotFoundError" in done.stderr


class TestChecksState:
    def read(self, monkeypatch, rows):
        monkeypatch.setattr(rp, "_gh", lambda *a, **k: subprocess.CompletedProcess(
            a, 0, json.dumps(rows), ""))
        return rp._checks_state(1, REPO)

    def test_all_three_pass(self, monkeypatch):
        assert self.read(monkeypatch, ALL_PASS) == ("passed", [])

    def test_a_check_gh_does_not_list_yet_is_pending(self, monkeypatch):
        assert self.read(monkeypatch, _rows(**{"pii-scan": "pass"})) == ("pending", ["tests", "bot-tests"])

    def test_nothing_listed_is_pending(self, monkeypatch):
        monkeypatch.setattr(rp, "_gh", lambda *a, **k: subprocess.CompletedProcess(
            a, 1, "", "no checks reported on the branch"))
        assert rp._checks_state(1, REPO) == ("pending", list(rp.REQUIRED_CHECKS))

    def test_a_check_that_is_not_required_is_ignored(self, monkeypatch):
        rows = ALL_PASS + _rows(**{"storage-pg": "fail"})
        assert self.read(monkeypatch, rows) == ("passed", [])

    def test_a_push_run_and_a_pull_request_run_of_one_check_both_count(self, monkeypatch):
        rows = ALL_PASS + [{"name": "tests", "bucket": "fail"}]
        assert self.read(monkeypatch, rows) == ("failed", ["tests"])
        rows = ALL_PASS + [{"name": "tests", "bucket": "pending"}]
        assert self.read(monkeypatch, rows) == ("pending", ["tests"])

    def test_the_required_names_are_the_rulesets(self):
        assert rp.REQUIRED_CHECKS == ("pii-scan", "tests", "bot-tests")


class FakeRunLog:
    instances = []

    def __init__(self, trigger):
        self.trigger, self.run_id, self.warning = trigger, RUN_ID, None
        self.finished = None
        FakeRunLog.instances.append(self)

    def start(self, git_sha):
        pass

    def finish(self, status, snapshot_commit_sha=None, rows_written=None, error=None,
               cadence=None, column_changes=None, fantrax_logins=None):
        self.finished = dict(status=status, snapshot_commit_sha=snapshot_commit_sha,
                             rows_written=rows_written, error=error)
        self.cadence = cadence


class TestMain:
    """main() with everything below commit_data stubbed."""

    @pytest.fixture
    def pipe(self, monkeypatch, tmp_path):
        FakeRunLog.instances = []
        state = SimpleNamespace(notified=[], seen=[], line="", sha="c" * 40)
        mp = monkeypatch
        mp.setattr(rp, "_load_04a", lambda: SimpleNamespace(CFG=None, derive_week_label=lambda cfg: "03"))
        mp.setattr(rp, "derive_phase", lambda: "OFFSEASON")
        mp.setattr(rp, "build_steps", lambda profile: [{"name": "s1", "chain": "c1"}])
        mp.setattr(rp, "run_steps", lambda *a, **k: [{"name": "s1", "status": "ok", "detail": ""}])
        mp.setattr(rp.etl_checks, "load_registry", lambda: {})
        mp.setattr(rp.etl_checks, "chain_tables", lambda reg: {"c1": ["dim_a"]})
        mp.setattr(rp.etl_checks, "run_suite", lambda tables=None, accept=None, **k: [])
        mp.setattr(rp.etl_checks, "file_review",
                   lambda results, run_id: {"open": 0, "opened": 0, "cleared": 0, "repeated": 0})
        mp.setattr(rp, "review_counts", lambda: {})
        mp.setattr(rp, "notify", state.notified.append)
        mp.setattr(rp, "OUT_DIR", tmp_path)
        mp.setattr(rp, "resolve_storage_env", lambda *a, **k: "parquet")
        mp.setattr(rl, "RunLog", FakeRunLog)
        mp.setattr(rl, "head_sha", lambda repo: "a" * 40)
        mp.setattr(rl, "row_counts", lambda tables: {t: 3 for t in tables})

        def commit_data(*args, **kwargs):
            state.seen.append(kwargs)
            if rl.data_merged(state.line):
                kwargs["landed"].update(pr=9, sha=state.sha)
            return state.line
        mp.setattr(rp, "commit_data", commit_data)

        def run(*argv):
            mp.setattr(sys, "argv", ["run_pipeline.py", *argv])
            return rp.main()
        state.run = run
        return state

    def test_a_merged_data_pr_reads_published_with_the_landed_sha(self, pipe):
        pipe.line = "committed + merged 1 parquet file(s) via data PR #9"
        assert pipe.run() == 0
        done = FakeRunLog.instances[-1].finished
        assert done == dict(status="published", snapshot_commit_sha=pipe.sha,
                            rows_written={"dim_a": 3}, error=None)
        assert pipe.seen[0]["run_id"] == RUN_ID and pipe.seen[0]["rows"] == {"dim_a": 3}
        assert pipe.seen[0]["landed"] == {"pr": 9, "sha": pipe.sha}
        assert "📦 committed + merged 1 parquet file(s) via data PR #9" in pipe.notified[0]

    def test_a_pr_left_open_is_failed_not_published_and_the_notice_says_so(self, pipe):
        pipe.line = "ABORTED: data PR #9 left open, required check failed (tests)"
        assert pipe.run() == 1
        done = FakeRunLog.instances[-1].finished
        assert done["status"] == "failed"
        assert done["snapshot_commit_sha"] is None
        assert done["error"] == "ABORTED: data PR #9 left open, required check failed (tests)"
        assert len(pipe.notified) == 1
        assert "📦 ABORTED: data PR #9 left open, required check failed (tests)" in pipe.notified[0]

    def test_a_timeout_is_failed_too(self, pipe):
        pipe.line = "ABORTED: data PR #9 left open, checks not done after 30 min (waiting on tests)"
        assert pipe.run() == 1
        done = FakeRunLog.instances[-1].finished
        assert done["status"] == "failed" and done["snapshot_commit_sha"] is None
        assert done["error"] == pipe.line
        assert "left open" in pipe.notified[0]

    def test_no_push_reads_committed_with_the_local_sha_and_no_pr(self, pipe):
        pipe.line = "committed 1 file(s), push skipped (--no-push)"
        assert pipe.run("--no-push") == 0
        assert pipe.seen[0]["landed"] == {}
        done = FakeRunLog.instances[-1].finished
        assert (done["status"], done["snapshot_commit_sha"]) == ("committed", "a" * 40)

    def test_no_commit_calls_nothing(self, pipe):
        assert pipe.run("--no-commit") == 0
        assert pipe.seen == []
        assert FakeRunLog.instances[-1].finished["status"] == "committed"
