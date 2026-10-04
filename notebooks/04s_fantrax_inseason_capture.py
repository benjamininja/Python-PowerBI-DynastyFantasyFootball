# %% [markdown]
# # 04s_fantrax_inseason_capture  (Playwright — in-season league payloads)
#
# **Purpose:** Capture the authenticated in-season Fantrax payloads for
# league `v744203wmmvjqzv6` (#78, map #70; #118): matchup scores, standings
# and every rostered player's points per Scoring Period. The public `fxea`
# API exposes none of the scores/points (#80), so this rides the internal
# `fxpa/req` RPC like 04a/04t/04v/04w. Endpoint map probed live 2026-09-26
# — see #78.
#
# **Requests** (all POST `fxpa/req?leagueId=...`):
# - `getStandings {view: "SCHEDULE"}` — one call, every week's matchups:
#   `tableList[]` one table per week, rows = away teamId+FPts, home teamId+FPts.
# - Per period, `period_requests(n)`:
#   - `getLiveScoringStats {period, playerViewType: "2"}` —
#     `statsPerTeam.allTeamsStats[teamId].{ACTIVE,BENCH}`: Starters under
#     `ACTIVE`; Bench, IR and Minors under `BENCH`.
#     `statsMap[scorer_id].object2[] = {scipId, sv, av, fpts}`.
#     **`period` is required** — omitted, it returns only today's live slice.
#     Without `playerViewType` only Starters come back.
#   - `getStandings {view: "COMBINED", period}` — the *current* standings:
#     Fantrax ignores `period` here (measured 2026-10-04, #118).
#   - Two standings probes (`PROBES`), `timeframeType: "BY_PERIOD"` with
#     `timeStartType` `FROM_SEASON_START` and `PERIOD_ONLY`: do they serve a
#     past period's standings? The reply's `displayedSelections` echo says
#     whether Fantrax took the selection. #118 decides `fact_standings` on it.
# Roster State is 04r's job (public `getTeamRosters`); the 28 logged-in
# `getTeamRosterInfo` calls per period were dropped (#118). Trades, claims
# and drops are 04t's job.
#
# **Errors:** Fantrax answers bad requests with HTTP 200 + `pageError`. The
# schedule call raises on one. A period that gets one writes no file, is
# reported, and the run carries on and exits 1. A probe's error reply is the
# answer to the probe, so it is kept in the file.
#
# **Output** (raw only; parsing is #118's next PR):
# - `data/raw/fantrax_inseason_{season}_schedule.json` =
#   `{"captured_at", "responses", ...}`
# - `data/raw/fantrax_inseason_{season}_p{NN}.json` =
#   `{"captured_at", "period", "standings", "standings_by_period",
#   "standings_period_only", "live_scoring"}`
# `captured_at` is the UTC time the file was written.
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
from datetime import date, datetime, timezone
from pathlib import Path

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "04a_fantrax_weekly_scrape.py").exists():
        sys.path.insert(0, str(_p))
        break
fx = importlib.import_module("04a_fantrax_weekly_scrape")
CFG = fx.CFG

LEAGUE_URL = f"https://www.fantrax.com/fantasy/league/{CFG.league_id}"
PULL_DELAY_S = (0.5, 1.5)     # between read pulls, same pacing as 04v
# Raw-file keys whose reply is a question put to Fantrax, not a payload we
# depend on: an error reply is kept, not raised.
PROBES = ("standings_by_period", "standings_period_only")
LIVE_GROUPS = ("ACTIVE", "BENCH")


class PageError(RuntimeError):
    """Fantrax's HTTP-200 error reply to one request."""


def out_path(suffix: str) -> Path:
    return Path(CFG.raw_dir) / f"fantrax_inseason_{CFG.snapshot_season}_{suffix}.json"


