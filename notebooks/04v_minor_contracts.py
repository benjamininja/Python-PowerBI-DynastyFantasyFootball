# %% [markdown]
# # 04v_minor_contracts  (Playwright, weekly — Yo-Yo Rule contract compliance)
#
# **Purpose:** Weekly contract-compliance pass for the Yo-Yo Rule: every player
# with career+current regular-season GP <= 19 holds a **Minor** contract
# (league-wide, rostered or FA); playing the 20th game graduates them to **1st**
# (3-year clock starts at the graduation season). Fantrax computes eligibility
# itself (league setting: "Career+Current regular season total GP <= 19", both
# Offense and Individual Defense) — this script READS the site's verdict and
# diffs it against contract types; it does not re-derive eligibility.
#
# **Three pulls per run (all via 04a's authenticated scraper):**
# 1. Eligibility — `getPlayerStats` with `statusOrTeamFilter=
#    MINOR_FANTASY_AVAILABLE|MINOR_FANTASY_TAKEN` (the players-page filter):
#    Fantrax's own list of minors-eligible players, split FA vs rostered.
# 2. Roster placement — `getTeamRosterInfo` per fantasy team: who sits in the
#    Minors squad vs active roster vs IR this week (cap exemption follows
#    placement, not contract type — team's choice, salary charged otherwise).
# 3. (implicit in 1+2) current contract type per player, for the diff.
#
# **Outputs:**
# - `data/raw/fantrax_minor_eligibility_{season}_wk{NN}.json` — raw filter pulls
# - `data/raw/fantrax_rosters_{season}_wk{NN}.json` — raw per-team roster pulls
# - `data/fact_roster_placement.parquet` — weekly placement snapshot,
#   replace-by-(season, week). Deliberately NOT ledger events: stash/activate
#   churn is not an acquisition (ADR-0003 scope).
# - `data/fact_minor_eligibility.parquet` — weekly eligibility snapshot; its
#   week-over-week history detects players who graduate while sitting in the
#   FA pool (absent from both current-week pulls).
# - `data/review/review_contract_actions.csv` — the commissioner worklist:
#   typed actions (set Minor / set 1st / set FA) with reasons. `--apply` replays
#   the rostered rows through Fantrax's contract-edit endpoint (opt-in, never
#   scheduled); `--export-fa-csv` writes `data/review/fa_contract_import.csv`
#   for the FA rows (commissioner CSV-import tool).
#
# **Apply pacing:** the startup apply is a ONE-SITTING session (~28 teams x 4
# POSTs + jittered delays, a few minutes total); weekly steady-state is a
# handful of graduations. Delay knobs: PULL_DELAY_S / APPLY_TEAM_DELAY_S.
#
# **Downstream (not here):** `02d` ingests the raw JSON and emits
# `minor_assignment` / `minor_graduation` ledger events; `02e` replay derives
# current contract type; capmath/PBI charge active-roster salaries and exempt
# Minors-squad placements.
#
# **Run:**  .\run.ps1 notebooks\04v_minor_contracts.py
# Scheduled right after 04a (same Task Scheduler cadence).

# %%
import importlib
import json
import random
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

# ---- Reuse 04a's authenticated scraper (auth, persistent profile, retry) -----
# 04a is the single source of truth for the Fantrax session. Import it by file
# (leading-digit module name -> importlib). It lazy-imports Playwright, so
# importing here is safe even where Playwright isn't installed.
for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "04a_fantrax_weekly_scrape.py").exists():
        sys.path.insert(0, str(_p))
        break
fx = importlib.import_module("04a_fantrax_weekly_scrape")
CFG = fx.CFG

# %%
# ---- Constants ----------------------------------------------------------------
# statusOrTeamFilter values, from the players-page URL:
#   .../players;statusOrTeamFilter=MINOR_FANTASY_AVAILABLE;pageNumber=1
ELIGIBILITY_FILTERS = {
    "MINOR_FANTASY_AVAILABLE": "available",   # minors-eligible, in free agency
    "MINOR_FANTASY_TAKEN": "taken",           # minors-eligible, on a fantasy roster
}

# Header shortNames that may carry the contract type on grid/roster tables.
# "Con" verified against the first real payloads (both grid and roster tables).
CONTRACT_HEADER_CANDIDATES = ("Con", "Contract", "Ctr", "Ct")

