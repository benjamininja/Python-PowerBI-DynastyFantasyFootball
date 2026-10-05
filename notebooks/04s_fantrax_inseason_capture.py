# %% [markdown]
# # 04s_fantrax_inseason_capture  (Playwright — in-season league payloads)
#
# **Purpose:** Capture the authenticated in-season Fantrax payloads for
# league `v744203wmmvjqzv6` (#78, map #70; #118), and load Period Scoring
# and Matchups from them: matchup scores and every rostered player's points
# per Scoring Period. The public `fxea` API exposes none of the
# scores/points (#80), so this rides the internal `fxpa/req` RPC like
# 04a/04t/04v/04w. Endpoint map probed live 2026-09-26 — see #78.
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
#     Fantrax ignores `period` here (measured 2026-10-04, #118). Saved raw
#     and never loaded: it carries Fantrax's Salary Remaining per team,
#     which #97 reads. No standings table is built (ADR-0016 amendment
#     decision 11): Standings are derived from Matchups.
# Roster State is 04r's job (public `getTeamRosters`); the 28 logged-in
# `getTeamRosterInfo` calls per period were dropped (#118). Trades, claims
# and drops are 04t's job.
#
# **Errors:** Fantrax answers bad requests with HTTP 200 + `pageError`. The
# schedule call raises on one. A period that gets one writes no file, is
# reported, and the run carries on and exits 1.
#
# **Raw output:**
# - `data/raw/fantrax_inseason_{season}_schedule.json` =
#   `{"captured_at", "responses", ...}`
# - `data/raw/fantrax_inseason_{season}_p{NN}.json` =
#   `{"captured_at", "period", "standings", "live_scoring"}`
# `captured_at` is the UTC time the file was written. A file captured on
# 2026-10-04 also holds two by-period standings probes; the load ignores them.
#
# **Load** (after the capture, or alone with `--from-raw`): a period loads
# once its games are final (`allEventsFinished`), even while its Update-Set
# is still `open`; it is replaced whole on every run until it is `closed`
# (ADR-0016 amendment decisions 1, 5, 9 and 15).
# - `fact_period_scoring.parquet` -- one row per rostered player with a
#   live-scoring entry, per team: `fpts` as served, split by Unit, and
#   `is_starter` (listed under `ACTIVE`). A player with no entry gets no row.
# - `fact_matchup.parquet` -- two mirrored rows per matchup, from the
#   schedule's week table.
# Both replace-by-`(season_id, period)`. `capture_date` is the Eastern day
# the raw file was written.
#
# **Which periods:** the regular-season periods that have started and are
# not `closed` in `dim_scoring_period`. `--periods` captures any period
# asked for, but a period outside that list is never loaded. Fantrax answers
# for a period that has not started with 28 teams and no entries.
#
# **The load fails, and writes nothing, when:** a raw file is missing or has
# no `captured_at`; a reply's teams are not exactly dim_fantasy_teams' teams;
# a team has no `BENCH` group (a capture without the bench view); a player is
# listed twice on a team; a stat id is not `<group>#<category>#<pos>` with a
# known group; a team's Starter points do not sum to its `totalFpts`; the
# week's matchups do not hold every team once.
#
# **Run:** python notebooks/04s_fantrax_inseason_capture.py [--periods 1-3] [--from-raw]

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

import pandas as pd

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "04a_fantrax_weekly_scrape.py").exists():
        sys.path.insert(0, str(_p))
        break
from etl_helpers import DATA, fantrax_public_get, load_replace_partition

# The season id and the Update-Set states are 04p's; the league clock is 04r's.
fx = importlib.import_module("04a_fantrax_weekly_scrape")
lg = importlib.import_module("04p_fantrax_league_info")
rs = importlib.import_module("04r_fantrax_roster_state")
CFG = fx.CFG

LEAGUE_URL = f"https://www.fantrax.com/fantasy/league/{CFG.league_id}"
PULL_DELAY_S = (0.5, 1.5)     # between read pulls, same pacing as 04v
LIVE_GROUPS = ("ACTIVE", "BENCH")
STARTER_GROUP = "ACTIVE"

SCORING_PATH = DATA / "fact_period_scoring.parquet"
MATCHUP_PATH = DATA / "fact_matchup.parquet"

# Unit (CONTEXT.md; ADR-0017 decision 2). A stat id is
# `<group>#<category>#<pos>`: the group is the side of the ball, and two
# categories are Special Teams whichever group they sit in.
UNIT_OF_GROUP = {"1010": "Offense", "1020": "Defense"}
SPECIAL_TEAMS_CATEGORIES = {"3218", "256g"}      # return yards, blocked kicks
UNIT_COLUMN = {"Offense": "fpts_offense", "Defense": "fpts_defense",
               "Special Teams": "fpts_special_teams"}
