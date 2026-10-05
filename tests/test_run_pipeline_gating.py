"""Per-Chain publish gating in scripts/run_pipeline.py (#115, ADR-0008
amendment decision 3).

plan_publish is pure (fake step results + gate results in). commit_data runs
against a throwaway git repo on `main` with push=False, so the restore/stage
path is exercised without touching the real repo or any remote. The
registry-consistency tests pin the step table to docs/data_model.yml.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import pandas as pd

import etl_checks as ec
import run_pipeline as rp
from conftest import git

STEPS = [
    {"name": "s_core", "chain": "fantrax_core"},
    {"name": "s_core2", "chain": "fantrax_core"},
    {"name": "s_rookie", "chain": "rookie"},
    {"name": "s_dyn", "chain": "dynasty_profile"},
]
CHAINS = {"fantrax_core": ["fa", "fb"], "rookie": ["ra"], "dynasty_profile": ["da"]}


def _r(name, status="ok"):
    return {"name": name, "status": status, "detail": ""}


def _gate(table, chain, ok=True, tier="gate"):
    return ec.Result("grain", table, chain, tier, ok, "" if ok else "boom")


class TestPlanPublish:
    def test_all_pass(self):
        plan = rp.plan_publish(STEPS, [_r("s_core"), _r("s_rookie")], [], CHAINS)
        assert plan["passed"] == ["fantrax_core", "rookie"]
        assert plan["publish"] == ["fa", "fb", "ra"] and plan["restore"] == []

    def test_chain_not_run_is_not_judged(self):
        plan = rp.plan_publish(STEPS, [_r("s_rookie")], [_gate("da", "dynasty_profile", ok=False)], CHAINS)
        assert plan["passed"] == ["rookie"] and plan["failed"] == {}
        assert "da" not in plan["restore"]

    def test_failed_step_holds_only_its_chain(self):
        plan = rp.plan_publish(STEPS, [_r("s_core", "failed"), _r("s_core2", "skipped"),
                                       _r("s_rookie")], [], CHAINS)
        assert plan["passed"] == ["rookie"]
        assert plan["failed"] == {"fantrax_core": ["step s_core failed", "step s_core2 skipped"]}
        assert plan["publish"] == ["ra"] and plan["restore"] == ["fa", "fb"]

    def test_gate_failure_holds_chain(self):
        plan = rp.plan_publish(STEPS, [_r("s_core"), _r("s_rookie")],
                               [_gate("fb", "fantrax_core", ok=False), _gate("ra", "rookie")], CHAINS)
        assert plan["failed"] == {"fantrax_core": ["grain fb: boom"]}
        assert plan["publish"] == ["ra"]

    def test_review_finding_does_not_block(self):
        plan = rp.plan_publish(STEPS, [_r("s_rookie")], [_gate("ra", "rookie", ok=False, tier="review")], CHAINS)
        assert plan["passed"] == ["rookie"]

    def test_dry_run_counts_as_ran(self):
        plan = rp.plan_publish(STEPS, [_r("s_dyn", "dry-run")], [], CHAINS)
        assert plan["passed"] == ["dynasty_profile"]


def _write(repo, table, n):
    pd.DataFrame({"a": range(n)}).to_parquet(repo / "data" / f"{table}.parquet")


def _rows_at_head(repo, table):
    return ec.head_row_count(table, repo=repo)


class TestCommitData:
    def _seed(self, git_repo):
        for t in ("fa", "ra", "manual"):
            _write(git_repo, t, 5)
        (git_repo / "notes.txt").write_text("x")
        git(git_repo, "add", "-A")
        git(git_repo, "commit", "-q", "-m", "seed")

    def test_publishes_passing_restores_failed(self, git_repo):
        self._seed(git_repo)
        for t in ("fa", "ra", "manual"):     # every table refreshed on disk
            _write(git_repo, t, 9)
        _write(git_repo, "new_table", 3)     # a new, untracked passing-Chain table
        (git_repo / "notes.txt").write_text("y")
        line = rp.commit_data("OFFSEASON", "03", push=False, publish=["ra", "new_table"],
                              restore=["fa"], cwd=git_repo)
        assert line == "committed 1 file(s), push skipped (--no-push)"
        assert _rows_at_head(git_repo, "ra") == 9                  # published
        assert _rows_at_head(git_repo, "fa") == 5                  # held at HEAD...
        assert len(pd.read_parquet(git_repo / "data" / "fa.parquet")) == 5   # ...and restored
        assert _rows_at_head(git_repo, "manual") == 5              # manual: never staged
        assert _rows_at_head(git_repo, "new_table") is None        # untracked: left for a PR
        changed = git(git_repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
        assert changed == ["data/ra.parquet"]

    def test_nothing_to_publish(self, git_repo):
        self._seed(git_repo)
        _write(git_repo, "fa", 9)
        line = rp.commit_data("OFFSEASON", "03", push=False, publish=[], restore=["fa"], cwd=git_repo)
        assert line == "no data changes — commit skipped"
        assert len(pd.read_parquet(git_repo / "data" / "fa.parquet")) == 5

    def test_not_on_main(self, git_repo):
        self._seed(git_repo)
        git(git_repo, "switch", "-q", "-c", "feature")
        _write(git_repo, "fa", 9)
        line = rp.commit_data("OFFSEASON", "03", push=False, publish=["fa"], restore=[], cwd=git_repo)
        assert line.startswith("commit skipped: on branch 'feature'")

    def test_non_allowlisted_staged_path_aborts(self, git_repo):
        self._seed(git_repo)
        _write(git_repo, "ra", 9)
        (git_repo / "notes.txt").write_text("y")
        git(git_repo, "add", "notes.txt")
        line = rp.commit_data("OFFSEASON", "03", push=False, publish=["ra"], restore=[], cwd=git_repo)
        assert line.startswith("ABORTED: non-allowlisted")
        assert _rows_at_head(git_repo, "ra") == 5


class TestRegistryConsistency:
    REG = ec.load_registry()
    CHAINS = ec.chain_tables(REG)

    def test_every_step_has_a_registry_chain(self):
        for profile in (None, "dynasty"):
            for s in rp.build_steps(profile):
                assert s.get("chain") in self.CHAINS, s["name"]

    def test_every_chain_has_a_step(self):
        steps = {s["chain"] for s in rp.build_steps("dynasty")}
        assert set(self.CHAINS) <= steps

    def test_every_parquet_is_registered(self):
        on_disk = {p.stem for p in (REPO / "data").glob("*.parquet")}
        assert on_disk <= set(self.REG), sorted(on_disk - set(self.REG))

    def test_no_table_registered_twice(self):
        # One entry per table = one `chain:` per table (load_registry would
        # silently keep the last duplicate, so read the raw list).
        import yaml
        names = [t["name"] for t in
                 yaml.safe_load(ec.MODEL_YML.read_text(encoding="utf-8"))["tables"]]
        assert len(names) == len(set(names))


class TestScoringStep:
    """04s is an in-season step of the Fantrax core Chain (#118)."""

    STEPS = rp.build_steps(None)

    def test_it_runs_in_season_only_after_roster_state(self):
        names = [s["name"] for s in self.STEPS]
        step = self.STEPS[names.index("04s_scoring")]
        assert step["phases"] == {"INSEASON"}
        assert (step["chain"], step["needs"]) == ("fantrax_core", ["04r_roster_state"])
        # Sequential execution: the period dim, then Roster State, then scoring.
        assert names.index("04p_league_info") < names.index("04r_roster_state") \
            < names.index("04s_scoring")

    def test_its_tables_are_in_the_same_chain(self):
        reg = ec.load_registry()
        assert {reg[t]["chain"] for t in ("fact_period_scoring", "fact_matchup")} == {"fantrax_core"}