# Roster placement is per-ROW (statusId), not per-table — the roster response's
# tables split by stat group (offense/defense), and their captions are empty.
# The live map is read from each response's statusTotals (Fantrax's own id->name
# list); this fallback is the vocabulary observed 2026-07-12. Unknown ids pass
# through raw so new sections (e.g. IR in-season) surface instead of silently
# binning. Cap logic downstream keys on "Minors" (exempt); Active/Reserve charge.
STATUS_TO_SECTION_FALLBACK = {"1": "Active", "2": "Reserve", "9": "Minors"}
EMPTY_SLOT_STATUS = "3"   # placeholder rows, scorerId null

# Contract targets for the diff (contract_id values in dim_contract).
MINOR_CONTRACT = "Minor"
GRADUATE_ROSTERED = "1st"
GRADUATE_FA = "FA"

PLACEMENT_FACT = "fact_roster_placement"
ELIGIBILITY_FACT = "fact_minor_eligibility"
WORKLIST_CSV = "review_contract_actions.csv"
FA_IMPORT_CSV = "fa_contract_import.csv"

# Pacing: jittered sleeps so the run reads like a human clicking through pages,
# not a burst (there is no other rate limiting anywhere in the Fantrax path).
# Startup apply ~= 28 teams x 4 POSTs + delays -> one sitting of a few minutes;
# weekly steady-state is a handful of graduations. Module knobs, not CLI.
PULL_DELAY_S = (0.5, 1.5)     # between read pulls (roster teams, filter pages)
APPLY_TEAM_DELAY_S = (3, 5)   # between teams during --apply (confirm/execute/
                              # verify within a team stay back-to-back — that
                              # matches the UI's own timing)


def _pause(bounds: tuple) -> None:
    time.sleep(random.uniform(*bounds))


# %%
# ---- Authenticated POST with self-heal (04w pattern) ---------------------------
def _post_healed(scraper, ctx, page, payload: dict, what: str) -> dict:
    """POST via the authenticated request context; on WARNING_NOT_LOGGED_IN,
    re-login once and retry (server verdict, same as 04a.fetch())."""
    raw = scraper._post_json(ctx, payload, what)
    if scraper._session_dead(raw):
        scraper._login(page)
        raw = scraper._post_json(ctx, payload, what)
        if scraper._session_dead(raw):
            raise RuntimeError(
                "Still WARNING_NOT_LOGGED_IN after login. Check .env creds, or "
                "run once with CFG.headless=False to clear a Cloudflare/captcha "
                "gate (see data/raw/login_debug.png)."
            )
    return raw


# %%
# ---- Pull 1: minors-eligibility filter (players grid) --------------------------
def eligibility_payload(filter_value: str, page_no: int) -> dict:
    """getPlayerStats scoped to a minors-eligibility filter. positionOrGroup=ALL
    is fine here (its known GP-column gap doesn't matter — eligibility IS the
    filter membership; GP monitoring has its own pull in 04a's backfill)."""
    return {
        "msgs": [{"method": "getPlayerStats", "data": {
            "statusOrTeamFilter": filter_value,
            "pageNumber": str(page_no),
            "maxResultsPerPage": str(CFG.players_page_size),
            "miscDisplayType": CFG.players_misc_display,
            "positionOrGroup": "ALL",
            "seasonOrProjection": fx.resolve_season_or_projection(CFG),
            "timeframeTypeCode": "YEAR_TO_DATE",
        }}],
        "uiv": CFG.ui_version, "refUrl": CFG.ref_url,
        "dt": 0, "at": 0, "tz": CFG.timezone, "v": CFG.api_version,
    }


def fetch_eligibility(scraper, ctx, page) -> dict:
    """Paginate both MINOR_FANTASY_* filters. Returns {filter_value: [pages]}."""
    out = {}
    first = True
    for filt in ELIGIBILITY_FILTERS:
        pages, page_no = [], 1
        while True:
            if not first:
                _pause(PULL_DELAY_S)
            first = False
            raw = _post_healed(scraper, ctx, page,
                               eligibility_payload(filt, page_no), filt)
            pages.append(raw)
            prs = raw["responses"][0]["data"].get("paginatedResultSet", {})
            total_pages = prs.get("totalNumPages", 1)
            print(f"[info] {filt} page {page_no}/{total_pages}")
            if page_no >= int(total_pages):
                break
            page_no += 1
        out[filt] = pages
    return out