POINTS_TOLERANCE = 0.01

SCORING_COLUMNS = ["season_id", "period", "team_key", "scorer_id", "is_starter", "fpts",
                   *UNIT_COLUMN.values(), "capture_date"]
MATCHUP_COLUMNS = ["season_id", "period", "team_key", "opponent_team_key", "is_home",
                   "fpts_for", "fpts_against", "capture_date"]


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
    return {
        "standings": ("getStandings", {"view": "COMBINED", "period": n}, "standings"),
        "live_scoring": (
            "getLiveScoringStats", {"period": n, "playerViewType": "2"}, "livescoring"),
    }


def period_snapshot(n: int, post) -> dict:
    """One period's raw-file body. `post(method, data, ref)` returns the raw
    reply. A pageError on either request raises PageError."""
    snap = {"period": n}
    for key, (method, data, ref) in period_requests(n).items():
        raw = post(method, data, ref)
        err = page_error(raw)
        if err:
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


# %%
def is_final(live: dict) -> bool:
    """True once every game of the period is over."""
    return _data(live).get("allEventsFinished") is True


def unit_of(scip_id: str) -> str:
    """The Unit a stat's points belong to. Raises on an id that is not
    `<group>#<category>#<pos>` with a known group."""
    parts = str(scip_id).split("#")
    if len(parts) != 3 or parts[0] not in UNIT_OF_GROUP:
        raise ValueError(f"unknown stat id {scip_id!r}")
    return "Special Teams" if parts[1] in SPECIAL_TEAMS_CATEGORIES else UNIT_OF_GROUP[parts[0]]


def periods_to_load(periods: pd.DataFrame, now) -> list[int]:
    """The periods captured and loaded this run: one season's regular-season
    periods that have started by `now` and are not `closed`. `periods` is that
    season's dim_scoring_period rows."""
    started = ~periods["is_playoff"] & (periods["start_at"] <= now)
    due = periods[started & ~periods["update_set_state"].eq(lg.CLOSED)]
    return sorted(int(p) for p in due["period"])


def _check_teams(got: set, key_of: dict, where: str) -> None:
    want = set(key_of)
    if got != want:
        raise ValueError(f"{where}: {len(got)} teams, expected {len(want)} "
                         f"(missing {sorted(want - got)}; not in dim_fantasy_teams "
                         f"{sorted(got - want, key=str)})")


def scoring_to_frame(live: dict, teams: pd.DataFrame, season_id: str, period: int,
                     capture_date) -> pd.DataFrame:
    """One final getLiveScoringStats reply -> fact_period_scoring rows.

    `teams` is dim_fantasy_teams (`fantrax_team_id` -> `team_key`). One row per
    (team, player with an entry): `fpts` as Fantrax serves it, its stats' points
    summed by Unit, and `is_starter` when the player is listed under `ACTIVE`.
    A rostered player with no entry gets no row. Raises on a reply whose teams
    are not exactly the dim's, a team with a group missing, a player listed
    twice on a team, an unknown stat id, or a team whose Starter points do not
    sum to its `totalFpts`.
    """
    key_of = dict(zip(teams["fantrax_team_id"], teams["team_key"]))
    all_teams = _data(live).get("statsPerTeam", {}).get("allTeamsStats", {})
    _check_teams(set(all_teams), key_of, f"live scoring period {period}")
    recs = []
    for team_id, groups in all_teams.items():
        where = f"live scoring period {period} team {team_id}"
        seen = set()
        for group in LIVE_GROUPS:
            if group not in groups:
                raise ValueError(f"{where}: no {group} group (captured without the bench view?)")
            total = 0.0
            for scorer_id, entry in (groups[group].get("statsMap") or {}).items():
                if scorer_id.startswith("_"):          # _1010 / _1020: group totals
                    continue
                if scorer_id in seen:
                    raise ValueError(f"{where}: player {scorer_id} is listed twice")
                seen.add(scorer_id)
                units = dict.fromkeys(UNIT_COLUMN.values(), 0.0)
                for stat in entry.get("object2") or []:
                    units[UNIT_COLUMN[unit_of(stat["scipId"])]] += float(stat["fpts"])
                fpts = float(entry["object1"])
                total += fpts
                # Fantrax serves points to the cent, so rounding a Unit's sum
                # changes no served value: it only drops float-addition noise.
                recs.append((key_of[team_id], scorer_id, group == STARTER_GROUP, fpts,
                             *(round(v, 2) for v in units.values())))
            if group == STARTER_GROUP:
                served = groups[group].get("totalFpts")
                if served is None or abs(float(served) - total) > POINTS_TOLERANCE:
                    raise ValueError(f"{where}: Starters sum to {total:.2f}, "
                                     f"totalFpts is {served}")

    rows = pd.DataFrame.from_records(
        recs, columns=["team_key", "scorer_id", "is_starter", "fpts", *UNIT_COLUMN.values()])
    rows = rows.sort_values(["team_key", "scorer_id"], ignore_index=True)
    df = pd.DataFrame({
        "season_id": pd.Series(season_id, index=rows.index, dtype="str"),
        "period": pd.Series(period, index=rows.index, dtype="int64"),
        "team_key": rows["team_key"].astype("str"),
        "scorer_id": rows["scorer_id"].astype("str"),
        "is_starter": rows["is_starter"].astype("bool"),
        "fpts": rows["fpts"].astype("float64"),
        **{c: rows[c].astype("float64") for c in UNIT_COLUMN.values()},
        "capture_date": pd.Series(capture_date, index=rows.index, dtype="datetime64[us]"),
    })
    return df[SCORING_COLUMNS]