def save(suffix: str, body: dict) -> Path:
    """Write one raw file, stamped with the UTC time it was written."""
    path = out_path(suffix)
    stamped = {"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **body}
    path.write_text(json.dumps(stamped, indent=2), encoding="utf-8")
    return path


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


def period_requests(n: int) -> dict[str, tuple[str, dict, str]]:
    """One period's requests: raw-file key -> (method, data, refUrl page)."""
    by_period = {"view": "COMBINED", "period": n, "timeframeType": "BY_PERIOD"}
    return {
        "standings": ("getStandings", {"view": "COMBINED", "period": n}, "standings"),
        "standings_by_period": (
            "getStandings", {**by_period, "timeStartType": "FROM_SEASON_START"}, "standings"),
        "standings_period_only": (
            "getStandings", {**by_period, "timeStartType": "PERIOD_ONLY"}, "standings"),
        "live_scoring": (
            "getLiveScoringStats", {"period": n, "playerViewType": "2"}, "livescoring"),
    }


def period_snapshot(n: int, post) -> dict:
    """One period's raw-file body. `post(method, data, ref)` returns the raw
    reply. A pageError raises PageError, except on a probe (kept as the answer)."""
    snap = {"period": n}
    for key, (method, data, ref) in period_requests(n).items():
        raw = post(method, data, ref)
        err = page_error(raw)
        if err and key not in PROBES:
            raise PageError(f"{method} {data} -> pageError {err.get('code')}: {err.get('text')}")
        snap[key] = raw
    return snap


def _data(raw: dict) -> dict:
    return (raw.get("responses") or [{}])[0].get("data") or {}


def live_counts(live: dict) -> dict[str, int]:
    """Teams and player entries per group in a live-scoring reply. The
    `_1010` / `_1020` keys are group totals, not players."""
    teams = _data(live).get("statsPerTeam", {}).get("allTeamsStats", {})
    out = {"teams": len(teams)}
    for g in LIVE_GROUPS:
        out[g] = sum(1 for t in teams.values()
                     for sid in (t.get(g) or {}).get("statsMap", {}) if not sid.startswith("_"))
    return out


def standings_echo(raw: dict) -> str:
    """What a standings reply says it served: the selection Fantrax echoes."""
    err = page_error(raw)
    if err:
        return f"pageError {err.get('code')}"
    sel = _data(raw).get("displayedSelections") or {}
    return "/".join(str(sel.get(k)) for k in ("timeframeType", "timeStartType", "period"))


# %%
def capture(periods: list[int] | None) -> None:
    from playwright.sync_api import sync_playwright

    scraper = fx.FantraxScraper(CFG)
    failed: dict[int, str] = {}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(CFG.user_data_dir, headless=CFG.headless)
        try:
            page = ctx.new_page()
            page.set_default_timeout(CFG.nav_timeout_ms)

            def post(method: str, data: dict, ref: str) -> dict:
                what = f"{method} {data}"
                raw = scraper._post_json(ctx, payload(method, data, ref), what)
                if scraper._session_dead(raw):
                    scraper._login(page)
                    raw = scraper._post_json(ctx, payload(method, data, ref), what)
                    if scraper._session_dead(raw):
                        raise RuntimeError(
                            "Still WARNING_NOT_LOGGED_IN after login. Check .env creds, or "
                            "run once with CFG.headless=False to clear a Cloudflare/captcha gate."
                        )
                time.sleep(random.uniform(*PULL_DELAY_S))
                return raw

            schedule = post("getStandings", {"view": "SCHEDULE"}, "standings")
            err = page_error(schedule)
            if err:
                raise PageError(f"getStandings SCHEDULE -> pageError {err.get('code')}: {err.get('text')}")
            path = save("schedule", schedule)
            weeks = schedule_periods(schedule)
            teams = schedule_team_ids(schedule)
            print(f"[ok] schedule: {len(weeks)} week(s), {len(teams)} team(s) -> {path}")

            if periods is None:
                periods = [n for n, start in weeks if start <= date.today()]
            for n in periods:
                # One bad period must not cost the others; a dead session still aborts.
                try:
                    snap = period_snapshot(n, post)
                except PageError as e:
                    failed[n] = str(e)
                    print(f"[fail] period {n}: {e}")
                    continue
                path = save(f"p{n:02d}", snap)
                live = live_counts(snap["live_scoring"])
                print(f"[ok] period {n}: live_scoring {live['teams']} teams, "
                      f"{live['ACTIVE']} ACTIVE, {live['BENCH']} BENCH -> {path}")
                for key in ("standings", *PROBES):
                    print(f"       {key}: {standings_echo(snap[key])}")
        finally:
            ctx.close()

    if failed:
        raise SystemExit(f"[fail] {len(failed)} period(s) not captured: {sorted(failed)}")


# %%
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--periods", help="e.g. 3 or 1-3; default 1..current")
    args = ap.parse_args()
    capture(parse_periods(args.periods) if args.periods else None)