def _header_index(data: dict) -> dict:
    """shortName -> cell index. Grid responses carry `tableHeader`; roster
    tables carry `header` (same cells shape)."""
    hdr = data.get("tableHeader") or data.get("header") or {}
    return {c.get("shortName"): i for i, c in enumerate(hdr.get("cells", []))}


def _find_contract_col(hdr: dict) -> str | None:
    return next((h for h in CONTRACT_HEADER_CANDIDATES if h in hdr), None)


def eligibility_to_frame(pulls: dict) -> pd.DataFrame:
    """Flatten the filter pulls: one row per minors-eligible scorer_id with
    fa_status (available|taken) and, when the grid exposes it, contract type."""
    recs, seen = [], set()
    for filt, pages in pulls.items():
        status = ELIGIBILITY_FILTERS[filt]
        for resp in pages:
            d = resp["responses"][0]["data"]
            hdr = _header_index(d)
            con_col = _find_contract_col(hdr)
            for r in d.get("statsTable", []):
                s = r["scorer"]
                sid = s["scorerId"]
                if sid in seen:      # dual-eligible players repeat within a pull
                    continue
                seen.add(sid)
                cells = r.get("cells", [])

                def col(name):
                    i = hdr.get(name)
                    return cells[i].get("content") if (i is not None and i < len(cells)) else None

                recs.append({
                    "scorer_id":    sid,
                    "player_name":  s.get("name"),
                    "position_raw": re.sub(r"<[^>]+>", "", s.get("posShortNames", "")).strip(),
                    "nfl_team":     s.get("teamShortName"),
                    "fa_status":    status,
                    "salary":       fx._cell_num(col("Sal")),
                    "contract":     (col(con_col) or "").strip() if con_col else None,
                    "games_played": fx._cell_num(col("GP")),
                })
    return pd.DataFrame.from_records(recs)


# %%
# ---- Pull 2: per-team roster placement ------------------------------------------
def _team_ids(cfg) -> pd.DataFrame:
    """fantrax_team_id -> team_key/team_name from dim_fantasy_teams (01c)."""
    path = Path(cfg.data_dir) / "dim_fantasy_teams.parquet"
    df = pd.read_parquet(path)
    cols = [c for c in ("fantrax_team_id", "team_key", "team_name") if c in df.columns]
    return df[cols].dropna(subset=["fantrax_team_id"])


def roster_payload(team_id: str) -> dict:
    """getTeamRosterInfo for one fantasy team (the roster-page fxpa method)."""
    return {
        "msgs": [{"method": "getTeamRosterInfo", "data": {"teamId": team_id}}],
        "uiv": CFG.ui_version,
        "refUrl": f"https://www.fantrax.com/fantasy/league/{CFG.league_id}/team/roster",
        "dt": 0, "at": 0, "tz": CFG.timezone, "v": CFG.api_version,
    }


def fetch_rosters(scraper, ctx, page, teams: pd.DataFrame) -> dict:
    """One getTeamRosterInfo call per team. Returns {fantrax_team_id: raw}."""
    out = {}
    for t in teams.itertuples():
        if out:
            _pause(PULL_DELAY_S)
        raw = _post_healed(scraper, ctx, page,
                           roster_payload(t.fantrax_team_id), "getTeamRosterInfo")
        out[t.fantrax_team_id] = raw
        name = getattr(t, "team_name", t.fantrax_team_id)
        print(f"[info] roster {getattr(t, 'team_key', '?')} {name}")
    return out


