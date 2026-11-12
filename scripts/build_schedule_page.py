"""Writes docs/site/pages/refresh-schedule.md from the runner's own step list.

Reads build_steps (phases, cadence) from scripts/run_pipeline.py, the stage
text in docs/site/stages.yml, the source names in docs/sources.yml and the
Scoring Periods in the published data/dim_scoring_period.parquet. Reading is
parquet only: no database, no .env, no step is run (#380).

Run before the site build:  python scripts/build_schedule_page.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "site" / "pages" / "refresh-schedule.md"
STAGES = REPO / "docs" / "site" / "stages.yml"
SOURCES = REPO / "docs" / "sources.yml"
GITHUB = "https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/blob/main"
ALL_PHASES = ("INSEASON", "PRESEASON", "OFFSEASON")
LOGIN_PREFIXES = ("04a_", "04s_", "04t_", "04v_", "04w_")
RUNNER = "PC daily task (Actions with #93)"
CLOSE_DAYS_SHOWN = 3
ONE_DAY = timedelta(days=1)


def load_run_pipeline():
    os.environ["ETL_STORAGE"] = "parquet"
    for p in (REPO / "notebooks", REPO / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import run_pipeline
    return run_pipeline


def script_file(step: dict) -> str:
    return next(Path(c).name for c in step["cmd"] if str(c).endswith((".py", ".ipynb")))


def needs_login(step: dict) -> bool:
    return script_file(step).startswith(LOGIN_PREFIXES)


def phase_text(step: dict) -> str:
    phases = step["phases"]
    return "all" if set(ALL_PHASES) <= set(phases) else ", ".join(p for p in ALL_PHASES if p in phases)


def next_close_days(periods: pd.DataFrame | None, today: date, weekday: int,
                    n: int = CLOSE_DAYS_SHOWN) -> list[date]:
    days: list[date] = []
    last = today - ONE_DAY
    if periods is not None and len(periods):
        days = sorted({pd.Timestamp(e).date() + ONE_DAY for e in periods["end_date"]
                       if pd.Timestamp(e).date() + ONE_DAY >= today})[:n]
        last = max([last] + days + [pd.Timestamp(e).date() + ONE_DAY for e in periods["end_date"]])
    cursor = last + ONE_DAY
    cursor += timedelta(days=(weekday - cursor.weekday()) % 7)
    while len(days) < n:
        days.append(cursor)
        cursor += timedelta(days=7)
    return days


def load_periods() -> pd.DataFrame | None:
    import etl_helpers
    try:
        return etl_helpers.read_table("dim_scoring_period")
    except Exception as exc:
        print(f"[warn] dim_scoring_period not read ({type(exc).__name__}): weekday Close Days only")
        return None


def sources_by_file() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for src in yaml.safe_load(SOURCES.read_text(encoding="utf-8"))["sources"]:
        for feed in src.get("feeds", []):
            names = out.setdefault(feed["notebook"], [])
            if src["name"] not in names:
                names.append(src["name"])
    return out


def cell(text: str) -> str:
    return str(text).replace("|", "\\|")


def render(steps: list[dict], stages: dict, periods: pd.DataFrame | None, today: date,
           weekday: int, built: datetime, sources: dict[str, list[str]]) -> str:
    by_name = {s["name"]: s for s in steps}
    out = ["# Refresh schedule", "",
           "Generated from the pipeline's own step list when the site is built, "
           "so it cannot drift from what runs. A step runs `daily`, or on each "
           "Close Day (`close_day`), the day after a Scoring Period ends. "
           "([ADR-0020](" + GITHUB + "/docs/adr/0020-daily-runs-weekly-finals.md))", ""]
    out += ["## Next Close Days", ""]
    out += [f"- {d:%A, %B} {d.day}, {d.year}" for d in next_close_days(periods, today, weekday)]
    out += ["", f"Last built: {built:%Y-%m-%d %H:%M} UTC", "", "## Stages", ""]
    for stage in stages["stages"]:
        members = [by_name[m["name"]] for m in stage["steps"]]
        out += [f"### {stage['name']}", "", " ".join(stage["description"].split()), ""]
        out += [f"**Cadence:** {', '.join(dict.fromkeys(s['cadence'] for s in members))}"
                f" · **Phase:** {'; '.join(dict.fromkeys(phase_text(s) for s in members))}"
                f" · **Login:** {'yes' if any(needs_login(s) for s in members) else 'no'}", ""]
        out += ["| Step | What it does | Phase | Cadence | Login | Runner |", "|---|---|---|---|---|---|"]
        for m in stage["steps"]:
            s = by_name[m["name"]]
            out.append(f"| `{s['name']}` | {cell(m['summary'])} | {phase_text(s)} | {s['cadence']} "
                       f"| {'yes' if needs_login(s) else 'no'} | {RUNNER} |")
        out.append("")
        out.append("Lands: " + ", ".join(f"`{t}`" for t in stage["tables"]))
        names = list(dict.fromkeys(n for m in stage["steps"] for n in sources.get(script_file(by_name[m["name"]]), [])))
        if names:
            out += ["", "Sources: " + "; ".join(names)]
        out.append("")
    pub = stages["publish"]
    out += [f"### {pub['name']}", "", " ".join(pub["description"].split()), "",
            "**Cadence:** every run · **Login:** no", "", "| Part | What it does |", "|---|---|"]
    out += [f"| {i['name']} | {cell(i['summary'])} |" for i in pub["items"]]
    out += ["", "## Run by hand", "",
            "These steps are never scheduled. Each one is run by hand when it is needed, "
            "and has no cadence. Notebook order and run modes are in the "
            f"[notebooks README]({GITHUB}/notebooks/README.md).", "", "| Step | What it does |", "|---|---|"]
    out += [f"| `{i['name']}` | {cell(i['summary'])} |" for i in stages["manual"]]
    out.append("")
    return "\n".join(out)


def build(today: date | None = None, built: datetime | None = None) -> str:
    rp = load_run_pipeline()
    import etl_helpers
    stages = yaml.safe_load(STAGES.read_text(encoding="utf-8"))
    return render(rp.build_steps(None), stages, load_periods(),
                  today or rp.league_today(), etl_helpers.CFG.close_day_weekday,
                  built or datetime.now(timezone.utc), sources_by_file())


def main() -> int:
    text = build()
    PAGE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {PAGE.name} ({len(text.splitlines())} lines)")
    for line in text.splitlines():
        if line.startswith(("- ", "Last built")):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
