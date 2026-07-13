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
# - `data/review/review_contract_actions.csv` — the commissioner worklist:
#   typed actions (set Minor / set 1st / set FA) with reasons. Structured so a
#   future --apply mode can replay it through Fantrax's contract-edit endpoint.
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
import re
import sys
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
WORKLIST_CSV = "review_contract_actions.csv"


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
    for filt in ELIGIBILITY_FILTERS:
        pages, page_no = [], 1
        while True:
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
# ---- Diff: site eligibility vs contract types ----------------------------------
def build_worklist(elig: pd.DataFrame, placement: pd.DataFrame) -> pd.DataFrame:
    """The Yo-Yo diff. Site eligibility (the MINOR_FANTASY_* pulls) is the truth
    for who SHOULD hold a Minor contract; contract type is what Fantrax does NOT
    auto-manage, so mismatches are the commissioner's worklist:

      - eligible & contract != Minor            -> set Minor
      - rostered & contract == Minor & !eligible -> set 1st (graduation)
      - FA       & contract == Minor & !eligible -> set FA  (graduation to pool)

    Contract unknown (grid doesn't expose the column) -> action still emitted,
    flagged needs_verification, so the worklist is useful from run one."""
    eligible_ids = set(elig["scorer_id"])
    con_by_id, name_by_id, teams_by_id = {}, {}, {}
    for df, has_team in ((placement, True), (elig, False)):
        for r in df.itertuples():
            if r.contract and r.scorer_id not in con_by_id:
                con_by_id[r.scorer_id] = r.contract
            name_by_id.setdefault(r.scorer_id, r.player_name)
            if has_team and r.team_key:
                # duplicate-player league: one owner per conference possible
                teams_by_id.setdefault(r.scorer_id, []).append(r.team_key)

    rostered_ids = set(placement["scorer_id"])
    actions = []

    def add(sid, to_contract, reason):
        current = con_by_id.get(sid)
        if current == to_contract:
            return
        actions.append({
            "scorer_id":          sid,
            "player_name":        name_by_id.get(sid),
            "team_key":           "+".join(sorted(set(teams_by_id.get(sid, [])))) or None,
            "fa_status":          "taken" if sid in rostered_ids else "available",
            "from_contract":      current,
            "to_contract":        to_contract,
            "reason":             reason,
            "needs_verification": current is None,
        })

    # Eligible players must hold Minor, rostered or not.
    for sid in eligible_ids:
        add(sid, MINOR_CONTRACT, "minors-eligible (site verdict) but not Minor")

    # Non-eligible players still holding Minor have graduated.
    for sid, con in con_by_id.items():
        if con == MINOR_CONTRACT and sid not in eligible_ids:
            target = GRADUATE_ROSTERED if sid in rostered_ids else GRADUATE_FA
            add(sid, target, "crossed 20 GP — graduate off Minor")

    return pd.DataFrame.from_records(actions)


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

    worklist = build_worklist(elig, placement)
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
    run()