def rosters_to_frame(rosters: dict, teams: pd.DataFrame,
                     season: int, week: str) -> pd.DataFrame:
    """Flatten per-team roster responses into placement rows. Placement is the
    per-row statusId (1/2=active lineup, 9=Minors squad; see STATUS_TO_SECTION);
    the response's tables split by stat group, not placement. Header-based cell
    lookup, like 04a's grid parser. scorer.minorsEligible rides along as
    Fantrax's row-level eligibility/placement flag."""
    key_by_id = {t.fantrax_team_id: getattr(t, "team_key", None)
                 for t in teams.itertuples()}
    today = date.today().isoformat()
    xwalk = fx._load_crosswalk(CFG)
    recs = []
    for team_id, raw in rosters.items():
        d = raw["responses"][0]["data"]
        tables = d.get("tables") or d.get("rosterTables") or []
        if not tables:
            print(f"[warn] no roster tables for team {team_id} — schema drift? "
                  f"keys: {list(d.keys())[:12]}")
            continue
        # Fantrax's own statusId -> section-name map rides on each table.
        status_map = dict(STATUS_TO_SECTION_FALLBACK)
        for tbl in tables:
            for st in tbl.get("statusTotals", []):
                if st.get("id") and st.get("name"):
                    status_map[st["id"]] = st["name"]
        for tbl in tables:
            hdr = _header_index(tbl)
            con_col = _find_contract_col(hdr)
            for r in tbl.get("rows", []):
                s = r.get("scorer") or {}
                sid = s.get("scorerId")
                status_id = r.get("statusId")
                if not sid or status_id == EMPTY_SLOT_STATUS:   # empty roster slot
                    continue
                section = status_map.get(status_id, str(status_id))
                cells = r.get("cells", [])

                def col(name):
                    i = hdr.get(name)
                    return cells[i].get("content") if (i is not None and i < len(cells)) else None

                gsis, pkey = xwalk.get(sid, (None, None))
                recs.append({
                    "season":          season,
                    "week":            week,
                    "capture_date":    today,
                    "team_id":         team_id,
                    "team_key":        key_by_id.get(team_id),
                    "scorer_id":       sid,
                    "player_name":     s.get("name"),
                    "position_raw":    re.sub(r"<[^>]+>", "", s.get("posShortNames", "")).strip(),
                    "roster_section":  section,
                    "status_id":       status_id,
                    "minors_eligible": bool(s.get("minorsEligible")),
                    "salary":          fx._cell_num(col("Sal")),
                    "contract":        (col(con_col) or "").strip() if con_col else None,
                    "gsis_id":         gsis,
                    "player_key":      pkey,
                })
    df = pd.DataFrame.from_records(recs)
    # Grain: one row per (team, scorer). NOT per scorer — this is a
    # duplicate-player league (each conference drafts its own copy), so the
    # same scorer_id legitimately appears on one team per conference.
    return df.drop_duplicates(subset=["team_id", "scorer_id"], keep="first")


def load_placement(df: pd.DataFrame, cfg) -> str:
    """Replace-by-(season, week) into fact_roster_placement.parquet — same
    idempotent pattern as 04a.load_fact."""
    path = f"{cfg.data_dir}/{PLACEMENT_FACT}.parquet"
    if Path(path).exists():
        old = pd.read_parquet(path)
        keys = set(map(tuple, df[["season", "week"]].drop_duplicates().to_numpy()))
        mask = old[["season", "week"]].apply(tuple, axis=1).isin(keys)
        df = pd.concat([old[~mask], df], ignore_index=True)
    df = df.drop_duplicates(subset=["team_id", "scorer_id", "season", "week"],
                            keep="last")
    df.to_parquet(path, index=False)
    return path


# %%
# ---- Durable eligibility snapshot (fact_minor_eligibility) ---------------------
def load_eligibility(df: pd.DataFrame, cfg, season: int, week: str) -> str:
    """Land the eligibility pull as a parquet fact (replace-by-(season, week)),
    so the FA-eligible population has queryable week-over-week history — the
    raw JSON alone can't answer 'who vanished from eligibility while FA'."""
    df = df.assign(season=season, week=week, capture_date=date.today().isoformat())
    path = f"{cfg.data_dir}/{ELIGIBILITY_FACT}.parquet"
    if Path(path).exists():
        old = pd.read_parquet(path)
        keys = set(map(tuple, df[["season", "week"]].drop_duplicates().to_numpy()))
        mask = old[["season", "week"]].apply(tuple, axis=1).isin(keys)
        df = pd.concat([old[~mask], df], ignore_index=True)
    df = df.drop_duplicates(subset=["scorer_id", "season", "week"], keep="last")
    df.to_parquet(path, index=False)
    return path


def prev_eligibility(cfg, season: int, week: str) -> pd.DataFrame | None:
    """Most recent eligibility snapshot BEFORE (season, week), or None on the
    first ever run. Ordered by capture_date (week labels 'PRE'/'01'.. don't
    sort lexically)."""
    path = Path(cfg.data_dir) / f"{ELIGIBILITY_FACT}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df = df[(df["season"] != season) | (df["week"] != week)]
    if df.empty:
        return None
    latest = df["capture_date"].max()
    return df[df["capture_date"] == latest]


