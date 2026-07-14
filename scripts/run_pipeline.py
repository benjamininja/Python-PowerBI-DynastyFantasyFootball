"""Weekly ETL orchestrator — phase-aware, Task Scheduler entrypoint.

Runs the scheduled slice of the pipeline in dependency order, surfaces
review-queue counts, commits refreshed data (allowlisted `data/*.parquet`
ONLY — the codified exception to the never-commit-to-main rule; see
CONTRIBUTING.md), and notifies a private Discord channel via webhook.

Phase model (derived from 04a's week label + the season calendar):
  INSEASON   week label != PRE and the NFL season hasn't ended
  PRESEASON  week label == PRE, within ~45 days of Week-1 Thursday
  OFFSEASON  everything else (fixes the "February clamps to week 18" edge:
             derive_week_label alone would keep saying 18 forever)

NOT scheduled, by design: live-draft chain (04w -> 02d -> 02e -> 05a), the
03-group rookie chain (manual Excel gates), review applies (03z,
apply_fantrax_crosswalk_review), and `04v --apply` (write-side; opt-in only).

Run:  .\\run_weekly.ps1            (Task Scheduler wrapper, logs console)
      .\\run.ps1 scripts\\run_pipeline.py --dry-run --phase OFFSEASON
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
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENV_PY = REPO / ".venv" / "Scripts" / "python.exe"
NB = REPO / "notebooks"
OUT_DIR = REPO / "data" / "outputs"
STEP_TIMEOUT_S = 1800

# Review queues surfaced (never blocking): file -> the action that drains it.
REVIEW_QUEUES = {
    "review_fuzzy_matches.csv": "run 03z_apply_fuzzy_review",
    "review_fantrax_crosswalk.csv": "run scripts/apply_fantrax_crosswalk_review.py",
    "review_dynasty_crosswalk.csv": "manual (no apply script exists yet)",
    "review_contract_actions.csv": "run 04v --dry-run then --apply (attended)",
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


# Step table: name -> (cmd, phases it runs in, upstream deps that must succeed).
# Order matters (sequential execution).
def build_steps(profile: str | None) -> list[dict]:
    steps = [
        {"name": "01f_dim_season", "cmd": _nbconvert("01f_dim_season_seed.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": []},
        {"name": "01e_dim_nfl_players", "cmd": _nbconvert("01e_dim_nfl_players_seed.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": []},
        {"name": "04a_scrape", "cmd": _script("04a_fantrax_weekly_scrape.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": []},
        {"name": "04z_crosswalk", "cmd": _nbconvert("04z_fantrax_crosswalk.ipynb"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04a_scrape"]},
        {"name": "04a_backfill_gp", "cmd": _script("04a_fantrax_weekly_scrape.py", "--backfill-gp"),
         "phases": {"INSEASON"}, "needs": ["04a_scrape"]},
        {"name": "04v_minor_contracts", "cmd": _script("04v_minor_contracts.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04z_crosswalk"]},
        {"name": "02d_ledger", "cmd": _script("02d_fact_roster_transactions.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04v_minor_contracts"]},
        {"name": "02e_derive", "cmd": _script("02e_fact_fantasy_teams_derive.py"),
         "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["02d_ledger"]},
        {"name": "04b_ktc_dynasty", "cmd": _nbconvert("04b_ktc_dynasty_rankings.ipynb"),
         "phases": {"OFFSEASON"}, "needs": []},
    ]
    if profile == "dynasty":
        # After the user refreshes the 04x manual Excel. 04b re-runs even if
        # the phase already included it (idempotent).
        steps += [
            {"name": "04b_ktc_dynasty_p", "cmd": _nbconvert("04b_ktc_dynasty_rankings.ipynb"),
             "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": []},
            {"name": "04c_dim_dynasty_metric", "cmd": _nbconvert("04c_dim_dynasty_metric.ipynb"),
             "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04b_ktc_dynasty_p"]},
            {"name": "04y_composite", "cmd": _nbconvert("04y_composite_dynasty_metrics.ipynb"),
             "phases": {"INSEASON", "PRESEASON", "OFFSEASON"}, "needs": ["04c_dim_dynasty_metric"]},
        ]
    return steps


def run_steps(steps: list[dict], phase: str, only: set[str] | None,
              dry_run: bool) -> list[dict]:
    results = []
    status = {}   # name -> ok|failed|skipped
    env = {**os.environ, "PYTHONUTF8": "1"}
    for s in steps:
        name = s["name"]
        if phase not in s["phases"] or (only and name not in only):
            continue
        bad_dep = next((d for d in s["needs"] if status.get(d) in ("failed", "skipped")), None)
        if bad_dep:
            status[name] = "skipped"
            results.append({"name": name, "status": "skipped",
                            "detail": f"upstream {bad_dep} did not succeed"})
            print(f"[skip] {name} (needs {bad_dep})")
            continue
        print(f"[step] {name}: {' '.join(s['cmd'][1:])}")
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


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def commit_data(phase: str, week: str, push: bool) -> str:
    """Allowlisted direct-to-main data commit. Stages data/*.parquet ONLY,
    verifies every staged path, skips when nothing changed (change detection),
    rebases on origin before pushing. Returns a one-line outcome."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        return f"commit skipped: on branch '{branch}', not main"
    _git("add", "--", "data/*.parquet")
    staged = [l for l in _git("diff", "--cached", "--name-only").stdout.splitlines() if l]
    if not staged:
        return "no data changes — commit skipped"
    bad = [p for p in staged if not re.fullmatch(r"data/[^/]+\.parquet", p)]
    if bad:
        _git("reset")
        return f"ABORTED: non-allowlisted staged path(s): {bad}"
    msg = (f"data: pipeline refresh {date.today().isoformat()} "
           f"({phase.lower()}, wk {week})\n\n"
           f"Machine-generated parquet refresh via scripts/run_pipeline.py "
           f"(allowlisted data-only commit).\n\n"
           f"Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    c = _git("commit", "-m", msg)
    if c.returncode != 0:
        return f"ABORTED: commit failed: {c.stderr.strip()[:200]}"
    if not push:
        return f"committed {len(staged)} file(s), push skipped (--no-push)"
    # autostash: nbconvert --inplace leaves executed .ipynb files dirty in the
    # working tree, which would otherwise block the rebase.
    r = _git("-c", "rebase.autostash=true", "pull", "--rebase", "origin", "main")
    if r.returncode != 0:
        _git("rebase", "--abort")
        return f"ABORTED: rebase conflict — resolve manually: {r.stderr.strip()[:200]}"
    p = _git("push", "origin", "main")
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
              commit_line: str) -> str:
    lines = [f"**Pipeline {date.today().isoformat()}** — phase {phase}, week {week}"]
    for r in results:
        mark = {"ok": "✅", "dry-run": "▫️", "skipped": "⏭️"}.get(r["status"], "❌")
        lines.append(f"{mark} {r['name']}" + (f" — {r['detail']}" if r["detail"] else ""))
    pending = {f: v for f, v in reviews.items() if v["rows"] > 0}
    if pending:
        lines.append("**Review queues:**")
        lines += [f"• {f}: {v['rows']} rows → {v['action']}" for f, v in pending.items()]
    lines.append(f"📦 {commit_line}")
    return "\n".join(lines)


def main() -> int:
    # Console may be cp1252 (bare python.exe outside run_weekly.ps1's
    # PYTHONUTF8): keep the summary's emoji from crashing the print.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Phase-aware weekly ETL pipeline")
    ap.add_argument("--phase", choices=["INSEASON", "PRESEASON", "OFFSEASON"],
                    help="override phase derivation (testing)")
    ap.add_argument("--steps", help="comma-separated step names to run (subset)")
    ap.add_argument("--profile", choices=["dynasty"],
                    help="extra chain: dynasty = 04b -> 04c -> 04y "
                         "(run after refreshing the 04x manual Excel)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the step plan, execute nothing, commit nothing")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()

    phase = args.phase or derive_phase()
    week = _load_04a().derive_week_label(_load_04a().CFG)
    print(f"[info] phase={phase} week={week} "
          f"{'[DRY RUN]' if args.dry_run else ''}")

    steps = build_steps(args.profile)
    only = set(args.steps.split(",")) if args.steps else None
    results = run_steps(steps, phase, only, args.dry_run)

    reviews = review_counts()
    if args.dry_run or args.no_commit:
        commit_line = "commit skipped (flag)"
    else:
        commit_line = commit_data(phase, week, push=not args.no_push)
    print(f"[info] {commit_line}")

    summary = summarize(phase, week, results, reviews, commit_line)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "pipeline_summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    if not args.dry_run:
        notify(summary)

    failed = any(r["status"] not in ("ok", "dry-run") for r in results)
    return 1 if failed or commit_line.startswith("ABORTED") else 0


if __name__ == "__main__":
    sys.exit(main())
