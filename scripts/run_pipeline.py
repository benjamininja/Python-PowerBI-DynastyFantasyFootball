"""Weekly ETL orchestrator — phase-aware, Task Scheduler entrypoint.

Runs the scheduled slice of the pipeline in dependency order, gates each
Chain, surfaces review-queue counts, commits the passing Chains' refreshed
data (allowlisted `data/*.parquet` ONLY) by its own data PR, which it merges
itself once pii-scan, tests and bot-tests pass (#361; see CONTRIBUTING.md),
and notifies a private Discord channel via webhook.

Publish gate (ADR-0008 amendment, #115): the publish unit is a Chain
(fantrax_core, rookie, dynasty_profile, nflverse — each step and each
registry table carries one). After the steps, notebooks/etl_checks.py runs
the Gate checks on every table of each Chain that ran. A Chain with a failed
or skipped step or a failed Gate is held: its tracked parquet is restored
from git HEAD and never staged; the other Chains still publish. Manual-only
tables (no Chain) are never staged here — they reach main by PR.

Phase model (derived from 04a's week label + the season calendar):
  INSEASON   week label != PRE and the NFL season hasn't ended
  PRESEASON  week label == PRE, within ~45 days of Week-1 Thursday
  OFFSEASON  everything else (fixes the "February clamps to week 18" edge:
             derive_week_label alone would keep saying 18 forever)

Cadence (ADR-0020): each step is `daily` or `close_day`. A close_day step runs
on its Close Day, or on the first run after it with no success for that week
in ops.etl_run_log; `--cadence all` runs every step. The week is
(season, period) in season and the ISO week off season.

NOT scheduled, by design: live-draft chain (04w -> 02d -> 02e -> 05a), the
03-group rookie chain (manual Excel gates), and review applies (03z,
apply_fantrax_crosswalk_review). Nothing here writes to Fantrax: the one
write-side path (`04v --apply`) was removed under ADR-0011 and stays removed
(ADR-0019: Fantrax sets the `Minor` contract itself).

Run:  .\\run_weekly.ps1            (Task Scheduler wrapper, logs console)
      .\\run.ps1 scripts\\run_pipeline.py --dry-run --phase OFFSEASON
      .\\run.ps1 scripts\\run_pipeline.py --check-only   (suite only, no steps)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
NB = REPO / "notebooks"
OUT_DIR = REPO / "data" / "outputs"
STEP_TIMEOUT_S = 1800
REQUIRED_CHECKS = ("pii-scan", "tests", "bot-tests")
CHECKS_TIMEOUT_S = 1800
CHECKS_POLL_S = 30

sys.path.insert(0, str(NB))
import etl_checks  # noqa: E402  (notebooks/ on the path, like the notebooks do)
import etl_helpers  # noqa: E402
import etl_run_log  # noqa: E402

CLOSE_DAY_STEPS = frozenset({"03a_fantasypros", "03b_walterfootball", "03c_ktc_rookie",
                             "03d_draftsharks_rookie", "04b_ktc_dynasty"})
CADENCES = ("due", "all")

# Review queues surfaced (never blocking): file -> the action that drains it.
REVIEW_QUEUES = {
    "review_fuzzy_matches.csv": "run 03z_apply_fuzzy_review",
    "review_fantrax_crosswalk.csv": "run scripts/apply_fantrax_crosswalk_review.py",
    "review_dynasty_crosswalk.csv": "manual (no apply script exists yet)",
}


_FX04A = None


def _load_04a():
    """Import 04a by file path (leading-digit module name). Cached."""
    global _FX04A
    if _FX04A is None:
        spec = importlib.util.spec_from_file_location(
            "fx04a", NB / "04a_fantrax_weekly_scrape.py")
        _FX04A = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_FX04A)
    return _FX04A


def derive_phase(today: date | None = None) -> str:
    """INSEASON / PRESEASON / OFFSEASON from the week label + season calendar.

    Prefers dim_season's season_nfl_end_date (relative season 0) when
    populated; falls back to CFG.week1_thursday arithmetic (week-18 Monday).
    """
    today = today or date.today()
    fx = _load_04a()
    week = fx.derive_week_label(fx.CFG, today)
    w1_thu = date.fromisoformat(fx.CFG.week1_thursday)
    week1_monday = w1_thu + timedelta(days=4)
    season_end = week1_monday + timedelta(weeks=17)  # week-18 Monday
    try:
        import pandas as pd
        ds = etl_helpers.read_table("dim_season")
        row = ds[ds["relative_nfl_season_number"] == 0]
        end = row["season_nfl_end_date"].iloc[0] if len(row) else None
        if pd.notna(end):
            season_end = pd.Timestamp(end).date()
    except Exception:
        pass  # calendar fallback already set

    if week != fx.CFG.preseason_label and today <= season_end + timedelta(days=3):
        return "INSEASON"
    if week == fx.CFG.preseason_label and 0 <= (w1_thu - today).days <= 45:
        return "PRESEASON"
    return "OFFSEASON"


def _script(p: str, *args: str) -> list[str]:
    return [str(VENV_PY), str(NB / p), *args]


def _nbconvert(p: str) -> list[str]:
    return [str(VENV_PY), "-m", "nbconvert", "--to", "notebook",
            "--execute", "--inplace", str(NB / p)]


# Step table: name -> (cmd, phases it runs in, upstream deps, Chain, "group").
# "phases" (calendar timing) and "group" (domain area) are orthogonal — e.g.
# the rookie chain below isn't phase-gated at all (runs in every phase) but
# is its own group, so --phase and --group filter independently. "chain" is
# the publish unit and must match the `chain:` of the tables the step writes
# in docs/data_model.yml (tests/test_run_pipeline_gating.py enforces it).
# Order matters (sequential execution).
def build_steps(profile: str | None) -> list[dict]:
    steps = [
        {"name": "01f_dim_season", "cmd": _nbconvert("01f_dim_season_seed.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "fantrax_core", "group": "pre_season"},
        # Public getLeagueInfo (no login): dim_scoring_period with the
        # Update-Set states, and dim_division. It checks the season against
        # dim_season, so it follows 01f.
        {"name": "04p_league_info", "cmd": _script("04p_fantrax_league_info.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["01f_dim_season"], "chain": "fantrax_core", "group": "regular_season"},
        # Public getTeamRosters (no login): the Roster State of every
        # regular-season period that has started and is not closed. It reads
        # the periods and their Update-Set states from 04p's table.
        {"name": "04r_roster_state", "cmd": _script("04r_fantrax_roster_state.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04p_league_info"], "chain": "fantrax_core", "group": "regular_season"},
        # Logged-in getLiveScoringStats + getStandings (04a's session): Period
        # Scoring and Matchups of every period 04r just read whose games are
        # final. Its Starter Gate reads that period's Roster State, so it
        # follows 04r. A closed period is skipped.
        {"name": "04s_scoring", "cmd": _script("04s_fantrax_inseason_capture.py"),
         "phases": {"INSEASON"}, "needs": ["04r_roster_state"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "01e_dim_nfl_players", "cmd": _nbconvert("01e_dim_nfl_players_seed.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "nflverse", "group": "pre_season"},
        # Combine / pro-day metrics (nflverse, no login). Rebuilt right after
        # the player dim so its gsis_id never points at an id 01e just
        # dropped or changed (#149).
        {"name": "02a_combine_metrics", "cmd": _nbconvert("02a_fact_nfl_combine_pro_day_metrics.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["01e_dim_nfl_players"], "chain": "nflverse", "group": "pre_season"},
        # Snap counts and the injury report (nflverse, no login; ADR-0017).
        # It maps players through 01e's season and stamps each row with a
        # Scoring Period from 04p's table, which an earlier run has written.
        # Its own group, so `--group injury` refreshes it between weekly runs.
        {"name": "02g_nflverse_inseason", "cmd": _script("02g_nflverse_inseason.py"),
         "phases": {"INSEASON"}, "needs": ["01e_dim_nfl_players"], "chain": "nflverse", "group": "injury"},
        {"name": "04a_scrape", "cmd": _script("04a_fantrax_weekly_scrape.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04z_crosswalk", "cmd": _nbconvert("04z_fantrax_crosswalk.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04a_scrape"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04a_backfill_gp", "cmd": _script("04a_fantrax_weekly_scrape.py", "--backfill-gp"),
         "phases": {"INSEASON"}, "needs": ["04a_scrape"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04v_minor_contracts", "cmd": _script("04v_minor_contracts.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04z_crosswalk"], "chain": "fantrax_core", "group": "regular_season"},
        # Logged-in transaction history (04a's session, like 04v): the raw
        # capture 02d builds the ledger from. If it fails, 02d is skipped and
        # the Chain is held.
        {"name": "04t_txn_history", "cmd": _script("04t_fantrax_transaction_history.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04v_minor_contracts"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "02d_ledger", "cmd": _script("02d_fact_roster_transactions.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04v_minor_contracts", "04t_txn_history"], "chain": "fantrax_core", "group": "regular_season"},
        # Dead Money from the ledger's drops (no network). 02e's cap summary
        # reads it, so it sits between the ledger and the roster.
        {"name": "02f_dead_money", "cmd": _script("02f_fact_dead_money.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["02d_ledger"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "02e_derive", "cmd": _script("02e_fact_fantasy_teams_derive.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["02d_ledger"], "chain": "fantrax_core", "group": "regular_season"},
        # The published cap table (no network): this season is the roster's,
        # and each season's row carries only that season's Dead Money.
        {"name": "02h_team_cap", "cmd": _script("02h_fact_team_cap.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["02f_dead_money", "02e_derive"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04b_ktc_dynasty", "cmd": _nbconvert("04b_ktc_dynasty_rankings.ipynb"),
         "phases": {"OFFSEASON"}, "needs": [], "chain": "dynasty_profile", "group": "pre_season"},
        # Rookie chain (auto-safe scrapes only): 03a-03d ingest expert sources
        # directly. Deliberately stops here — 03x (manual Excel), 03y/03z
        # (fuzzy-review + apply) need a human in the loop, per
        # notebooks/README.md, and are never added to this orchestrator.
        {"name": "03a_fantasypros", "cmd": _nbconvert("03a_fantasypros_rankings.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "rookie", "group": "rookie"},
        {"name": "03b_walterfootball", "cmd": _nbconvert("03b_walterfootball_rankings.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "rookie", "group": "rookie"},
        {"name": "03c_ktc_rookie", "cmd": _nbconvert("03c_ktc_rankings.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "rookie", "group": "rookie"},
        {"name": "03d_draftsharks_rookie", "cmd": _nbconvert("03d_draftsharks_rankings.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "rookie", "group": "rookie"},
    ]
    if profile == "dynasty":
        # After the user refreshes the 04x manual Excel. 04b re-runs even if
        # the phase already included it (idempotent).
        steps += [
            {"name": "04b_ktc_dynasty_p", "cmd": _nbconvert("04b_ktc_dynasty_rankings.ipynb"),
             "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "dynasty_profile", "group": "pre_season"},
            {"name": "04c_dim_dynasty_metric", "cmd": _nbconvert("04c_dim_dynasty_metric.ipynb"),
             "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04b_ktc_dynasty_p"], "chain": "dynasty_profile", "group": "pre_season"},
            {"name": "04y_composite", "cmd": _nbconvert("04y_composite_dynasty_metrics.ipynb"),
             "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04c_dim_dynasty_metric"], "chain": "dynasty_profile", "group": "pre_season"},
        ]
    for s in steps:
        s["cadence"] = "close_day" if s["name"] in CLOSE_DAY_STEPS else "daily"
    return steps


def _selected(s: dict, phase: str, only: set[str] | None, groups: set[str] | None) -> bool:
    if phase not in s["phases"] or (only and s["name"] not in only):
        return False
    return not (groups and s.get("group") not in groups)


def league_today() -> date:
    return etl_helpers.league_date()


def close_day_state(today: date, periods=None, weekday: int | None = None) -> dict:
    """What the close_day steps owe on `today`, from `etl_helpers.close_state`,
    which alone defines the week (ADR-0020). `week_key` and `close_day` are
    None when no week is owed; `reason` says why: owed, not_yet or covered (a
    quiet day), unreadable (the calendar could not be read: no week, no guess).
    `periods` and `weekday` default to the stored table and the config."""
    owed = etl_helpers.close_state(today, periods, weekday)
    week = owed.week
    return {"week_key": week.key if week else None,
            "close_day": week.close_day if week else None,
            "mode": week.mode if week else None,
            "is_playoff": week.is_playoff if week else False,
            "reason": owed.reason}


def apply_cadence(steps: list[dict], phase: str, only: set[str] | None,
                  groups: set[str] | None, cadence: str, state: dict, today: date,
                  done_for: Callable[[str], set[str] | None]) -> tuple[list[dict], dict]:
    """Drop the close_day steps that are not due. Only a close_day step that
    phase, --steps and --group would otherwise run counts as ran or deferred.
    With an unreadable calendar (`state["reason"]`) no step is due, whatever
    `cadence` says. Otherwise a step is due when `cadence` is "all", or when the week in `state` has no
    record of it in `done_for(week_key)`; with no record to read (None) it is
    due on its Close Day only. Returns (steps to run, the cadence report)."""
    kept, ran, deferred = [], [], []
    record: list = []
    for s in steps:
        if s.get("cadence", "daily") != "close_day" or not _selected(s, phase, only, groups):
            kept.append(s)
            continue
        if state["reason"] == "unreadable":
            due = False
        elif cadence == "all":
            due = True
        elif state["week_key"] is None:
            due = False
        else:
            if not record:
                record.append(done_for(state["week_key"]))
            due = (today == state["close_day"]) if record[0] is None else s["name"] not in record[0]
        if due:
            kept.append(s)
            ran.append(s["name"])
        else:
            deferred.append(s["name"])
    return kept, {"filter": cadence, "week_key": state["week_key"],
                  "close_day": state["close_day"].isoformat() if state["close_day"] else None,
                  "mode": state["mode"], "is_playoff": state["is_playoff"],
                  "reason": state["reason"], "ran": ran, "deferred": deferred}


def close_steps_done(report: dict, results: list[dict], steps: list[dict], plan: dict | None,
                     commit_line: str) -> list[str]:
    """The close_day steps of this run that count as a success for its week: ok,
    their Chain passed and was not withheld, and the data was not aborted or
    left uncommitted."""
    landed = etl_run_log.data_committed(commit_line) or commit_line.startswith("no data changes")
    if not plan or not landed:
        return []
    chain_of = {s["name"]: s["chain"] for s in steps}
    good = set(plan["passed"]) - set(plan.get("unpublished", ()))
    return [r["name"] for r in results if r["name"] in report["ran"]
            and r["status"] == "ok" and chain_of[r["name"]] in good]


NO_WEEK = {"not_yet": "no Close Day yet", "covered": "week covered by the last period's run",
           "unreadable": "calendar unreadable, no week"}


def cadence_line(report: dict) -> str:
    when = f"week {report['week_key']}, Close Day {report['close_day']}" if report["week_key"] \
        else NO_WEEK.get(report.get("reason"), "no week owed")
    return (f"filter={report['filter']} ({when}); close_day ran: "
            f"{', '.join(report['ran']) or 'none'}; deferred: {', '.join(report['deferred']) or 'none'}")


def cadence_warning(report: dict) -> str | None:
    """A run-summary warning when the calendar could not be read: close_day
    steps are skipped (their catch-up runs once it reads), never keyed on a
    guessed week."""
    if report.get("reason") != "unreadable":
        return None
    return ("⚠️ dim_scoring_period could not be read: close_day steps skipped "
            f"({', '.join(report['deferred']) or 'none selected'}); they run once the calendar reads")


def run_steps(steps: list[dict], phase: str, only: set[str] | None,
              dry_run: bool, groups: set[str] | None = None) -> list[dict]:
    results = []
    status = {}   # name -> ok|failed|skipped
    env = {**os.environ, "PYTHONUTF8": "1"}
    for s in steps:
        name = s["name"]
        if not _selected(s, phase, only, groups):
            continue
        bad_dep = next((d for d in s["needs"] if status.get(d) in ("failed", "skipped")), None)
        if bad_dep:
            status[name] = "skipped"
            results.append({"name": name, "status": "skipped",
                            "detail": f"upstream {bad_dep} did not succeed"})
            print(f"[skip] {name} (needs {bad_dep})")
            continue
        print(f"[step] {name} ({s['chain']}): {' '.join(s['cmd'][1:])}")
        if dry_run:
            status[name] = "ok"
            results.append({"name": name, "status": "dry-run", "detail": ""})
            continue
        t0 = datetime.now()
        try:
            proc = subprocess.run(s["cmd"], cwd=REPO, env=env,
                                  capture_output=True, text=True,
                                  timeout=STEP_TIMEOUT_S)
            ok = proc.returncode == 0
            tail = "\n".join((proc.stderr or proc.stdout or "").splitlines()[-8:])
        except subprocess.TimeoutExpired:
            ok, tail = False, f"timeout after {STEP_TIMEOUT_S}s"
        status[name] = "ok" if ok else "failed"
        secs = (datetime.now() - t0).total_seconds()
        results.append({"name": name, "status": status[name],
                        "detail": "" if ok else tail, "secs": round(secs)})
        print(f"[{'ok' if ok else 'FAIL'}] {name} ({secs:.0f}s)")
        if not ok:
            print(tail)
    return results


def review_counts() -> dict:
    """Row counts (minus header) per review queue. Never raises."""
    counts = {}
    rd = REPO / "data" / "review"
    for fname, action in REVIEW_QUEUES.items():
        p = rd / fname
        try:
            n = max(0, sum(1 for _ in p.open(encoding="utf-8")) - 1) if p.exists() else 0
        except Exception:
            n = -1
        counts[fname] = {"rows": n, "action": action}
    return counts


def plan_publish(steps: list[dict], results: list[dict],
                 gate_results: list, chain_tables: dict[str, list[str]]) -> dict:
    """Which Chains publish. A Chain is judged only if one of its steps ran
    (or was skipped) this run; it fails on a failed step, a step skipped for
    an upstream failure, or a failed Gate check on one of its tables.
    Returns {passed, failed: {chain: [reasons]}, publish, restore} with
    publish/restore as table names."""
    chain_of = {s["name"]: s["chain"] for s in steps}
    why: dict[str, list[str]] = {}
    for r in results:
        c = chain_of[r["name"]]
        why.setdefault(c, [])
        if r["status"] in ("failed", "skipped"):
            why[c].append(f"step {r['name']} {r['status']}")
    for g in gate_results:
        if g.tier == "gate" and not g.ok and g.chain in why:
            why[g.chain].append(f"{g.check} {g.table}: {g.detail}")
    passed = sorted(c for c, w in why.items() if not w)
    failed = {c: w for c, w in sorted(why.items()) if w}
    return {"passed": passed, "failed": failed,
            "publish": sorted(t for c in passed for t in chain_tables.get(c, [])),
            "restore": sorted(t for c in failed for t in chain_tables.get(c, []))}


def _git(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _parquet_paths(tables: list[str]) -> list[str]:
    return [f"data/{t}.parquet" for t in tables]


def _gh(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(["gh", *args], 1, "", f"{type(exc).__name__}: {exc}")


def _checks_state(pr: int, cwd: Path) -> tuple[str, list[str]]:
    """One read of the PR's required checks: ("failed", names that failed),
    ("passed", []) or ("pending", names not yet passed). A check that gh does
    not list yet (the PR was just opened) is pending."""
    done = _gh("pr", "checks", str(pr), "--json", "name,bucket", cwd=cwd)
    try:
        rows = json.loads(done.stdout or "[]")
    except ValueError:
        rows = []
    seen: dict[str, set[str]] = {}
    for row in rows:
        if row.get("name") in REQUIRED_CHECKS:
            seen.setdefault(row["name"], set()).add(row.get("bucket"))
    failed = [n for n in REQUIRED_CHECKS if seen.get(n, set()) & {"fail", "cancel"}]
    if failed:
        return "failed", failed
    waiting = [n for n in REQUIRED_CHECKS if not (n in seen and seen[n] <= {"pass", "skipping"})]
    return ("pending", waiting) if waiting else ("passed", [])


def _wait_for_checks(pr: int, cwd: Path, timeout_s: float, poll_s: float) -> tuple[str, list[str]]:
    """Poll until the required checks pass or one fails; "timeout" when
    `timeout_s` runs out first."""
    deadline = time.monotonic() + timeout_s
    while True:
        state, names = _checks_state(pr, cwd)
        if state != "pending":
            return state, names
        if time.monotonic() >= deadline:
            return "timeout", names
        time.sleep(poll_s)


def _pr_view(pr: int, cwd: Path) -> dict:
    view = _gh("pr", "view", str(pr), "--json", "state,mergeCommit", cwd=cwd)
    try:
        info = json.loads(view.stdout or "{}")
    except ValueError:
        return {}
    return info if isinstance(info, dict) else {}


def _pr_body(staged: list[str], run_id: str | None, rows: dict | None) -> str:
    lines = ["Machine-generated parquet refresh via scripts/run_pipeline.py "
             "(allowlisted data-only commit). Opened and merged by the pipeline "
             "once pii-scan, tests and bot-tests pass.", "",
             f"Run log: {run_id or 'not written'}", "", "Tables:"]
    for path in staged:
        table = Path(path).stem
        lines.append(f"- {table}: {(rows or {}).get(table, 'rows unknown')}")
    return "\n".join(lines)


def _free_branch(stem: str, cwd: Path) -> str:
    """`stem`, or `stem-2`, `stem-3`, ... : the first name no local branch and
    no origin branch holds (an earlier run's PR may still be open)."""
    for n in range(1, 100):
        name = stem if n == 1 else f"{stem}-{n}"
        local = _git("rev-parse", "--verify", "--quiet", f"refs/heads/{name}", cwd=cwd).returncode == 0
        remote = _git("ls-remote", "--exit-code", "--heads", "origin", name, cwd=cwd).returncode == 0
        if not (local or remote):
            return name
    return stem


def _drop_branch(name: str, cwd: Path) -> subprocess.CompletedProcess:
    """Back to main, then delete the local data branch: its commit is on the
    remote PR, or is not wanted, and main must stay the checked-out branch."""
    back = _git("switch", "main", cwd=cwd)
    if back.returncode == 0:
        _git("branch", "-D", name, cwd=cwd)
    return back


def commit_data(phase: str, week: str, push: bool, publish: list[str],
                restore: list[str], cwd: Path = REPO, run_id: str | None = None,
                rows: dict | None = None, landed: dict | None = None,
                checks_timeout_s: float = CHECKS_TIMEOUT_S,
                poll_s: float = CHECKS_POLL_S) -> str:
    """Allowlisted data commit, per Chain, landed by its own data PR (#361).
    Restores the failed Chains' tracked parquet from HEAD, stages exactly the
    passing Chains' tracked parquet (never a glob), verifies every staged
    path, skips when nothing changed (change detection). With push, commits
    to data/<date>-<phase>-wk<NN>, rebases it on origin/main, pushes it, opens
    a PR, waits for the required checks (bounded) and rebase-merges it. A
    failed check, a timeout or a refused merge leaves the PR open. `landed`,
    when given, receives {"pr", "sha"} once the PR has merged. Without push
    the commit stays on local main and nothing is pushed.
    `publish`/`restore` are table names. Returns a one-line outcome."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).stdout.strip()
    if branch != "main":
        return f"commit skipped: on branch '{branch}', not main"
    held = _git("ls-files", "--", *_parquet_paths(restore), cwd=cwd).stdout.split() if restore else []
    if held:
        r = _git("checkout", "HEAD", "--", *held, cwd=cwd)
        if r.returncode != 0:
            return f"ABORTED: restore of held Chains failed: {r.stderr.strip()[:200]}"
    paths = _parquet_paths(publish)
    tracked = set(_git("ls-files", "--", *paths, cwd=cwd).stdout.split()) if paths else set()
    new = [p for p in paths if p not in tracked and (cwd / p).exists()]
    if new:
        # A new table reaches main by PR (registry entry + review), not here.
        print(f"[warn] untracked parquet left unstaged (add it by PR): {new}")
    if tracked:
        _git("add", "--", *sorted(tracked), cwd=cwd)
    staged = [l for l in _git("diff", "--cached", "--name-only", cwd=cwd).stdout.splitlines() if l]
    if not staged:
        return "no data changes — commit skipped"
    bad = [p for p in staged if not re.fullmatch(r"data/[^/]+\.parquet", p)]
    if bad:
        _git("reset", cwd=cwd)
        return f"ABORTED: non-allowlisted staged path(s): {bad}"
    title = f"data: pipeline refresh {date.today().isoformat()} ({phase.lower()}, wk {week})"
    msg = (f"{title}\n\n"
           f"Machine-generated parquet refresh via scripts/run_pipeline.py "
           f"(allowlisted data-only commit).\n\n"
           f"Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    data_branch = None
    if push:
        wk = re.sub(r"[^A-Za-z0-9._-]", "", week)
        data_branch = _free_branch(f"data/{date.today().isoformat()}-{phase.lower()}-wk{wk}", cwd)
        s = _git("switch", "-c", data_branch, cwd=cwd)
        if s.returncode != 0:
            _git("reset", cwd=cwd)
            _git("checkout", "HEAD", "--", *sorted(tracked), cwd=cwd)
            return f"ABORTED: could not create branch {data_branch}: {s.stderr.strip()[:200]}"
    c = _git("commit", "-m", msg, cwd=cwd)
    if c.returncode != 0:
        if data_branch:
            _drop_branch(data_branch, cwd)
        return f"ABORTED: commit failed: {c.stderr.strip()[:200]}"
    if not data_branch:
        return f"committed {len(staged)} file(s), push skipped (--no-push)"
    # autostash: nbconvert --inplace leaves executed .ipynb files dirty in the
    # working tree, which would otherwise block the rebase.
    r = _git("-c", "rebase.autostash=true", "pull", "--rebase", "origin", "main", cwd=cwd)
    if r.returncode != 0:
        _git("rebase", "--abort", cwd=cwd)
        _drop_branch(data_branch, cwd)
        return f"ABORTED: rebase conflict — resolve manually: {r.stderr.strip()[:200]}"
    p = _git("push", "-u", "origin", data_branch, cwd=cwd)
    if p.returncode != 0:
        _drop_branch(data_branch, cwd)
        return f"ABORTED: push failed: {p.stderr.strip()[:200]}"
    made = _gh("pr", "create", "--base", "main", "--head", data_branch, "--title", title,
               "--body", _pr_body(staged, run_id, rows), cwd=cwd)
    found = re.search(r"/pull/(\d+)", made.stdout) if made.returncode == 0 else None
    if not found:
        _drop_branch(data_branch, cwd)
        return (f"ABORTED: {data_branch} pushed but no data PR was opened: "
                f"{(made.stderr or made.stdout).strip()[:200]}")
    pr = int(found.group(1))
    state, names = _wait_for_checks(pr, cwd, checks_timeout_s, poll_s)
    # Whatever the checks say, data/ goes back to main's files until the PR lands.
    back = _drop_branch(data_branch, cwd)
    if back.returncode != 0:
        return f"ABORTED: data PR #{pr} left open, could not switch back to main"
    if state == "failed":
        return f"ABORTED: data PR #{pr} left open, required check failed ({', '.join(names)})"
    if state == "timeout":
        return (f"ABORTED: data PR #{pr} left open, checks not done after "
                f"{int(checks_timeout_s // 60)} min (waiting on {', '.join(names)})")
    merge = _gh("pr", "merge", str(pr), "--rebase", "--delete-branch", cwd=cwd)
    info = _pr_view(pr, cwd)
    if info.get("state") != "MERGED":
        return (f"ABORTED: data PR #{pr} left open, merge refused "
                f"({' '.join((merge.stderr or merge.stdout).split())[:200]})")
    _git("branch", "-D", data_branch, cwd=cwd)
    sha = (info.get("mergeCommit") or {}).get("oid")
    if not sha:
        sha = (_pr_view(pr, cwd).get("mergeCommit") or {}).get("oid")
    notes = []
    pulled = _git("-c", "merge.autostash=true", "pull", "--ff-only", "origin", "main", cwd=cwd)
    if pulled.returncode != 0:
        print(f"[warn] data PR #{pr} merged but local main did not fast-forward: "
              f"{pulled.stderr.strip()[:200]}")
        notes.append("local main not fast-forwarded, run git pull")
    if not sha:
        sha = _git("rev-parse", "origin/main", cwd=cwd).stdout.strip() or None
        notes.append("landed sha taken from origin/main" if sha else "landed sha unknown")
    if landed is not None:
        landed.update(pr=pr, sha=sha)
    return (f"committed + merged {len(staged)} parquet file(s) via data PR #{pr}"
            + "".join(f"; {n}" for n in notes))


def storage_is_postgres() -> bool:
    return (os.environ.get("ETL_STORAGE") or "parquet") == "postgres"


def _withhold(plan: dict) -> None:
    """Nothing publishes: the passing Chains are listed as not published."""
    plan["publish"] = []
    plan["unpublished"] = list(plan["passed"])


def _dirty_data(tables: list[str], cwd: Path) -> int:
    """How many data/ files of `tables` differ from HEAD (modified, staged or
    untracked). Raises when git cannot say, so a git error never reads as clean."""
    r = _git("status", "--porcelain", "--untracked-files=all", "--", *_parquet_paths(tables), cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError("git could not compare data/ with HEAD")
    return len([line for line in r.stdout.splitlines() if line.strip()])


def _data_to_head(tables: list[str], cwd: Path) -> None:
    """Put the data/ files of `tables` back to HEAD: tracked ones are checked
    out, untracked ones (no HEAD copy) are removed."""
    paths = _parquet_paths(tables)
    r = _git("ls-files", "--", *paths, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError("git could not list data/")
    tracked = r.stdout.split()
    if tracked and _git("checkout", "HEAD", "--", *tracked, cwd=cwd).returncode != 0:
        raise RuntimeError("git could not restore data/ to HEAD")
    for path in set(paths) - set(tracked):
        (cwd / path).unlink(missing_ok=True)


def publish_postgres(plan: dict, cwd: Path = REPO, export: bool = True) -> str | None:
    """The Postgres branch of the publish step (#136, ADR-0014). The steps
    wrote to the database and left data/ equal to HEAD. The failed Chains'
    tables are reloaded from that snapshot in one transaction; if the database
    refuses (a passing Chain's rows reference a key the reload removes), every
    table the run wrote is reloaded and nothing publishes; if it refuses that
    too the run is ABORTED. Then each passing Chain's tables are exported from
    the database to data/, rows sorted by primary key, for commit_data to stage.
    Changes plan["publish"] and adds plan["notes"]. Returns an ABORTED line, or
    None when commit_data should go on. Prints and returns names and counts,
    never a cell."""
    import etl_storage_pg as pg
    data = cwd / "data"
    notes = plan.setdefault("notes", [])
    written = sorted(set(plan["publish"]) | set(plan["restore"]))
    url = os.environ.get(pg.URL_ENV)
    try:
        if not url:
            raise RuntimeError(f"{pg.URL_ENV} is not set")
        if plan["restore"]:
            moved = _dirty_data(written, cwd)
            if moved:
                _withhold(plan)
                return (f"ABORTED: {moved} file(s) under data/ differ from HEAD "
                        f"with ETL_STORAGE=postgres; the snapshot to reload from is not clean")
            loaded = pg.reload_snapshot(url, plan["restore"], data)
            if loaded.problems:
                notes.append(f"reload of the held Chains refused ({loaded.problems[0]}); "
                             f"all {len(written)} table(s) the run wrote reloaded from the snapshot, "
                             f"nothing published")
                loaded = pg.reload_snapshot(url, written, data)
                if loaded.problems:
                    _withhold(plan)
                    return f"ABORTED: reload from the snapshot refused: {loaded.problems[0]}"
                _withhold(plan)
    except Exception as exc:
        _withhold(plan)
        return f"ABORTED: reload from the snapshot failed: {pg.describe(exc)}"
    if export and plan["publish"]:
        published = list(plan["publish"])
        try:
            pg.export_published(published, data)
        except Exception as exc:
            _withhold(plan)
            try:
                _data_to_head(published, cwd)
                loaded = pg.reload_snapshot(url, sorted(set(published) | set(plan["restore"])), data)
                if loaded.problems:
                    raise RuntimeError(loaded.problems[0])
            except Exception as again:
                return f"ABORTED: export failed ({pg.describe(exc)}); recovery failed ({pg.describe(again)})"
            return f"ABORTED: export failed: {pg.describe(exc)}"
    return None


def notify(text: str) -> None:
    """Discord webhook (DISCORD_WEBHOOK_URL in .env / env). Never raises."""
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        url = etl_run_log.env_value("DISCORD_WEBHOOK_URL", REPO / ".env")
    if not url:
        print("[info] no DISCORD_WEBHOOK_URL — notification skipped")
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"content": text[:1900]}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": "DiscordBot (https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball, 1.0)"})
        urllib.request.urlopen(req, timeout=15)
        print("[ok] Discord notification sent")
    except Exception as e:
        reason = str(e).replace(url, "<webhook>")
        print(f"[warn] webhook failed: {type(e).__name__}: {reason}")


def summarize(phase: str, week: str, results: list[dict], reviews: dict,
              commit_line: str, plan: dict | None = None,
              filed: dict | None = None, cadence: dict | None = None) -> str:
    lines = [f"**Pipeline {date.today().isoformat()}** — phase {phase}, week {week}"]
    if cadence:
        lines.append(f"🗓️ {cadence_line(cadence)}")
        if cadence_warning(cadence):
            lines.append(cadence_warning(cadence))
    for r in results:
        mark = {"ok": "✅", "dry-run": "▫️", "skipped": "⏭️"}.get(r["status"], "❌")
        lines.append(f"{mark} {r['name']}" + (f" — {r['detail']}" if r["detail"] else ""))
    if plan:
        lines.append("**Chains:**")
        lines += [f"✅ {c}: " + ("passed, not published" if c in plan.get("unpublished", ()) else "published")
                  for c in plan["passed"]]
        lines += [f"🛑 {c}: held at HEAD — {'; '.join(w)[:300]}"
                  for c, w in plan["failed"].items()]
        lines += [f"♻️ {n}" for n in plan.get("notes", [])]
    if filed:
        lines.append(f"🔎 Review findings: {filed['open']} open "
                     f"({filed['opened']} new, {filed['cleared']} cleared)")
    pending = {f: v for f, v in reviews.items() if v["rows"] > 0}
    if pending:
        lines.append("**Review queues:**")
        lines += [f"• {f}: {v['rows']} rows → {v['action']}" for f, v in pending.items()]
    lines.append(f"📦 {commit_line}")
    return "\n".join(lines)


def check_only(accepted_shrink: list[str]) -> int:
    """--check-only: the whole suite against the current snapshot (every
    registered table, manual ones included). No steps, no commit, no Discord.
    Files Review findings to the local CSV. Exit 1 on any Gate failure."""
    results = etl_checks.run_suite(accepted_shrink=accepted_shrink)
    for r in results:
        mark = "ok  " if r.ok else ("FAIL" if r.tier == "gate" else "FIND")
        extra = r.detail or "; ".join(d for _, d in r.findings)
        print(f"[{mark}] {r.tier:6} {r.check:15} {r.table}" + (f" — {extra}" if extra else ""))
    filed = etl_checks.file_review(results, run_id=_run_id())
    gate_fail = [r for r in results if r.tier == "gate" and not r.ok]
    print(f"\n{len(results)} checks, {len(gate_fail)} Gate failure(s); review findings "
          f"{filed['open']} open ({filed['opened']} new, {filed['repeated']} repeat, "
          f"{filed['cleared']} cleared) -> {etl_checks.REVIEW_CSV}")
    return 1 if gate_fail else 0


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_storage_env(env_file: Path | None = None) -> str:
    for key in ("ETL_STORAGE", etl_run_log.URL_ENV):
        if not os.environ.get(key):
            value = etl_run_log.env_value(key, REPO / ".env" if env_file is None else env_file)
            if value:
                os.environ[key] = value
    return os.environ.get("ETL_STORAGE") or "parquet"


def main() -> int:
    # Console may be cp1252 (bare python.exe outside run_weekly.ps1's
    # PYTHONUTF8): keep the summary's emoji from crashing the print. Guarded
    # because a Jupyter kernel's stdout (00_fantasy_etl_flow.ipynb calling
    # main() directly) is an OutStream, not a real file object.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Phase-aware weekly ETL pipeline")
    ap.add_argument("--phase", choices=["INSEASON", "PRESEASON", "OFFSEASON"],
                    help="override phase derivation (testing)")
    ap.add_argument("--steps", help="comma-separated step names to run (subset)")
    ap.add_argument("--group", help="comma-separated groups to run "
                    "(pre_season,rookie,regular_season,injury) — orthogonal "
                    "to --phase, combines with AND")
    ap.add_argument("--cadence", choices=CADENCES, default="due",
                    help="due (default): a close_day step runs on its Close Day "
                         "or the first run after it that has no success for "
                         "the week; all: every step runs whatever the day "
                         "(close_day steps still wait for a readable calendar)")
    ap.add_argument("--profile", choices=["dynasty"],
                    help="extra chain: dynasty = 04b -> 04c -> 04y "
                         "(run after refreshing the 04x manual Excel)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the step plan, execute nothing, commit nothing")
    ap.add_argument("--no-commit", action="store_true",
                    help="run steps and checks, stop before publishing (a held "
                         "Chain's output stays on disk for inspection)")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--check-only", action="store_true",
                    help="run the check suite on the current snapshot only: "
                         "no steps, no commit, no Discord; exit 1 on a Gate failure")
    ap.add_argument("--accept-shrink", action="append", default=[], metavar="TABLE",
                    help="let TABLE shrink past its limit (known rollover); repeatable")
    ap.add_argument("--trigger", choices=etl_run_log.TRIGGERS, default="manual",
                    help="what started the run, for ops.etl_run_log")
    args = ap.parse_args()

    print(f"storage: {resolve_storage_env()}")

    if args.check_only:
        return check_only(args.accept_shrink)

    runlog = etl_run_log.RunLog(args.trigger)
    if not args.dry_run:
        runlog.start(etl_run_log.head_sha(REPO))
    try:
        phase = args.phase or derive_phase()
        week = _load_04a().derive_week_label(_load_04a().CFG)
        print(f"[info] phase={phase} week={week} "
              f"{'[DRY RUN]' if args.dry_run else ''}")

        steps = build_steps(args.profile)
        only = set(args.steps.split(",")) if args.steps else None
        groups = set(args.group.split(",")) if args.group else None
        today = league_today()
        state = close_day_state(today)
        steps, cadence = apply_cadence(steps, phase, only, groups, args.cadence, state,
                                       today, etl_run_log.steps_done)
        print(f"[cadence] {cadence_line(cadence)}")
        results = run_steps(steps, phase, only, args.dry_run, groups)

        plan, filed = None, None
        if not args.dry_run:
            # Gate every table of each Chain that had a step run this phase.
            chains = etl_checks.chain_tables(etl_checks.load_registry())
            ran = {s["chain"] for s in steps if s["name"] in {r["name"] for r in results}}
            # data_dir=None: under Postgres the Gates read the database.
            read_from = {"data_dir": None} if storage_is_postgres() else {}
            suite = etl_checks.run_suite([t for c in ran for t in chains.get(c, [])],
                                         args.accept_shrink, **read_from)
            plan = plan_publish(steps, results, suite, chains)
            for c in plan["passed"]:
                print(f"[chain] {c}: pass")
            for c, w in plan["failed"].items():
                print(f"[chain] {c}: HELD — {'; '.join(w)}")
            # File only what publishes: a held Chain's tables revert to HEAD.
            filed = etl_checks.file_review(
                [r for r in suite if r.table in plan["publish"]], run_id=_run_id())

        reviews = review_counts()
        rows, landed = None, {}
        if args.dry_run:
            commit_line = "commit skipped (flag)"
        elif args.no_commit:
            # The database is the system of record: a held Chain's rows go
            # back to the snapshot even when nothing is exported or committed.
            aborted = publish_postgres(plan, export=False) if storage_is_postgres() else None
            commit_line = aborted or "commit skipped (flag)"
        else:
            aborted = publish_postgres(plan) if storage_is_postgres() else None
            if not aborted:
                rows = etl_run_log.row_counts(plan["publish"])
            commit_line = aborted or commit_data(phase, week, push=not args.no_push,
                                                 publish=plan["publish"], restore=plan["restore"],
                                                 run_id=runlog.run_id, rows=rows, landed=landed)
        print(f"[info] {commit_line}")

        failed = bool(plan and plan["failed"]) or any(
            r["status"] not in ("ok", "dry-run") for r in results)
        code = 1 if failed or commit_line.startswith("ABORTED") else 0

        cadence["done"] = [] if args.no_commit or not cadence["week_key"] else close_steps_done(
            cadence, results, steps, plan, commit_line)
        if runlog.run_id:
            runlog.finish(
                etl_run_log.final_status(code, commit_line),
                snapshot_commit_sha=(landed.get("sha") if etl_run_log.data_merged(commit_line)
                                     else etl_run_log.head_sha(REPO)
                                     if etl_run_log.data_committed(commit_line) else None),
                rows_written=(rows if rows is not None
                              else etl_run_log.row_counts(plan["publish"])),
                error=(etl_run_log.failure_summary(results, plan, commit_line)
                       if code else None),
                cadence=cadence)
    except BaseException as exc:
        runlog.finish("failed", error=f"{type(exc).__name__} raised before the run finished")
        if runlog.warning and not args.dry_run:
            notify(f"{runlog.warning}\nThe pipeline raised {type(exc).__name__} before it finished.")
        raise

    summary = summarize(phase, week, results, reviews, commit_line, plan, filed, cadence)
    if runlog.warning:
        summary = f"{runlog.warning}\n{summary}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pipeline_summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    if not args.dry_run:
        notify(summary)

    return code


if __name__ == "__main__":
    sys.exit(main())