# %%
# ---- Diff: site eligibility vs contract types ----------------------------------
def build_worklist(elig: pd.DataFrame, placement: pd.DataFrame,
                   prev_elig: pd.DataFrame | None = None) -> pd.DataFrame:
    """The Yo-Yo diff. Site eligibility (the MINOR_FANTASY_* pulls) is the truth
    for who SHOULD hold a Minor contract; contract type is what Fantrax does NOT
    auto-manage, so mismatches are the commissioner's worklist.

    Contract is PER ROSTER COPY, not per player (verified live 2026-07-12: a
    post-draft FA signing gave 3 players '1st' in one conference and 'FA' in
    the other), so rostered actions target one team's copy and FA actions the
    pool copy:

      - rostered copy, eligible, contract != Minor  -> set Minor (that team)
      - rostered copy, !eligible, contract == Minor -> set 1st  (graduation)
      - FA copy (AVAILABLE bucket), contract != Minor -> set Minor
      - vanished: eligible last snapshot, now in NEITHER pull -> set FA
        (graduated while in the pool — invisible to the current-week pulls,
        so it needs the previous fact_minor_eligibility snapshot)

    Contract unknown -> action still emitted, flagged needs_verification."""
    eligible_ids = set(elig["scorer_id"])
    actions, seen = [], set()

    def add(sid, name, team_key, fa_status, current, to_contract, reason,
            needs_verification=False):
        if current == to_contract or (sid, team_key) in seen:
            return
        seen.add((sid, team_key))
        actions.append({
            "scorer_id":          sid,
            "player_name":        name,
            "team_key":           team_key,
            "fa_status":          fa_status,
            "from_contract":      current,
            "to_contract":        to_contract,
            "reason":             reason,
            "needs_verification": needs_verification or current is None,
        })

    # Rostered copies — contract from the roster pull, per (team, scorer).
    for r in placement.itertuples():
        if r.scorer_id in eligible_ids:
            add(r.scorer_id, r.player_name, r.team_key, "taken", r.contract,
                MINOR_CONTRACT, "minors-eligible (site verdict) but not Minor")
        elif r.contract == MINOR_CONTRACT:
            add(r.scorer_id, r.player_name, r.team_key, "taken", r.contract,
                GRADUATE_ROSTERED, "crossed 20 GP — graduate off Minor")

    # FA copies — the AVAILABLE bucket (covers players FA in one conference
    # while rostered in the other; their rostered copy is handled above).
    for r in elig[elig["fa_status"] == "available"].itertuples():
        add(r.scorer_id, r.player_name, None, "available", r.contract,
            MINOR_CONTRACT, "minors-eligible (site verdict) but not Minor")

    # Vanished — eligible last snapshot, absent from BOTH pulls this week:
    # graduated while sitting in the FA pool (or purged from Fantrax). Flagged
    # for verification since it's inferred from history, not a live row.
    if prev_elig is not None:
        rostered_ids = set(placement["scorer_id"])
        for r in prev_elig.itertuples():
            if r.scorer_id not in eligible_ids and r.scorer_id not in rostered_ids:
                add(r.scorer_id, r.player_name, None, "available", r.contract,
                    GRADUATE_FA,
                    "left eligibility while FA — graduated in the pool",
                    needs_verification=True)

    return pd.DataFrame.from_records(
        actions,
        columns=["scorer_id", "player_name", "team_key", "fa_status",
                 "from_contract", "to_contract", "reason", "needs_verification"])


