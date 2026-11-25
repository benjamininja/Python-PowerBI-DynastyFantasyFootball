"""Weekly ETL orchestrator — phase-aware, Task Scheduler entrypoint.

Runs the scheduled slice of the pipeline in dependency order, gates each
Chain, surfaces review-queue counts, commits the passing Chains' refreshed
data (allowlisted `data/*.parquet` ONLY) by its own data PR, which it merges
itself once pii-scan, tests and bot-tests pass (#361; see CONTRIBUTING.md),
and notifies a private Discord channel via webhook.

Publish gate (ADR-0008 amendment, #115): the publish unit is a Chain
(fantrax_core, rookie, dynasty_profile, nflverse, team_manifest — each step
and each registry table carries one). After the steps, notebooks/etl_checks.py runs
the Gate checks on every table of each Chain that ran. A Chain with a failed
or skipped step or a failed Gate is held: its tracked parquet is restored
from git HEAD and never staged; the other Chains still publish. One id-only
exception (ADR-0008 amendment, #639): the gsis_id re-key belongs to the nflverse
Chain and is all or nothing. A table holding a gsis_id of a Chain that did not
run or was held goes back to its published rows, has each old gsis_id of
dim_gsis_link put on its newest id and publishes with the nflverse Chain's link
row, or neither does (one table refusing, one Gate failing or a step raising
puts every remapped table back and holds nflverse). A run never
stages a manual-only table (no Chain). It reaches main by a PR of its own or,
on the owner's command only, by `--publish-manual TABLE ...` (#616): an
allowlisted manual-only table is Gate-checked and exported from the store,
then lands by the same data PR as a Chain publish.

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
03-group rookie chain (manual Excel gates), and review applies (03z; a
crosswalk decision is the Record a crosswalk override workflow). Nothing here writes to Fantrax: the one
write-side path (`04v --apply`) was removed under ADR-0011 and stays removed
(ADR-0019: Fantrax sets the `Minor` contract itself).

Run:  .\\run_weekly.ps1            (Task Scheduler wrapper, logs console)
      .\\run.ps1 scripts\\run_pipeline.py --dry-run --phase OFFSEASON
      .\\run.ps1 scripts\\run_pipeline.py --check-only   (suite only, no steps)
      .\\run.ps1 scripts\\run_pipeline.py --publish-manual TABLE [TABLE ...]
                                                     (the owner only, #616)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

REPO = Path(__file__).resolve().parent.parent


def _find_python(repo: Path) -> Path:
    for candidate in (repo / ".venv" / "Scripts" / "python.exe", repo / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate
    return Path(sys.executable)


VENV_PY = _find_python(REPO)
NB = REPO / "notebooks"
OUT_DIR = REPO / "data" / "outputs"
STEP_TIMEOUT_S = 1800
REQUIRED_CHECKS = ("pii-scan", "tests", "bot-tests")
CHECKS_TIMEOUT_S = 1800
CHECKS_POLL_S = 30

sys.path.insert(0, str(NB))
import etl_checks  # noqa: E402  (notebooks/ on the path, like the notebooks do)
import etl_contract_moves  # noqa: E402
import etl_helpers  # noqa: E402
import etl_run_log  # noqa: E402

CLOSE_DAY_STEPS = frozenset({"03b_walterfootball", "03d_draftsharks_rookie"})
CADENCES = ("due", "all")

# Review queues surfaced (never blocking): file -> the action that drains it.
REVIEW_QUEUES = {
    "review_fuzzy_matches.csv": "run 03z_apply_fuzzy_review",
    "review_fantrax_crosswalk.csv": "GitHub Actions: Record a crosswalk override",
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


FANTRAX_SESSION_DIR_ENV = "FANTRAX_SESSION_DIR"
FANTRAX_LOGIN_LEDGER = "logins"
FANTRAX_BLOCKED_LEDGER = "blocked"


def open_fantrax_session() -> Path:
    """One folder per run. It carries the Fantrax session and the login
    count between the steps' processes (#525); removed when the run ends."""
    folder = Path(tempfile.mkdtemp(prefix="fantrax_session_"))
    os.environ[FANTRAX_SESSION_DIR_ENV] = str(folder)
    return folder


def close_fantrax_session(folder: Path | None) -> None:
    if folder is None:
        return
    os.environ.pop(FANTRAX_SESSION_DIR_ENV, None)
    shutil.rmtree(folder, ignore_errors=True)


def _ledger(folder: Path | None, name: str) -> list[str]:
    if folder is None:
        return []
    try:
        return (folder / name).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def fantrax_logins(folder: Path | None) -> list[str]:
    """The scripts that logged in to Fantrax this run, one entry per login."""
    return _ledger(folder, FANTRAX_LOGIN_LEDGER)


def fantrax_blocked(folder: Path | None) -> list[str]:
    """The scripts whose login the per-run cap refused (no login was tried)."""
    return _ledger(folder, FANTRAX_BLOCKED_LEDGER)


def _script(p: str, *args: str) -> list[str]:
    return [str(VENV_PY), str(NB / p), *args]


