"""Weekly ETL orchestrator — phase-aware, Task Scheduler entrypoint.

Runs the scheduled slice of the pipeline in dependency order, gates each
Chain, surfaces review-queue counts, commits the passing Chains' refreshed
data (allowlisted `data/*.parquet` ONLY — the codified exception to the
never-commit-to-main rule; see CONTRIBUTING.md), and notifies a private
Discord channel via webhook.

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
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
NB = REPO / "notebooks"
OUT_DIR = REPO / "data" / "outputs"
STEP_TIMEOUT_S = 1800

sys.path.insert(0, str(NB))
import etl_checks  # noqa: E402  (notebooks/ on the path, like the notebooks do)

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
        ds = pd.read_parquet(REPO / "data" / "dim_season.parquet")
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
        {"name": "04a_scrape", "cmd": _script("04a_fantrax_weekly_scrape.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": [], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04z_crosswalk", "cmd": _nbconvert("04z_fantrax_crosswalk.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04a_scrape"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04a_backfill_gp", "cmd": _script("04a_fantrax_weekly_scrape.py", "--backfill-gp"),
         "phases": {"INSEASON"}, "needs": ["04a_scrape"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "04v_minor_contracts", "cmd": _script("04v_minor_contracts.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04z_crosswalk"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "02d_ledger", "cmd": _script("02d_fact_roster_transactions.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04v_minor_contracts"], "chain": "fantrax_core", "group": "regular_season"},
        {"name": "02e_derive", "cmd": _script("02e_fact_fantasy_teams_derive.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["02d_ledger"], "chain": "fantrax_core", "group": "regular_season"},
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
    return steps


def run_steps(steps: list[dict], phase: str, only: set[str] | None,
              dry_run: bool, groups: set[str] | None = None) -> list[dict]:
    results = []
    status = {}   # name -> ok|failed|skipped
    env = {**os.environ, "PYTHONUTF8": "1"}
    for s in steps:
        name = s["name"]
        if phase not in s["phases"] or (only and name not in only):
            continue
        if groups and s.get("group") not in groups:
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


def commit_data(phase: str, week: str, push: bool, publish: list[str],
                restore: list[str], cwd: Path = REPO) -> str:
    """Allowlisted direct-to-main data commit, per Chain. Restores the failed
    Chains' tracked parquet from HEAD, stages exactly the passing Chains'
    tracked parquet (never a glob), verifies every staged path, skips when
    nothing changed (change detection), rebases on origin before pushing.
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
    msg = (f"data: pipeline refresh {date.today().isoformat()} "
           f"({phase.lower()}, wk {week})\n\n"
           f"Machine-generated parquet refresh via scripts/run_pipeline.py "
           f"(allowlisted data-only commit).\n\n"
           f"Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    c = _git("commit", "-m", msg, cwd=cwd)
    if c.returncode != 0:
        return f"ABORTED: commit failed: {c.stderr.strip()[:200]}"
    if not push:
        return f"committed {len(staged)} file(s), push skipped (--no-push)"
    # autostash: nbconvert --inplace leaves executed .ipynb files dirty in the
    # working tree, which would otherwise block the rebase.
    r = _git("-c", "rebase.autostash=true", "pull", "--rebase", "origin", "main", cwd=cwd)
    if r.returncode != 0:
        _git("rebase", "--abort", cwd=cwd)
        return f"ABORTED: rebase conflict — resolve manually: {r.stderr.strip()[:200]}"
    p = _git("push", "origin", "main", cwd=cwd)
    if p.returncode != 0:
        return f"ABORTED: push failed: {p.stderr.strip()[:200]}"
    return f"committed + pushed {len(staged)} parquet file(s) to main"


def notify(text: str) -> None:
    """Discord webhook (DISCORD_WEBHOOK_URL in .env / env). Never raises."""
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        env_file = REPO / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("DISCORD_WEBHOOK_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
                    break
    if not url:
        print("[info] no DISCORD_WEBHOOK_URL — notification skipped")
        return
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"content": text[:1900]}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15)
        print("[ok] Discord notification sent")
    except Exception as e:
        print(f"[warn] webhook failed: {e}")


def summarize(phase: str, week: str, results: list[dict], reviews: dict,
              commit_line: str, plan: dict | None = None,
              filed: dict | None = None) -> str:
    lines = [f"**Pipeline {date.today().isoformat()}** — phase {phase}, week {week}"]
    for r in results:
        mark = {"ok": "✅", "dry-run": "▫️", "skipped": "⏭️"}.get(r["status"], "❌")
        lines.append(f"{mark} {r['name']}" + (f" — {r['detail']}" if r["detail"] else ""))
    if plan:
        lines.append("**Chains:**")
        lines += [f"✅ {c}: published" for c in plan["passed"]]
        lines += [f"🛑 {c}: held at HEAD — {'; '.join(w)[:300]}"
                  for c, w in plan["failed"].items()]
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
    args = ap.parse_args()

    if args.check_only:
        return check_only(args.accept_shrink)

    phase = args.phase or derive_phase()
    week = _load_04a().derive_week_label(_load_04a().CFG)
    print(f"[info] phase={phase} week={week} "
          f"{'[DRY RUN]' if args.dry_run else ''}")

    steps = build_steps(args.profile)
    only = set(args.steps.split(",")) if args.steps else None
    groups = set(args.group.split(",")) if args.group else None
    results = run_steps(steps, phase, only, args.dry_run, groups)

    plan, filed = None, None
    if not args.dry_run:
        # Gate every table of each Chain that had a step run this phase.
        chains = etl_checks.chain_tables(etl_checks.load_registry())
        ran = {s["chain"] for s in steps if s["name"] in {r["name"] for r in results}}
        suite = etl_checks.run_suite([t for c in ran for t in chains.get(c, [])],
                                     args.accept_shrink)
        plan = plan_publish(steps, results, suite, chains)
        for c in plan["passed"]:
            print(f"[chain] {c}: pass")
        for c, w in plan["failed"].items():
            print(f"[chain] {c}: HELD — {'; '.join(w)}")
        # File only what publishes: a held Chain's tables revert to HEAD.
        filed = etl_checks.file_review(
            [r for r in suite if r.table in plan["publish"]], run_id=_run_id())

    reviews = review_counts()
    if args.dry_run or args.no_commit:
        commit_line = "commit skipped (flag)"
    else:
        commit_line = commit_data(phase, week, push=not args.no_push,
                                  publish=plan["publish"], restore=plan["restore"])
    print(f"[info] {commit_line}")

    summary = summarize(phase, week, results, reviews, commit_line, plan, filed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pipeline_summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    if not args.dry_run:
        notify(summary)

    failed = bool(plan and plan["failed"]) or any(
        r["status"] not in ("ok", "dry-run") for r in results)
    return 1 if failed or commit_line.startswith("ABORTED") else 0


if __name__ == "__main__":
    sys.exit(main())