# %%
# ---- Apply mode: replay the worklist through the commissioner edit endpoint ----
# Captured 2026-07-13 (flip-and-revert on A10 with a network listener): the
# roster page's edit = POST `confirmOrExecuteTeamRosterChanges`, TWO-PHASE
# (first with confirm:true, then without), whose `fieldMap` carries the ENTIRE
# team roster keyed by scorer_id: {posId, stId, sal, csId}. csId is the
# contract's smallId from the response's own miscData.contractChoices enum
# (1st=0 ... Minor=8, FA=9) — read live per team, never hardcoded. Because the
# fieldMap is whole-roster, it MUST be rebuilt from a fresh adminMode
# getTeamRosterInfo pull (the Con cell carries {'content','id'}) with only the
# target csIds mutated — replaying stale salaries/statuses would overwrite
# live roster state.
#
# Scope: rostered copies only. FA-copy actions have no fieldMap home; they
# self-correct on signing (the copy lands on a roster -> next weekly diff
# flips it). Opt-in via --apply, NEVER scheduled/unattended (grill sign-off:
# scoped exception to the no-write-side rule). --dry-run prints the planned
# csId mutations without POSTing.
def admin_roster_payload(team_id: str) -> dict:
    """getTeamRosterInfo with adminMode (carries contractChoices + Con cell ids)."""
    return {
        "msgs": [{"method": "getTeamRosterInfo",
                  "data": {"leagueId": CFG.league_id, "teamId": team_id,
                           "adminMode": True}}],
        "uiv": CFG.ui_version,
        "refUrl": f"https://www.fantrax.com/fantasy/league/{CFG.league_id}/team/roster",
        "dt": 0, "at": 0, "tz": CFG.timezone, "v": CFG.api_version,
    }


def build_field_map(data: dict) -> dict:
    """Whole-roster fieldMap verbatim from an adminMode roster response."""
    fm = {}
    for tbl in data.get("tables", []):
        hdr = _header_index(tbl)
        sal_i, con_i = hdr.get("Sal"), hdr.get("Con")
        for r in tbl.get("rows", []):
            sid = (r.get("scorer") or {}).get("scorerId")
            if not sid or r.get("statusId") == EMPTY_SLOT_STATUS:
                continue
            cells = r.get("cells", [])
            fm[sid] = {
                "posId": str(r.get("posId")),
                "stId":  str(r.get("statusId")),
                "sal":   cells[sal_i].get("content") if sal_i is not None else None,
                "csId":  cells[con_i].get("id") if con_i is not None else None,
            }
    return fm


def edit_payload(team_id: str, period, field_map: dict, confirm: bool) -> dict:
    data = {
        "rosterLimitPeriod": period,
        "fantasyTeamId": team_id,
        "daily": False,
        "adminMode": True,
        "applyToFuturePeriods": True,
        "fieldMap": field_map,
    }
    if confirm:
        data["confirm"] = True
    return {
        "msgs": [{"method": "confirmOrExecuteTeamRosterChanges", "data": data}],
        "uiv": CFG.ui_version,
        "refUrl": f"https://www.fantrax.com/fantasy/league/{CFG.league_id}/team/roster",
        "dt": 0, "at": 0, "tz": CFG.timezone, "v": CFG.api_version,
    }


def _resp_errors(raw) -> list:
    """Collect error-looking codes anywhere in an fxpa response (HTTP 200 is
    not success — repo standing rule)."""
    errs = []

    def walk(n):
        if isinstance(n, dict):
            code = str(n.get("code", ""))
            if "ERROR" in code.upper() and code != "WARNING_NOT_LOGGED_IN":
                errs.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(raw)
    return errs