def _nbconvert(p: str) -> list[str]:
    return [str(VENV_PY), "-m", "nbconvert", "--to", "notebook",
            "--execute", "--inplace", str(NB / p)]


def _nbconvert_untracked(p: str) -> list[str]:
    """Execute a notebook that reads the owner sheet without saving its
    outputs into the tracked file: the executed copy goes to data/outputs
    (gitignored). The tracked notebook stays output-free (nbstripout and
    check_pii.py OUTPUT_FREE)."""
    return [str(VENV_PY), "-m", "nbconvert", "--to", "notebook", "--execute",
            "--output-dir", str(OUT_DIR), "--output", p, str(NB / p)]


# Step table: name -> (cmd, phases it runs in, upstream deps, Chain, "group").
# "phases" (calendar timing) and "group" (domain area) are orthogonal — e.g.
# the rookie chain below isn't phase-gated at all (runs in every phase) but
# is its own group, so --phase and --group filter independently. "chain" is
# the publish unit and must match the `chain:` of the tables the step writes
# in docs/data_model.yml (tests/test_run_pipeline_gating.py enforces it).
# Order matters (sequential execution).
def build_steps(profile: str | None) -> list[dict]:
    steps = [
        # The team-manifest (a private Google Sheet, read as a service account;
        # #609, #614) in a Chain of its own, so a missing or unreadable
        # GOOGLE_SHEETS_KEY_FILE holds only this table's publish. First, so the
        # fantrax_core steps that read dim_fantasy_teams (02d, 02e, 02h, 02k)
        # read it as the run leaves it; none of them needs it. Runs out of
        # data/outputs, so the owner's sheet never lands in the tracked notebook.
        {"name": "01c_dim_fantasy_teams", "cmd": _nbconvert_untracked("01c_dim_fantasy_teams_seed.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "team_manifest", "group": "pre_season"},
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
        # Minors eligibility of every player from nflverse (no login; #524,
        # #538). It reads 01e's player list and 04p's Scoring Periods, and
        # writes the table the minor_drift check compares with 04v's.
        {"name": "02j_minor_eligibility", "cmd": _script("02j_nflverse_minor_eligibility.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["01e_dim_nfl_players", "04p_league_info"], "chain": "nflverse", "group": "pre_season"},
        {"name": "04a_scrape", "cmd": _script("04a_fantrax_weekly_scrape.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "fantrax_core", "group": "regular_season"},
        # Logged-in transaction history (04a's session, like 04v): the raw
        # capture 02d builds the ledger from and 04z reads for scorers seen
        # only in a trade or claim. If it fails, 02d is skipped and the Chain
        # is held.
        {"name": "04t_txn_history", "cmd": _script("04t_fantrax_transaction_history.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04a_scrape"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04a_backfill_gp", "cmd": _script("04a_fantrax_weekly_scrape.py", "--backfill-gp"),
         "phases": {"INSEASON"}, "needs": ["04a_scrape"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04z_crosswalk", "cmd": _nbconvert("04z_fantrax_crosswalk.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04a_scrape", "04t_txn_history", "04a_backfill_gp"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04v_minor_contracts", "cmd": _script("04v_minor_contracts.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04z_crosswalk"], "chain": "fantrax_core", "group": "regular_season"},
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
        # The commissioners' contract lists (no network; #545): Minor to 1st,
        # Expiring and the re-sign Decision table off the current roster. It
        # reads, so it needs the step of each table it reads inside its own
        # Chain: the roster (02e), the ledger (02d) and 04v's eligibility
        # capture. dim_nfl_players and dim_gsis_link (both 01e) and
        # fact_nfl_minor_eligibility (02j) are read as the run leaves them,
        # with no need, so an nflverse failure does not hold this Chain.
        # dim_fantasy_teams (01c, the team_manifest Chain) is read the same way.
        {"name": "02k_contract_moves", "cmd": _script("02k_fact_contract_move.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"},
         "needs": ["02e_derive", "04v_minor_contracts", "02d_ledger"], "chain": "fantrax_core", "group": "regular_season"},
        # Rookie chain (auto-safe scrapes only): 03b and 03d ingest expert
        # sources directly. Deliberately stops here — 03x (manual Excel), 03y/03z
        # (fuzzy-review + apply) need a human in the loop, per
        # notebooks/README.md, and are never added to this orchestrator.
        {"name": "03b_walterfootball", "cmd": _nbconvert("03b_walterfootball_rankings.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "rookie", "group": "rookie"},
        {"name": "03d_draftsharks_rookie", "cmd": _nbconvert("03d_draftsharks_rankings.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "rookie", "group": "rookie"},
    ]
    if profile == "dynasty":
        # After the user refreshes the 04x manual Excel.
        steps += [
            {"name": "04c_dim_dynasty_metric", "cmd": _nbconvert("04c_dim_dynasty_metric.ipynb"),
             "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "dynasty_profile", "group": "pre_season"},
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


ACCESS_STEP = "access_loads"
ACCESS_PREFIX = "access:"
ACCESS_TIMEOUT_S = 300


def access_lines(text: str | None) -> list[str]:
    """Only the lines the access step marks as its own (counts, tab names and row
    numbers, never an id). Whatever else it printed, a traceback included, stays
    out of the notice and the log."""
    return [line.strip() for line in (text or "").splitlines() if line.startswith(ACCESS_PREFIX)]


def run_access_loads(dry_run: bool, no_commit: bool, only: set[str] | None,
                     groups: set[str] | None, run=subprocess.run) -> dict | None:
    """The scheduled run's load of the role table and the owner crosswalk (#700,
    ADR-0026 decision 2). It is not a step of any Chain, so a failure holds no
    data Chain: its result stays out of `results` and `plan_publish` and goes to
    the notice and the exit code on its own. It runs when no subset is named, or
    when `--steps` names it; never under --dry-run (the plan is printed) or
    --no-commit. Returns None when it does not run, else {name, status, detail}."""
    if (only or groups) and not (only and ACCESS_STEP in only):
        return None
    cmd = [str(VENV_PY), str(REPO / "scripts" / "load_access_tables.py")]
    print(f"[step] {ACCESS_STEP} (no Chain): {' '.join(cmd[1:])}")
    if dry_run:
        return {"name": ACCESS_STEP, "status": "dry-run", "detail": ""}
    if no_commit:
        print(f"[skip] {ACCESS_STEP} (--no-commit)")
        return None
    try:
        proc = run(cmd, cwd=REPO, env={**os.environ, "PYTHONUTF8": "1"},
                   capture_output=True, text=True, timeout=ACCESS_TIMEOUT_S)
        ok, lines = proc.returncode == 0, access_lines(proc.stdout)
        if not ok and not lines:
            lines = [f"{ACCESS_PREFIX} load stopped before it reported (exit {proc.returncode}); both tables are as they were"]
    except subprocess.TimeoutExpired:
        ok, lines = False, [f"{ACCESS_PREFIX} load timed out after {ACCESS_TIMEOUT_S}s; both tables are as they were"]
    for line in lines:
        print(line)
    print(f"[{'ok' if ok else 'FAIL'}] {ACCESS_STEP}")
    return {"name": ACCESS_STEP, "status": "ok" if ok else "failed", "detail": "\n".join(lines)}


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


PR_INTRO = "Machine-generated parquet refresh via scripts/run_pipeline.py"
MANUAL_INTRO = ("Manual-only table(s) exported from the store on the owner's "
                "--publish-manual command via scripts/run_pipeline.py (#616)")


def _pr_body(staged: list[str], run_id: str | None, rows: dict | None,
             intro: str = PR_INTRO) -> str:
    lines = [f"{intro} "
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
                poll_s: float = CHECKS_POLL_S, title: str | None = None,
                branch_stem: str | None = None, intro: str = PR_INTRO) -> str:
    """Allowlisted data commit, per Chain, landed by its own data PR (#361).
    Restores the failed Chains' tracked parquet from HEAD, stages exactly the
    passing Chains' tracked parquet (never a glob), verifies every staged
    path, skips when nothing changed (change detection). With push, commits
    to data/<date>-<phase>-wk<NN>, rebases it on origin/main, pushes it, opens
    a PR, waits for the required checks (bounded) and rebase-merges it. A
    failed check, a timeout or a refused merge leaves the PR open. `landed`,
    when given, receives {"pr", "sha"} once the PR has merged. Without push
    the commit stays on local main and nothing is pushed. `title`,
    `branch_stem` and `intro` replace the run's PR title, branch stem and
    body opening (the manual publish of #616 sets them).
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
    title = title or f"data: pipeline refresh {date.today().isoformat()} ({phase.lower()}, wk {week})"
    msg = (f"{title}\n\n"
           f"{intro} "
           f"(allowlisted data-only commit).\n\n"
           f"Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    data_branch = None
    if push:
        wk = re.sub(r"[^A-Za-z0-9._-]", "", week)
        data_branch = _free_branch(
            branch_stem or f"data/{date.today().isoformat()}-{phase.lower()}-wk{wk}", cwd)
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
               "--body", _pr_body(staged, run_id, rows, intro), cwd=cwd)
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
    plan.pop("riders", None)


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
        changes: dict = {}
        try:
            pg.export_published(published, data, changes)
            if changes:
                plan["column_changes"] = changes
                notes.append("snapshot columns changed (names only): " + "; ".join(
                    f"{t} added {c['added']} dropped {c['dropped']}" for t, c in sorted(changes.items())))
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


def restore_to_head(tables: list[str], cwd: Path = REPO) -> None:
    """Put `tables` back to the published snapshot in the store the run writes:
    the files from git HEAD for parquet, a reload from data/ (which a Postgres
    run leaves equal to HEAD) for the database. Raises when it cannot."""
    if not storage_is_postgres():
        _data_to_head(tables, cwd)
        return
    import etl_storage_pg as pg
    url = os.environ.get(pg.URL_ENV)
    if not url:
        raise RuntimeError(f"{pg.URL_ENV} is not set")
    moved = _dirty_data(tables, cwd)
    if moved:
        raise RuntimeError(f"{moved} file(s) under data/ differ from HEAD; the snapshot to reload from is not clean")
    loaded = pg.reload_snapshot(url, tables, cwd / "data")
    if loaded.problems:
        raise RuntimeError(loaded.problems[0])


GSIS_CHAIN = "nflverse"


def hold_chain(plan: dict, chain: str, reason: str, chains: dict[str, list[str]]) -> None:
    """Hold a Chain that had passed: it leaves plan["passed"], its tables go to
    plan["restore"], and so do the riders, which stop publishing with it."""
    riders = set(plan.pop("riders", ()))
    plan["passed"] = [c for c in plan["passed"] if c != chain]
    plan["failed"] = {**plan["failed"], chain: [reason]}
    out = set(chains.get(chain, ())) | riders
    plan["publish"] = sorted(set(plan["publish"]) - out)
    plan["restore"] = sorted(set(plan["restore"]) | out)


def rekey_all_or_nothing(plan: dict, chains: dict[str, list[str]], candidates: list[str],
                         needs: Callable[[list[str]], list[str]],
                         restore: Callable[[list[str]], None],
                         rekey: Callable[[list[str], bool], dict],
                         undo: Callable[[list[str]], None],
                         gate: Callable[[list[str]], list[str]]) -> list[str]:
    """The gsis_id re-key belongs to the nflverse Chain (#639, ADR-0008
    amendment): the link row it publishes and the id change in every published
    table that holds a gsis_id publish together, or none of it does.

    Does nothing unless nflverse is a passing Chain. The targets are the gsis
    tables of the passing Chains (this run's vetted rows) and the `candidates`
    outside them, a Chain that did not run or was held, of which `needs` picks
    those whose PUBLISHED rows hold an old id; each of those goes back to its
    published rows first (`restore`), so a store a failed or `--no-commit` run
    left remapped heals, and no unvetted row rides. `rekey(tables, dry_run)`
    must return the rekey_gsis_tables dict. The dry run decides first: one
    refused table holds nflverse and nothing is written. Then the remap is
    written and `gate` returns the changed tables whose Gate fails; one failure,
    or any step that raises, puts every remapped table back (`undo`) and holds
    nflverse (`hold_chain`). A failing `restore` or `undo` is not caught: the
    run ends as failed. On success the riders move into plan["publish"] and
    plan["riders"]. Returns the riders."""
    if GSIS_CHAIN not in plan["passed"]:
        return []
    passing = [t for c in plan["passed"] for t in chains.get(c, ())]
    written: list[str] = []
    reason = None
    try:
        riders = needs(candidates)
    except Exception as exc:
        return hold_with(plan, chains, f"gsis re-key held: published rows unreadable ({type(exc).__name__})")
    if riders:
        restore(riders)
    targets = sorted(set(passing) | set(riders))
    try:
        dry = rekey(targets, True)
        if dry["refused"]:
            reason = "gsis re-key held: " + "; ".join(sorted(dry["refused"].values()))
        elif dry["changed"]:
            done = rekey(targets, False)
            written = list(done["changed"])
            failing = gate(written)
            if failing:
                reason = f"gsis re-key held: Gate failed on {', '.join(failing)} after the id change"
    except Exception as exc:
        reason = f"gsis re-key held: a step raised ({type(exc).__name__})"
        written = written or targets
    if reason:
        if written:
            undo(written)
        hold_chain(plan, GSIS_CHAIN, reason, chains)
        return []
    rode = [t for t in written if t in riders]
    if rode:
        plan["publish"] = sorted(set(plan["publish"]) | set(rode))
        plan["restore"] = sorted(set(plan["restore"]) - set(rode))
        plan["riders"] = rode
    return rode


def hold_with(plan: dict, chains: dict[str, list[str]], reason: str) -> list[str]:
    hold_chain(plan, GSIS_CHAIN, reason, chains)
    return []


def rekey_report(result: dict) -> None:
    """Print what a `rekey_gsis_tables` call changed, names and counts only."""
    for name in result["changed"]:
        moved = ", ".join(f"{c} {n}" for c, n in result["stats"][name]["changed"].items())
        print(f"[gsis] {name}: old gsis_id put on its newest id ({moved})")


def rekey_gsis_links(plan: dict, chains: dict[str, list[str]], accept_shrink: list[str],
                     read_from: dict) -> None:
    """#639: `rekey_all_or_nothing` over the real store. Not caught here: a
    restore or an undo that fails ends the run as failed, its notice sent."""
    if GSIS_CHAIN not in plan["passed"]:
        print(f"[gsis] {GSIS_CHAIN} did not pass: no gsis_id is re-keyed from this run's links")
        return
    chain_of = {t: c for c, ts in chains.items() for t in ts}
    listed = [t for t in etl_helpers.gsis_id_tables()
              if chain_of.get(t) and chain_of[t] not in plan["passed"]]
    tracked = tracked_at_head(listed) if listed else set()
    candidates = [t for t in listed if f"data/{t}.parquet" in tracked]
    old = (set(etl_helpers.read_table(etl_helpers.GSIS_LINK_TABLE)["old_gsis_id"])
           if etl_helpers.table_exists(etl_helpers.GSIS_LINK_TABLE) else set())
    saved: dict = {}

    def needs(tables):
        if storage_is_postgres():
            if _dirty_data(tables, REPO):
                raise RuntimeError("data/ differs from HEAD; the published rows are not clean")
        else:
            _data_to_head(tables, REPO)
        out = []
        for t in tables:
            ids = etl_helpers.read_stored(t, REPO / "data")["gsis_id"].dropna()
            if old & set(ids):
                out.append(t)
        return out

    def rekey(tables, dry_run):
        done = etl_helpers.rekey_gsis_tables(only=tables, dry_run=dry_run, undo=saved)
        if not dry_run:
            rekey_report(done)
        return done

    def undo(tables):
        for t in tables:
            if t in saved:
                etl_helpers.write_table(t, saved[t])

    def gate(tables):
        suite = etl_checks.run_suite(tables, accept_shrink, **read_from)
        return sorted({r.table for r in suite if r.tier == "gate" and not r.ok})

    riders = rekey_all_or_nothing(plan, chains, candidates, needs, restore_to_head, rekey, undo, gate)
    if riders:
        print(f"[chain] riders: {', '.join(riders)} publish with the {GSIS_CHAIN} re-key")
    elif GSIS_CHAIN not in plan["passed"]:
        print(f"[chain] {GSIS_CHAIN}: HELD — {'; '.join(plan['failed'][GSIS_CHAIN])}")


def tracked_at_head(tables: list[str], cwd: Path = REPO) -> set[str]:
    """The `data/<table>.parquet` paths of `tables` that HEAD holds. Raises
    when git cannot say, so a git error never reads as tracked."""
    r = _git("ls-tree", "--name-only", "HEAD", "--", *_parquet_paths(tables), cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError("git could not list data/ at HEAD")
    return set(r.stdout.split())


def manual_refusals(names: list[str], registry: dict[str, dict], tracked: set[str]) -> list[str]:
    """The allowlist of --publish-manual (#616): one line per named table that
    may not go by it. A table passes only when docs/data_model.yml declares it
    with no `chain:`, it is published (not private), and HEAD already tracks
    its snapshot. Pure: reads no store and no file."""
    out = []
    for name in names:
        entry = registry.get(name)
        if entry is None:
            out.append(f"{name}: not declared in docs/data_model.yml")
        elif entry.get("chain"):
            out.append(f"{name}: in Chain {entry['chain']}, which publishes it")
        elif etl_helpers.is_private(entry):
            out.append(f"{name}: private, never published")
        elif f"data/{name}.parquet" not in tracked:
            out.append(f"{name}: no snapshot tracked at HEAD (a new table goes by its own PR)")
    return out


def manual_preflight(names: list[str], cwd: Path = REPO) -> list[str]:
    """The checkout checks of --publish-manual (#616, PR #669 review), made
    before any read: the checkout is on main, and the index holds no staged
    path but the named tables' own, since commit_data commits all it finds
    staged and a staged Chain table would land unchecked. Raises when git
    cannot say."""
    out = []
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
    if branch.returncode != 0:
        raise RuntimeError("git could not read the current branch")
    if branch.stdout.strip() != "main":
        out.append(f"on branch '{branch.stdout.strip()}', not main")
    staged = _git("diff", "--cached", "--name-only", cwd=cwd)
    if staged.returncode != 0:
        raise RuntimeError("git could not read the index")
    named = set(_parquet_paths(names))
    others = sorted(p for p in staged.stdout.splitlines() if p and p not in named)
    if others:
        out.append(f"the index holds staged path(s) that are not named tables: {', '.join(others)}")
    return out


def publish_manual(names: list[str], accepted_shrink: list[str], push: bool, dry_run: bool,
                   cwd: Path = REPO) -> int:
    """--publish-manual (#616, ADR-0008 decision 3): the owner's command to
    publish named manual-only tables. Refuses, before any read, a table off
    the allowlist (`manual_refusals`), a checkout off main or with other
    staged paths (`manual_preflight`), or a store that is not Postgres. Then,
    read-only, runs the tables' Gate checks against the store and exports
    them to data/, and lands them by commit_data, the data PR of a Chain
    publish. Runs no step and signs in nowhere. Exit 0 published or nothing
    changed, 1 failed, 2 refused. Prints table names and counts only."""
    names = list(dict.fromkeys(names))
    refused = manual_refusals(names, etl_checks.load_registry(), tracked_at_head(names, cwd))
    refused += manual_preflight(names, cwd)
    for line in refused:
        print(f"refused: {line}")
    if refused:
        return 2
    if dry_run:
        print(f"[dry run] would publish {len(names)} manual-only table(s): {', '.join(names)}")
        if not storage_is_postgres():
            print("[dry run] a real run refuses: ETL_STORAGE is not postgres")
        return 0
    import etl_storage_pg as pg
    if not storage_is_postgres():
        print("refused: ETL_STORAGE is not postgres; the store is the source of a manual publish")
        return 2
    if not os.environ.get(pg.URL_ENV):
        print(f"refused: {pg.URL_ENV} is not set")
        return 2
    runlog = etl_run_log.RunLog("manual")
    runlog.start(etl_run_log.head_sha(cwd))
    rows, changes, landed = None, {}, {}
    try:
        with pg.session_read_only():
            suite = etl_checks.run_suite(names, accepted_shrink, data_dir=None)
        for r in suite:
            if not r.ok:
                mark = "FAIL" if r.tier == "gate" else "FIND"
                print(f"[{mark}] {r.tier:6} {r.check:15} {r.table}"
                      + (f" — {r.detail}" if r.detail else ""))
        gate_fail = [r for r in suite if r.tier == "gate" and not r.ok]
        if gate_fail:
            line = ("ABORTED: Gate failed, nothing exported: "
                    + "; ".join(f"{g.check} {g.table}" for g in gate_fail))
        else:
            try:
                with pg.session_read_only():
                    rows = pg.export_published(names, cwd / "data", changes)
                line = None
            except Exception as exc:
                rows = None
                _data_to_head(names, cwd)
                line = f"ABORTED: export failed: {pg.describe(exc)}"
            if line is None:
                today = date.today().isoformat()
                line = commit_data("MANUAL", "", push=push, publish=names, restore=[], cwd=cwd,
                                   run_id=runlog.run_id, rows=rows, landed=landed,
                                   title=f"data: manual publish {today} ({', '.join(names)})",
                                   branch_stem=f"data/{today}-manual", intro=MANUAL_INTRO)
        code = 1 if line.startswith("ABORTED") else 0
        runlog.finish(
            etl_run_log.final_status(code, line),
            snapshot_commit_sha=(landed.get("sha") if etl_run_log.data_merged(line)
                                 else etl_run_log.head_sha(cwd)
                                 if etl_run_log.data_committed(line) else None),
            rows_written=rows, error=line if code else None,
            column_changes=changes or None)
    except BaseException as exc:
        runlog.finish("failed", error=f"{type(exc).__name__} raised before the manual publish finished")
        raise
    print(f"[info] {line}")
    return code


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
        print(f"[warn] webhook failed: {type(e).__name__}")


CONTRACT_TABLE = "fact_contract_move"
CONTRACT_WEBHOOK_ENV = "DISCORD_WEBHOOK_URL_ADMIN"
CONTRACT_FORMATTER = REPO / "discord_bot" / "contract_moves.py"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CONTRACT_FMT = None


def contract_formatter():
    """The bot's xlsx formatter, loaded by file path: discord_bot/ has no
    package and its sibling names (config, cap, render) would shadow others.
    The file imports only pandas and openpyxl, so the ETL environment has all
    it needs. Cached."""
    global _CONTRACT_FMT
    if _CONTRACT_FMT is None:
        spec = importlib.util.spec_from_file_location("contract_moves_formatter", CONTRACT_FORMATTER)
        _CONTRACT_FMT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_CONTRACT_FMT)
    return _CONTRACT_FMT


def contract_webhook(env_file: Path | None = None) -> str | None:
    """The admin webhook: the environment variable, else the repo .env, as
    notify() does. The runner has no .env and gets the secret in its environment;
    the PC task has the .env and no variable."""
    url = os.environ.get(CONTRACT_WEBHOOK_ENV)
    if not url:
        url = etl_run_log.env_value(CONTRACT_WEBHOOK_ENV, REPO / ".env" if env_file is None else env_file)
    return url


def read_contract_list(data_dir: Path | None = None):
    """The published snapshot of the contract lists. A table with no file is the
    first run: an empty list. Any other failure is None, which skips the post
    instead of reading as an empty list and posting every row."""
    try:
        return etl_helpers.read_stored(CONTRACT_TABLE, data_dir=etl_helpers.DATA if data_dir is None else data_dir)
    except etl_helpers.TableNotFound:
        return etl_contract_moves.empty()
    except Exception as exc:
        print(f"[warn] {CONTRACT_TABLE} could not be read ({type(exc).__name__}); "
              f"the contract-moves post is skipped")
        return None


def read_team_names(data_dir: Path | None = None):
    """team_key and team_name for the xlsx; None when the table cannot be read,
    and the file then shows team keys."""
    try:
        return etl_helpers.read_stored("dim_fantasy_teams", data_dir=etl_helpers.DATA if data_dir is None else data_dir)
    except Exception:
        return None


def send_webhook_file(url: str, content: str, filename: str, data: bytes) -> None:
    """One plain multipart post: a message and one file, no mention allowed.
    Raises on any failure; the caller logs the exception type and none of its
    text, which can hold part of the URL."""
    boundary = uuid.uuid4().hex
    payload = json.dumps({"content": content[:1900], "allowed_mentions": {"parse": []},
                          "attachments": [{"id": 0, "filename": filename}]})
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
        f"Content-Type: application/json\r\n\r\n{payload}\r\n".encode("utf-8"),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; "
        f"filename=\"{filename}\"\r\nContent-Type: {XLSX_TYPE}\r\n\r\n".encode("utf-8"),
        data,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    req = urllib.request.Request(
        url, data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "DiscordBot (https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball, 1.0)"})
    urllib.request.urlopen(req, timeout=30)


def contract_post_text(current, new: set) -> str:
    """A short, counts-only message: no team and no player in the text."""
    fmt = contract_formatter()
    keyed = current.assign(_key=list(map(tuple, current[etl_contract_moves.CHANGE_KEY].astype(str).to_numpy())))
    rows = keyed[keyed["_key"].isin(new)]
    by_status = " · ".join(f"{n} {s.lower()}" for s, n in rows["status"].value_counts().items())
    by_list = " · ".join(f"{fmt.LIST_LABELS.get(n, n)} {c}" for n, c in rows["list_name"].value_counts().items())
    return (f"**Contract moves**: {len(rows)} new on the commissioners' lists ({by_status}). "
            f"{by_list}. The full list is attached; `/contract-moves` shows it any time.")


def contract_post_due(dry_run: bool, no_commit: bool, commit_line: str) -> bool:
    """Good for this table: no flag that stops short of publishing and the data
    PR merged. The run's exit code is not part of it (ADR-0008: the publish unit
    is a Chain, so another Chain failing must not freeze this table's post).
    That the table itself was published this run is main()'s guard: the
    after-list is read only when it is in the publish plan, and without it
    post_contract_moves posts nothing."""
    return not dry_run and not no_commit and etl_run_log.data_merged(commit_line)


def post_contract_moves(previous, current, teams, webhook: str | None, sender=send_webhook_file,
                        today: date | None = None) -> str:
    """After a good run: post the xlsx and a short message to the admin webhook
    only when a row is new by the change key (list, conference, team, player,
    status) against the list the previous good run published. No state file: the
    next run's previous list already holds these rows, so a failed post is not
    retried until the list gains a row. Never raises; returns one line to log."""
    try:
        if previous is None or current is None:
            return "contract-moves post skipped: no list to compare (not published this run, or not readable)"
        if current.empty:
            return "contract-moves post: nothing due, no post"
        new = etl_contract_moves.new_keys(current, previous)
        if not new:
            return "contract-moves post: no new row, no post"
        if not webhook:
            return f"contract-moves post skipped: {CONTRACT_WEBHOOK_ENV} is not set ({len(new)} new row(s))"
        fmt = contract_formatter()
        if teams is None:
            keys = current["team_key"].astype(str).unique()
            teams = pd.DataFrame({"team_key": keys, "team_name": keys})
        data = fmt.xlsx_bytes(fmt.prepare(current, teams))
        name = f"contract-moves-{(today or league_today()).isoformat()}.xlsx"
        sender(webhook, contract_post_text(current, new), name, data)
        return f"contract-moves post sent: {len(new)} new row(s)"
    except Exception as exc:
        return f"[warn] contract-moves post failed, not retried: {type(exc).__name__}"


def terms_line() -> str:
    try:
        import check_sources
        n = check_sources.terms_due_count(check_sources.load_yaml())
    except Exception:
        return "📜 Terms checks due: unavailable (docs/sources.yml could not be read)"
    return f"📜 Terms checks due: {n}"


def summarize(phase: str, week: str, results: list[dict], reviews: dict,
              commit_line: str, plan: dict | None = None,
              filed: dict | None = None, cadence: dict | None = None,
              access: dict | None = None) -> str:
    lines = [f"**Pipeline {date.today().isoformat()}** — phase {phase}, week {week}"]
    if cadence:
        lines.append(f"🗓️ {cadence_line(cadence)}")
        if cadence_warning(cadence):
            lines.append(cadence_warning(cadence))
    for r in results:
        mark = {"ok": "✅", "dry-run": "▫️", "skipped": "⏭️"}.get(r["status"], "❌")
        lines.append(f"{mark} {r['name']}" + (f" — {r['detail']}" if r["detail"] else ""))
    if access:
        mark = {"ok": "✅", "dry-run": "▫️"}.get(access["status"], "❌")
        lines.append(f"{mark} {access['name']} (no Chain: a failure here holds no data Chain)")
        lines += [("⚠️ " if "CHANGED" in d else "   ") + d for d in access["detail"].splitlines()]
    if plan:
        lines.append("**Chains:**")
        lines += [f"✅ {c}: " + ("passed, not published" if c in plan.get("unpublished", ()) else "published")
                  for c in plan["passed"]]
        lines += [f"🛑 {c}: held at HEAD — {'; '.join(w)[:300]}"
                  for c, w in plan["failed"].items()]
        if plan.get("riders"):
            lines.append(f"♻️ gsis ids put on their newest id and published outside their Chain: "
                         f"{', '.join(plan['riders'])}")
        lines += [f"♻️ {n}" for n in plan.get("notes", [])]
    if filed:
        lines.append(f"🔎 Review findings: {filed['open']} open "
                     f"({filed['opened']} new, {filed['cleared']} cleared)")
    pending = {f: v for f, v in reviews.items() if v["rows"] > 0}
    if pending:
        lines.append("**Review queues:**")
        lines += [f"• {f}: {v['rows']} rows → {v['action']}" for f, v in pending.items()]
    lines.append(terms_line())
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
    ap.add_argument("--publish-manual", nargs="+", metavar="TABLE",
                    help="the owner's command only (#616): export the named manual-only "
                         "tables from the store and land them by the data PR; no steps")
    args = ap.parse_args()

    print(f"storage: {resolve_storage_env()}")

    if args.publish_manual:
        clash = [flag for flag, on in (("--steps", args.steps), ("--group", args.group),
                                       ("--profile", args.profile), ("--check-only", args.check_only),
                                       ("--no-commit", args.no_commit)) if on]
        if clash:
            print(f"refused: --publish-manual runs no steps; drop {', '.join(clash)}")
            return 2
        return publish_manual(args.publish_manual, args.accept_shrink,
                              push=not args.no_push, dry_run=args.dry_run)

    if args.check_only:
        return check_only(args.accept_shrink)

    runlog = etl_run_log.RunLog(args.trigger)
    session = None if args.dry_run else open_fantrax_session()
    logins: list[str] = []
    blocked: list[str] = []
    contract_before = contract_after = None
    access = None
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
        if not args.dry_run and not args.no_commit:
            contract_before = read_contract_list()
        results = run_steps(steps, phase, only, args.dry_run, groups)
        access = run_access_loads(args.dry_run, args.no_commit, only, groups)
        logins = fantrax_logins(session)
        blocked = fantrax_blocked(session)
        if session:
            print(f"[info] fantrax logins: {len(logins)}"
                  f"{' (' + ', '.join(logins) + ')' if logins else ''}")
        if blocked:
            print(f"[info] fantrax login cap reached, blocked: {', '.join(blocked)}")

        plan, filed = None, None
        if not args.dry_run:
            # Gate every table of each Chain that had a step run this phase.
            chains = etl_checks.chain_tables(etl_checks.load_registry())
            ran = {s["chain"] for s in steps if s["name"] in {r["name"] for r in results}}
            # data_dir=None: under Postgres the Gates read the database.
            read_from = {"data_dir": None} if storage_is_postgres() else {}
            ran_tables = [t for c in ran for t in chains.get(c, [])]
            suite = etl_checks.run_suite(ran_tables, args.accept_shrink, **read_from)
            plan = plan_publish(steps, results, suite, chains)
            for c in plan["passed"]:
                print(f"[chain] {c}: pass")
            for c, w in plan["failed"].items():
                print(f"[chain] {c}: HELD — {'; '.join(w)}")
            # #639: the gsis_id re-key is the nflverse Chain's and is all or
            # nothing. Nothing publishes under --no-commit, and a held Chain's
            # output stays on disk for inspection, so it does not run there.
            if not args.no_commit:
                rekey_gsis_links(plan, chains, args.accept_shrink, read_from)
            # File only what publishes: a held Chain's tables revert to HEAD.
            # A rider's rows are its published rows, whose findings were filed
            # when they published, and the results here were computed on the
            # held run's unvetted rows (ADR-0008 amendment, #639).
            riders = set(plan.get("riders", ()))
            filed = etl_checks.file_review(
                [r for r in suite if r.table in plan["publish"] and r.table not in riders],
                run_id=_run_id())

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
                if CONTRACT_TABLE in plan["publish"]:
                    contract_after = read_contract_list()
            commit_line = aborted or commit_data(phase, week, push=not args.no_push,
                                                 publish=plan["publish"], restore=plan["restore"],
                                                 run_id=runlog.run_id, rows=rows, landed=landed)
        print(f"[info] {commit_line}")

        failed = bool(plan and plan["failed"]) or any(
            r["status"] not in ("ok", "dry-run") for r in results) or bool(
            access and access["status"] == "failed")
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
                error=(etl_run_log.failure_summary(results, plan, commit_line, blocked, access)
                       if code else None),
                cadence=cadence,
                column_changes=(plan or {}).get("column_changes")
                if not commit_line.startswith("ABORTED") else None,
                fantrax_logins=len(logins))
    except BaseException as exc:
        runlog.finish("failed", error=f"{type(exc).__name__} raised before the run finished",
                      fantrax_logins=len(fantrax_logins(session)) if session else None)
        if runlog.warning and not args.dry_run:
            notify(f"{runlog.warning}\nThe pipeline raised {type(exc).__name__} before it finished.")
        raise
    finally:
        close_fantrax_session(session)

    summary = summarize(phase, week, results, reviews, commit_line, plan, filed, cadence, access)
    if blocked:
        summary = (f"⚠️ Fantrax login cap reached: {len(blocked)} step(s) blocked "
                   f"({', '.join(blocked)}); they catch up at the next run.\n{summary}")
    elif len(logins) > 1:
        summary = f"⚠️ {len(logins)} Fantrax logins in this run; one is expected.\n{summary}"
    if runlog.warning:
        summary = f"{runlog.warning}\n{summary}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pipeline_summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    if not args.dry_run:
        notify(summary)
    if contract_post_due(args.dry_run, args.no_commit, commit_line):
        print(post_contract_moves(contract_before, contract_after, read_team_names(),
                                  contract_webhook()))

    return code


if __name__ == "__main__":
    sys.exit(main())
