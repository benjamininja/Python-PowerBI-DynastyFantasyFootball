# %% [markdown]
# # 04s_fantrax_inseason_capture  (Playwright — in-season league payloads)
#
# **Purpose:** Capture the authenticated in-season Fantrax payloads for
# league `v744203wmmvjqzv6` (#78, map #70): matchup scores, standings,
# starters' per-player points and the per-team roster snapshot (age, salary,
# contract, FPts, pick ownership). The public `fxea` API exposes none of the
# scores/points (#80), so this rides the internal `fxpa/req` RPC like
# 04a/04t/04v/04w. Endpoint map probed live 2026-09-26 — see #78.
#
# **Requests** (all POST `fxpa/req?leagueId=...`):
# - `getStandings {view: "SCHEDULE"}` — one call, every week's matchups:
#   `tableList[]` one table per week, rows = away teamId+FPts, home teamId+FPts.
# - `getStandings {view: "COMBINED", period}` — year-to-date standings as of
#   that period.
# - `getLiveScoringStats {period}` — `statsPerTeam.allTeamsStats[teamId].ACTIVE`
#   = starters only, `statsMap[scorer_id].object2[] = {scipId, sv, av, fpts}`.
#   **`period` is required** — omitted, it returns only today's live slice.
# - `getTeamRosterInfo {teamId, period}` — roster tables (Age|Sal|Con|FPts|...)
#   plus `draftPicksData` (pick ownership, ADR-0006).
# Trades/claims/drops are 04t's job (`team: "ALL"`, both views) — not repeated.
#
# **Errors:** Fantrax answers bad requests with HTTP 200 + `pageError`; every
# response is checked and raises rather than persisting an error body.
#
# **Output** (raw only; parsing is #79/#81):
# - `data/raw/fantrax_inseason_{season}_schedule.json`
# - `data/raw/fantrax_inseason_{season}_p{NN}.json` =
#   `{"period", "standings", "live_scoring", "rosters": {teamId: raw}}`
#
# **Run:** python notebooks/04s_fantrax_inseason_capture.py [--periods 1-3]
#   Default periods = 1..current (every schedule week whose start date <= today).

# %%
import argparse
import importlib
import json
import random
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "04a_fantrax_weekly_scrape.py").exists():
        sys.path.insert(0, str(_p))
        break
fx = importlib.import_module("04a_fantrax_weekly_scrape")
CFG = fx.CFG

LEAGUE_URL = f"https://www.fantrax.com/fantasy/league/{CFG.league_id}"
PULL_DELAY_S = (0.5, 1.5)     # between read pulls, same pacing as 04v


def out_path(suffix: str) -> Path:
    return Path(CFG.raw_dir) / f"fantrax_inseason_{CFG.snapshot_season}_{suffix}.json"


# %%
def payload(method: str, data: dict, ref: str) -> dict:
    return {
        "msgs": [{"method": method, "data": {"leagueId": CFG.league_id, **data}}],
        "uiv": CFG.ui_version,
        "refUrl": f"{LEAGUE_URL}/{ref}",
        "dt": 0, "at": 0, "tz": CFG.timezone, "v": CFG.api_version,
    }


def page_error(raw: dict):
    """Fantrax's HTTP-200 error channel: top-level or per-response pageError."""
    if raw.get("pageError"):
        return raw["pageError"]
    resp = (raw.get("responses") or [{}])[0]
    return resp.get("pageError")


def schedule_periods(schedule: dict) -> list[tuple[int, date]]:
    """(period, start_date) per schedule table. Caption 'Week N', subCaption
    '(Wed Sep 9, 2026 - Wed Sep 16, 2026)'."""
    out = []
    for t in schedule["responses"][0]["data"].get("tableList", []):
        m = re.search(r"(\d+)", t.get("caption", ""))
        d = re.search(r"\(\w+ (\w+ \d+, \d{4})", t.get("subCaption", ""))
        if m and d:
            out.append((int(m.group(1)), datetime.strptime(d.group(1), "%b %d, %Y").date()))
    return out


def schedule_team_ids(schedule: dict) -> list[str]:
    ids = {c["teamId"]
           for t in schedule["responses"][0]["data"].get("tableList", [])
           for r in t.get("rows", [])
           for c in r.get("cells", []) if c.get("teamId")}
    return sorted(ids)


def parse_periods(spec: str) -> list[int]:
    lo, _, hi = spec.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


# %%
def capture(periods: list[int] | None) -> None:
    from playwright.sync_api import sync_playwright

    scraper = fx.FantraxScraper(CFG)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(CFG.user_data_dir, headless=CFG.headless)
        page = ctx.new_page()
        page.set_default_timeout(CFG.nav_timeout_ms)

        def post(method: str, data: dict, ref: str) -> dict:
            what = f"{method} {data}"
            raw = scraper._post_json(ctx, payload(method, data, ref), what)
            if scraper._session_dead(raw):
                scraper._login(page)
                raw = scraper._post_json(ctx, payload(method, data, ref), what)
                if scraper._session_dead(raw):
                    ctx.close()
                    raise RuntimeError(
                        "Still WARNING_NOT_LOGGED_IN after login. Check .env creds, or "
                        "run once with CFG.headless=False to clear a Cloudflare/captcha gate."
                    )
            err = page_error(raw)
            if err:
                ctx.close()
                raise RuntimeError(f"{what} -> pageError {err.get('code')}: {err.get('text')}")
            time.sleep(random.uniform(*PULL_DELAY_S))
            return raw

        schedule = post("getStandings", {"view": "SCHEDULE"}, "standings")
        out_path("schedule").write_text(json.dumps(schedule, indent=2), encoding="utf-8")
        weeks = schedule_periods(schedule)
        teams = schedule_team_ids(schedule)
        print(f"[ok] schedule: {len(weeks)} week(s), {len(teams)} team(s) -> {out_path('schedule')}")

        if periods is None:
            periods = [n for n, start in weeks if start <= date.today()]
        for n in periods:
            snap = {
                "period": n,
                "standings": post("getStandings", {"view": "COMBINED", "period": n}, "standings"),
                "live_scoring": post("getLiveScoringStats", {"period": n}, "livescoring"),
                "rosters": {tid: post("getTeamRosterInfo", {"teamId": tid, "period": n}, "team/roster")
                            for tid in teams},
            }
            path = out_path(f"p{n:02d}")
            path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
            n_live = len(snap["live_scoring"]["responses"][0]["data"]
                         .get("statsPerTeam", {}).get("allTeamsStats", {}))
            print(f"[ok] period {n}: standings, live_scoring ({n_live} teams), "
                  f"{len(snap['rosters'])} rosters -> {path}")

        ctx.close()


# %%
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", help="e.g. 3 or 1-3; default 1..current")
    args = ap.parse_args()
    capture(parse_periods(args.periods) if args.periods else None)