def apply_worklist(dry_run: bool = True, team_keys: list[str] | None = None,
                   max_teams: int | None = None) -> None:
    """Apply the current review_contract_actions.csv to Fantrax, one team at a
    time: fresh adminMode roster pull -> mutate target csIds -> confirm ->
    execute -> re-pull and verify. Rostered, verified actions only."""
    from playwright.sync_api import sync_playwright

    wl_path = Path(CFG.data_dir) / "review" / WORKLIST_CSV
    wl = pd.read_csv(wl_path)
    wl = wl[(wl["fa_status"] == "taken") & wl["team_key"].notna()
            & (~wl["needs_verification"].astype(bool))]
    skipped_fa = (pd.read_csv(wl_path)["fa_status"] == "available").sum()
    if team_keys:
        wl = wl[wl["team_key"].isin(team_keys)]
    teams = _team_ids(CFG)
    id_by_key = dict(zip(teams["team_key"], teams["fantrax_team_id"]))
    grouped = list(wl.groupby("team_key"))
    if max_teams:
        grouped = grouped[:max_teams]
    print(f"[info] applying {sum(len(g) for _, g in grouped)} actions across "
          f"{len(grouped)} team(s); {skipped_fa} FA-copy actions skipped "
          f"(no roster fieldMap; self-correct on signing)"
          f"{' [DRY RUN]' if dry_run else ''}")

    scraper = fx.FantraxScraper(CFG)
    failures = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            CFG.user_data_dir, headless=CFG.headless)
        page = ctx.new_page()
        page.set_default_timeout(CFG.nav_timeout_ms)
        first_team = True
        for team_key, g in grouped:
            team_id = id_by_key.get(team_key)
            if not team_id:
                failures.append((team_key, "no fantrax_team_id")); continue
            if not first_team:
                _pause(PULL_DELAY_S if dry_run else APPLY_TEAM_DELAY_S)
            first_team = False
            raw = _post_healed(scraper, ctx, page,
                               admin_roster_payload(team_id), "getTeamRosterInfo")
            d = raw["responses"][0]["data"]
            cs_by_name = {c["name"]: c["smallId"]
                          for c in d.get("miscData", {}).get("contractChoices", [])}
            period = d.get("displayedSelections", {}).get("displayedPeriod", 1)
            fm = build_field_map(d)

            changes = []
            for a in g.itertuples():
                target_cs = cs_by_name.get(a.to_contract)
                cur = fm.get(a.scorer_id)
                if target_cs is None or cur is None:
                    failures.append((team_key, f"{a.player_name}: "
                                     f"{'unknown contract ' + a.to_contract if target_cs is None else 'not on roster pull'}"))
                    continue
                if cur["csId"] == target_cs:
                    continue     # already compliant on-site
                changes.append((a.scorer_id, a.player_name, cur["csId"], target_cs))

            if not changes:
                print(f"[skip] {team_key}: nothing to change"); continue
            print(f"[team] {team_key}: {len(changes)} change(s)")
            for sid, name, frm, to in changes:
                print(f"    {name} ({sid}): csId {frm} -> {to}")
            if dry_run:
                continue

            for sid, _, _, to in changes:
                fm[sid]["csId"] = to
            confirm = _post_healed(scraper, ctx, page,
                                   edit_payload(team_id, period, fm, True),
                                   "confirm roster changes")
            errs = _resp_errors(confirm)
            if errs:
                failures.append((team_key, f"confirm errors: {errs[:2]}")); continue
            execute = _post_healed(scraper, ctx, page,
                                   edit_payload(team_id, period, fm, False),
                                   "execute roster changes")
            errs = _resp_errors(execute)
            if errs:
                failures.append((team_key, f"execute errors: {errs[:2]}")); continue

            # verify: re-pull and compare the targets' Con ids.
            chk = _post_healed(scraper, ctx, page,
                               admin_roster_payload(team_id), "verify roster")
            fm_after = build_field_map(chk["responses"][0]["data"])
            bad = [(sid, name) for sid, name, _, to in changes
                   if fm_after.get(sid, {}).get("csId") != to]
            if bad:
                failures.append((team_key, f"verify mismatch: {bad}"))
            else:
                print(f"[ok] {team_key}: {len(changes)} contract(s) updated + verified")
        ctx.close()

    if failures:
        print(f"\n[warn] {len(failures)} failure(s):")
        for t, msg in failures:
            print(f"  {t}: {msg}")
    else:
        print("\n[ok] apply complete, no failures")


# %%
# ---- FA path: commissioner CSV import ------------------------------------------
# FA copies have no roster fieldMap, so --apply can't touch them. The chosen
# route (grill sign-off 2026-07-13) is Fantrax's commissioner contract
# CSV-import tool. Column shape below is a sensible default (player identity +
# target contract + salary) pending discovery of the tool's exact expected
# headers in League Admin — iterate once against a real upload.
def export_fa_csv() -> Path:
    """Write data/review/fa_contract_import.csv: the worklist's FA-copy actions
    joined to the latest eligibility snapshot for salary/position/NFL team."""
    review_dir = Path(CFG.data_dir) / "review"
    wl = pd.read_csv(review_dir / WORKLIST_CSV)
    fa = wl[wl["fa_status"] == "available"].copy()

    elig_path = Path(CFG.data_dir) / f"{ELIGIBILITY_FACT}.parquet"
    if elig_path.exists():
        elig = pd.read_parquet(elig_path)
        latest = elig[elig["capture_date"] == elig["capture_date"].max()]
        fa = fa.merge(
            latest[["scorer_id", "position_raw", "nfl_team", "salary"]],
            on="scorer_id", how="left")
    else:
        fa[["position_raw", "nfl_team", "salary"]] = None
    fa["salary"] = pd.to_numeric(fa["salary"], errors="coerce").astype("Int64")

    out = fa.rename(columns={
        "player_name":  "Player",
        "position_raw": "Position",
        "nfl_team":     "Team",
        "salary":       "Salary",
        "to_contract":  "Contract",
        "scorer_id":    "FantraxID",
    })[["Player", "Position", "Team", "Salary", "Contract", "FantraxID"]]
    path = review_dir / FA_IMPORT_CSV
    out.to_csv(path, index=False)
    print(f"[ok] {len(out)} FA contract rows -> {path}")
    return path