def _week_of(table: dict) -> int | None:
    m = re.search(r"(\d+)", table.get("caption", ""))
    return int(m.group(1)) if m else None


def _score(cell: dict, where: str) -> float:
    text = str(cell.get("content", "")).replace(",", "")
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{where}: score {text!r} is not a number") from None


def matchups_to_frame(schedule: dict, teams: pd.DataFrame, season_id: str, period: int,
                      capture_date) -> pd.DataFrame:
    """The schedule's week `period` -> fact_matchup rows.

    Two mirrored rows per matchup, one per team: its opponent, whether it is
    the home side, and the Team Score of each side as the schedule shows it.
    Row cells are away team, away score, home team, home score. Raises unless
    the week has exactly one table whose matchups hold every team of `teams`
    once, with numeric scores.
    """
    key_of = dict(zip(teams["fantrax_team_id"], teams["team_key"]))
    tables = [t for t in _data(schedule).get("tableList", []) if _week_of(t) == period]
    if len(tables) != 1:
        raise ValueError(f"schedule: {len(tables)} tables for week {period}, expected 1")
    recs, listed = [], []
    for i, row in enumerate(tables[0].get("rows", [])):
        where = f"schedule week {period} row {i}"
        cells = row.get("cells") or []
        if len(cells) != 4:
            raise ValueError(f"{where}: {len(cells)} cells, expected 4")
        away, home = cells[0].get("teamId"), cells[2].get("teamId")
        away_pts, home_pts = _score(cells[1], where), _score(cells[3], where)
        listed += [away, home]
        if away in key_of and home in key_of:
            recs.append((key_of[away], key_of[home], False, away_pts, home_pts))
            recs.append((key_of[home], key_of[away], True, home_pts, away_pts))
    _check_teams(set(listed), key_of, f"schedule week {period}")
    if len(listed) != len(key_of):
        raise ValueError(f"schedule week {period}: {len(listed) // 2} matchups do not "
                         f"hold each of {len(key_of)} teams once")

    rows = pd.DataFrame.from_records(
        recs, columns=["team_key", "opponent_team_key", "is_home", "fpts_for", "fpts_against"])
    rows = rows.sort_values("team_key", ignore_index=True)
    df = pd.DataFrame({
        "season_id": pd.Series(season_id, index=rows.index, dtype="str"),
        "period": pd.Series(period, index=rows.index, dtype="int64"),
        "team_key": rows["team_key"].astype("str"),
        "opponent_team_key": rows["opponent_team_key"].astype("str"),
        "is_home": rows["is_home"].astype("bool"),
        "fpts_for": rows["fpts_for"].astype("float64"),
        "fpts_against": rows["fpts_against"].astype("float64"),
        "capture_date": pd.Series(capture_date, index=rows.index, dtype="datetime64[us]"),
    })
    return df[MATCHUP_COLUMNS]


def read_raw(suffix: str) -> tuple[dict, pd.Timestamp]:
    """One saved raw file and the league day it was written. Raises on a
    missing file and on a file with no `captured_at` (a capture older than
    #118, which also lacks the bench view)."""
    path = out_path(suffix)
    if not path.exists():
        raise FileNotFoundError(f"{path.name}: no capture on disk")
    body = json.loads(path.read_text(encoding="utf-8"))
    if not body.get("captured_at"):
        raise ValueError(f"{path.name} has no captured_at -- capture it again")
    return body, rs.league_day(pd.Timestamp(body["captured_at"]))


