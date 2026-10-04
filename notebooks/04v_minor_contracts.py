# %% [markdown]
# # 04v_minor_contracts  (Playwright, weekly — Minors eligibility)
#
# **Purpose:** Weekly read-only snapshot of Minors **eligibility**. The Minors
# system is made of two things (ADR-0011), eligibility and placement, and this
# script captures the first only.
#
# - *Eligibility* — career+current regular-season GP <= 19, computed by Fantrax
#   itself (league setting: "Career+Current regular season total GP <= 19", both
#   Offense and Individual Defense). This script READS the site's verdict; it
#   does not re-derive it.
# - *Placement* — the Roster Slot each roster copy sits in (Starter / Bench /
#   IR / Minors). Placement is the team's own lever and is what the cap
#   exemption follows. Not captured here: `04r` reads it from the public API
#   into `fact_roster_state`, along with each copy's contract and salary.
#
# **`Minor` is a contract stage, and it is read, never derived (ADR-0019).** A
# minors-eligible player holds `Minor`, the stage before `1st`; Fantrax moves
# them to `1st` once they pass the games-played limit. This script never works
# a contract out. Placement is a separate lever: eligibility permits a team to
# *place* a player in the Minors squad, and only that placement is cap-exempt.
#
# An earlier design gave this script an eligibility-vs-contract diff, a
# commissioner worklist and a write-side `--apply` path. All three were retired
# (ADR-0011) and stay retired: Fantrax sets the contract itself, so there is
# nothing left to reconcile.
#
# This script is therefore READ-ONLY and makes no write-side calls to Fantrax.
#
# **One pull per run (via 04a's authenticated scraper):** `getPlayerStats` with
# `statusOrTeamFilter=MINOR_FANTASY_AVAILABLE|MINOR_FANTASY_TAKEN` (the
# players-page filter): Fantrax's own list of minors-eligible players, split
# FA vs rostered.
#
# **Outputs:**
# - `data/raw/fantrax_minor_eligibility_{season}_wk{NN}.json` — raw filter pulls
# - `data/fact_minor_eligibility.parquet` — weekly eligibility snapshot,
#   replace-by-(season, week), for week-over-week history of the eligible
#   population. Every row of a run carries the same `capture_date`.
#
# **Read by:** `02d`, for the `Minor` default on a Roster Move that no Roster
# State row covers (ADR-0019 decision 6).
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

# Header shortNames that may carry the contract type on the players grid.
# "Con" verified against the first real payloads.
CONTRACT_HEADER_CANDIDATES = ("Con", "Contract", "Ctr", "Ct")

ELIGIBILITY_FACT = "fact_minor_eligibility"

# Pacing: jittered sleeps so the run reads like a human clicking through pages,
# not a burst (there is no other rate limiting anywhere in the Fantrax path).
PULL_DELAY_S = (0.5, 1.5)     # between read pulls (filter pages)


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
# ---- Pull: minors-eligibility filter (players grid) ----------------------------
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
    """shortName -> cell index, off the grid response's `tableHeader`."""
    hdr = data.get("tableHeader") or {}
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
# ---- Durable eligibility snapshot (fact_minor_eligibility) ---------------------
def load_eligibility(df: pd.DataFrame, cfg, season: int, week: str,
                     capture_date: str) -> str:
    """Land the eligibility pull as a parquet fact (replace-by-(season, week)),
    so the eligible population has queryable week-over-week history — the raw
    JSON alone can't answer 'when did this player cross 20 GP'. `capture_date`
    is the run's ISO day, read once by run() and stamped on every row."""
    df = df.assign(season=season, week=week, capture_date=capture_date)
    path = f"{cfg.data_dir}/{ELIGIBILITY_FACT}.parquet"
    if Path(path).exists():
        old = pd.read_parquet(path)
        keys = set(map(tuple, df[["season", "week"]].drop_duplicates().to_numpy()))
        mask = old[["season", "week"]].apply(tuple, axis=1).isin(keys)
        df = pd.concat([old[~mask], df], ignore_index=True)
    df = df.drop_duplicates(subset=["scorer_id", "season", "week"], keep="last")
    df.to_parquet(path, index=False)
    return path


# ---- Main -----------------------------------------------------------------------
def run() -> pd.DataFrame:
    """Pull the eligibility lists and land the snapshot. Read-only."""
    from playwright.sync_api import sync_playwright

    # Read the day once: the week label and every row's capture_date come from
    # it, so a run that crosses midnight still lands one capture_date.
    today = date.today()
    week = fx.derive_week_label(CFG, today)
    season = CFG.snapshot_season
    capture_date = today.isoformat()
    scraper = fx.FantraxScraper(CFG)
    print(f"[info] season={season} week={week} capture_date={capture_date}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            CFG.user_data_dir, headless=CFG.headless,
        )
        page = ctx.new_page()
        page.set_default_timeout(CFG.nav_timeout_ms)
        elig_pulls = fetch_eligibility(scraper, ctx, page)
        ctx.close()

    # Raw audit file (data/raw is gitignored).
    elig_path = Path(CFG.raw_dir) / f"fantrax_minor_eligibility_{season}_wk{week}.json"
    elig_path.write_text(json.dumps(elig_pulls, indent=2), encoding="utf-8")
    print(f"[ok] raw -> {elig_path.name}")

    elig = eligibility_to_frame(elig_pulls)
    n_av = (elig["fa_status"] == "available").sum() if len(elig) else 0
    print(f"[info] minors-eligible: {len(elig)} ({n_av} FA, {len(elig) - n_av} rostered)")

    elig_fact_path = load_eligibility(elig, CFG, season, week, capture_date)
    print(f"[ok] eligibility snapshot -> {elig_fact_path}")
    return elig


if __name__ == "__main__":
    run()