# %%
# ---- Main -----------------------------------------------------------------------
def run() -> pd.DataFrame:
    from playwright.sync_api import sync_playwright

    week = fx.derive_week_label(CFG)
    season = CFG.snapshot_season
    scraper = fx.FantraxScraper(CFG)
    teams = _team_ids(CFG)
    print(f"[info] season={season} week={week} teams={len(teams)}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            CFG.user_data_dir, headless=CFG.headless,
        )
        page = ctx.new_page()
        page.set_default_timeout(CFG.nav_timeout_ms)
        elig_pulls = fetch_eligibility(scraper, ctx, page)
        rosters = fetch_rosters(scraper, ctx, page, teams)
        ctx.close()

    # Raw audit files (data/raw is gitignored).
    elig_path = Path(CFG.raw_dir) / f"fantrax_minor_eligibility_{season}_wk{week}.json"
    elig_path.write_text(json.dumps(elig_pulls, indent=2), encoding="utf-8")
    roster_path = Path(CFG.raw_dir) / f"fantrax_rosters_{season}_wk{week}.json"
    roster_path.write_text(json.dumps(rosters, indent=2), encoding="utf-8")
    print(f"[ok] raw -> {elig_path.name}, {roster_path.name}")

    elig = eligibility_to_frame(elig_pulls)
    placement = rosters_to_frame(rosters, teams, season, week)
    if len(placement):
        path = load_placement(placement, CFG)
        print(f"[ok] placement snapshot {len(placement)} rows -> {path}")
        sections = placement["roster_section"].value_counts().to_dict()
        print(f"[info] roster sections seen: {sections}")
    else:
        print("[warn] placement frame empty — inspect the raw roster JSON schema")

    n_av = (elig["fa_status"] == "available").sum() if len(elig) else 0
    print(f"[info] minors-eligible: {len(elig)} ({n_av} FA, {len(elig) - n_av} rostered)")

    # Vanish detection needs LAST week's snapshot — read it before landing this week's.
    prev = prev_eligibility(CFG, season, week)
    elig_fact_path = load_eligibility(elig, CFG, season, week)
    print(f"[ok] eligibility snapshot -> {elig_fact_path}")

    worklist = build_worklist(elig, placement, prev)
    review_dir = Path(CFG.data_dir) / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    out_csv = review_dir / WORKLIST_CSV
    worklist.to_csv(out_csv, index=False)
    print(f"\n[ok] {len(worklist)} contract actions -> {out_csv}")
    if len(worklist):
        print(worklist.groupby(["to_contract", "reason"]).size().to_string())
        if worklist["needs_verification"].any():
            print("[warn] some actions have unknown current contract (grid didn't "
                  "expose a contract column) — verify against the Fantrax UI; "
                  "schema-discovery below shows available headers.")
    return worklist


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Yo-Yo Rule contract compliance")
    ap.add_argument("--apply", action="store_true",
                    help="apply the current worklist to Fantrax (write-side; "
                         "opt-in, never scheduled)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --apply: print planned changes, POST nothing")
    ap.add_argument("--teams", help="with --apply: comma-separated team_keys")
    ap.add_argument("--max-teams", type=int,
                    help="with --apply: stop after N teams (cautious first run)")
    ap.add_argument("--export-fa-csv", action="store_true",
                    help="write data/review/fa_contract_import.csv from the "
                         "worklist's FA-copy actions (commissioner CSV-import "
                         "tool; format iterating against a real upload)")
    args = ap.parse_args()
    if args.export_fa_csv:
        export_fa_csv()
    elif args.apply or args.dry_run:
        apply_worklist(dry_run=args.dry_run,
                       team_keys=args.teams.split(",") if args.teams else None,
                       max_teams=args.max_teams)
    else:
        run()