def parse_raw(periods: list[int], teams: pd.DataFrame,
              season_id: str) -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    """The saved captures of `periods` -> (fact_period_scoring rows,
    fact_matchup rows, the periods whose games are not final). A period that is
    not final gives no rows. Everything is parsed before anything is returned,
    so a bad file leaves nothing to write."""
    scoring, matchups, waiting = [], [], []
    schedule, schedule_day = read_raw("schedule") if periods else ({}, None)
    for n in periods:
        snap, day = read_raw(f"p{n:02d}")
        if snap.get("period") != n:
            raise ValueError(f"{out_path(f'p{n:02d}').name} holds period {snap.get('period')}")
        if not is_final(snap["live_scoring"]):
            waiting.append(n)
            continue
        scoring.append(scoring_to_frame(snap["live_scoring"], teams, season_id, n, day))
        matchups.append(matchups_to_frame(schedule, teams, season_id, n, schedule_day))
    if not scoring:
        return (pd.DataFrame(columns=SCORING_COLUMNS), pd.DataFrame(columns=MATCHUP_COLUMNS),
                waiting)
    return pd.concat(scoring, ignore_index=True), pd.concat(matchups, ignore_index=True), waiting


def load(periods: list[int], teams: pd.DataFrame, season_id: str) -> int:
    """Load every final period of `periods` from the saved captures."""
    scoring, matchups, waiting = parse_raw(periods, teams, season_id)
    if waiting:
        print(f"[skip] period(s) {waiting}: games not final, nothing loaded")
    if scoring.empty:
        print(f"[ok] fact_period_scoring, fact_matchup: no final period of {season_id} to load")
        return 0
    total_s = load_replace_partition(scoring, SCORING_PATH, part_cols=("season_id", "period"))
    total_m = load_replace_partition(matchups, MATCHUP_PATH, part_cols=("season_id", "period"))
    print(f"[ok] fact_period_scoring: {len(scoring)} rows for {season_id}, periods "
          f"{scoring.groupby('period').size().to_dict()} "
          f"({int(scoring['is_starter'].sum())} Starters) -> {total_s} total rows "
          f"-> {SCORING_PATH.name}")
    print(f"[ok] fact_matchup: {len(matchups)} rows for {season_id}, periods "
          f"{matchups.groupby('period').size().to_dict()} -> {total_m} total rows "
          f"-> {MATCHUP_PATH.name}")
    return 0


# %%
def capture(periods: list[int]) -> None:
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
        finally:
            ctx.close()

    if failed:
        raise SystemExit(f"[fail] {len(failed)} period(s) not captured: {sorted(failed)}")


# %%
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Capture the in-season Fantrax payloads, then load Period Scoring "
                    "and Matchups for every period whose games are final.")
    ap.add_argument("--periods", help="e.g. 3 or 1-3; default: every regular-season "
                                      "period that has started and is not closed")
    ap.add_argument("--from-raw", action="store_true",
                    help="load from the saved raw files: no browser, no login")
    args = ap.parse_args(argv)

    now = pd.Timestamp.now(tz="UTC")
    # The season is the league's own, as in 04r. The raw files are named by
    # 04a's snapshot_season, so the two must agree.
    info = fantrax_public_get("getLeagueInfo", CFG.league_id, expect=("seasonYear",))
    season_id = lg.season_id_of(info)
    if int(info["seasonYear"]) != int(CFG.snapshot_season):
        raise ValueError(f"the league's season is {info['seasonYear']}; 04a's "
                         f"snapshot_season is {CFG.snapshot_season}")
    periods = pd.read_parquet(lg.PERIODS_PATH) if lg.PERIODS_PATH.exists() else None
    if periods is None or season_id not in set(periods["season_id"]):
        raise ValueError(f"season {season_id} is not in dim_scoring_period -- run 04p first")
    due = periods_to_load(periods[periods["season_id"] == season_id], now)
    asked = parse_periods(args.periods) if args.periods else due
    teams = pd.read_parquet(DATA / "dim_fantasy_teams.parquet")

    if not args.from_raw and asked:
        capture(asked)
    not_due = [n for n in asked if n not in due]
    if not_due:
        print(f"[skip] period(s) {not_due}: not a started, open regular-season period, "
              "never loaded")
    return load([n for n in asked if n in due], teams, season_id)


if __name__ == "__main__":
    sys.exit(main())
