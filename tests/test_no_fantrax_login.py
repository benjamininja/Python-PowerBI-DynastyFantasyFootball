"""No scheduled run, PC task or poll trigger signs in to Fantrax (the owner's
ruling of 2026-11-28, #760, #429 round 8).

The Actions run (scripts/run_daily.sh) and the PC task (run_weekly.ps1) both
start scripts/run_pipeline.py, which runs each step as a subprocess. So a
sign-in is reachable only through a step whose command names a signed-in
script. These tests run the real step table through run_steps with the
subprocess call replaced, under every phase, profile and step filter, and
check that no such command is started, that the public fxea steps still run
and that the run is not red because the retired steps are gone.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "notebooks"))

import etl_checks as ec  # noqa: E402
import run_pipeline as rp  # noqa: E402

PHASES = ("INSEASON", "PRESEASON", "OFFSEASON")
PROFILES = (None, "dynasty")
SIGNED_IN = {"04s_scoring", "04a_scrape", "04t_txn_history", "04a_backfill_gp",
             "04v_minor_contracts"}
NEEDS_SIGNED_IN = {"04z_crosswalk", "02d_ledger", "02f_dead_money", "02e_derive",
                   "02h_team_cap", "02k_contract_moves"}
PUBLIC_FXEA = {"04p_league_info", "04r_roster_state"}


def _run(monkeypatch, steps, phase, only=None, groups=None):
    started = []

    def fake(cmd, **kwargs):
        started.append([str(c) for c in cmd])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(rp.subprocess, "run", fake)
    results = rp.run_steps(steps, phase, only, dry_run=False, groups=groups)
    return results, started


def _names_a_login_script(cmd):
    return any(Path(c).name in rp.LOGIN_SCRIPTS for c in cmd)


def test_the_retired_steps_are_the_signed_in_steps_and_what_needs_them():
    for profile in PROFILES:
        assert rp.retired_steps(rp.build_steps(profile)) == SIGNED_IN | NEEDS_SIGNED_IN


def test_every_step_that_names_a_signed_in_script_is_retired():
    for profile in PROFILES:
        for s in rp.build_steps(profile):
            if rp.signs_in(s):
                assert s["retired"], s["name"]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("phase", PHASES)
def test_a_scheduled_run_starts_no_signed_in_script(monkeypatch, phase, profile):
    _, started = _run(monkeypatch, rp.build_steps(profile), phase)
    assert started
    assert [c for c in started if _names_a_login_script(c)] == []


@pytest.mark.parametrize("phase", PHASES)
def test_naming_a_retired_step_or_its_group_does_not_run_it(monkeypatch, phase):
    steps = rp.build_steps("dynasty")
    every = {s["name"] for s in steps}
    for only, groups in ((every, None), (SIGNED_IN | NEEDS_SIGNED_IN, None),
                         (None, {"regular_season"})):
        results, started = _run(monkeypatch, steps, phase, only, groups)
        assert [c for c in started if _names_a_login_script(c)] == []
        assert not {r["name"] for r in results} & (SIGNED_IN | NEEDS_SIGNED_IN)


def test_a_new_step_that_names_a_signed_in_script_is_retired_with_its_dependents():
    steps = [
        {"name": "a", "cmd": ["py", "notebooks/04t_fantrax_transaction_history.py"], "needs": []},
        {"name": "b", "cmd": ["py", "notebooks/x.py"], "needs": ["a"]},
        {"name": "c", "cmd": ["py", "notebooks/y.py"], "needs": ["b"]},
        {"name": "d", "cmd": ["py", "notebooks/z.py"], "needs": []},
    ]
    assert rp.retired_steps(steps) == {"a", "b", "c"}


@pytest.mark.parametrize("phase", PHASES)
def test_the_public_fxea_steps_still_run(monkeypatch, phase):
    results, _ = _run(monkeypatch, rp.build_steps(None), phase)
    assert {r["name"] for r in results if r["status"] == "ok"} >= PUBLIC_FXEA


@pytest.mark.parametrize("phase", PHASES)
def test_the_run_is_not_red_because_the_retired_steps_are_gone(monkeypatch, phase):
    steps = rp.build_steps(None)
    results, _ = _run(monkeypatch, steps, phase)
    assert all(r["status"] == "ok" for r in results)
    chains = ec.chain_tables(ec.load_registry())
    plan = rp.plan_publish(steps, results, [], chains)
    assert plan["failed"] == {}
    assert "fantrax_core" in plan["passed"]


def test_the_run_log_says_so_in_one_line():
    line = rp.retired_line(rp.build_steps(None), "INSEASON", None, None)
    assert "\n" not in line
    assert line.startswith("Fantrax logged-in pulls retired by the owner's ruling of 2026-11-28 (#760)")
    for name in SIGNED_IN | NEEDS_SIGNED_IN:
        assert name in line
    summary = rp.summarize("INSEASON", "12", [], {}, "no data changes — commit skipped",
                           retired=line)
    assert sum(1 for ln in summary.splitlines() if "(#760)" in ln) == 1


def test_no_line_when_no_retired_step_was_selected():
    assert rp.retired_line(rp.build_steps(None), "INSEASON", None, {"rookie"}) is None


def test_both_runners_start_only_the_orchestrator():
    for path in (REPO / "scripts" / "run_daily.sh", REPO / "run_weekly.ps1"):
        text = path.read_text(encoding="utf-8")
        assert "run_pipeline.py" in text
        assert not any(name in text for name in rp.LOGIN_SCRIPTS), path.name


def test_no_scheduled_workflow_reads_a_fantrax_secret():
    """The Change Poll of #93 brief 5, or any other scheduled workflow, may not
    read a Fantrax secret. A workflow that names one starts only by hand."""
    for path in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        wf = yaml.safe_load(text)
        on = wf.get("on", wf.get(True)) or {}
        if "FANTRAX_" in text:
            assert set(on) == {"workflow_dispatch"}, path.name
