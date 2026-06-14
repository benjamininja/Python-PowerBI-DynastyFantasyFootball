# %% [markdown]
# # 04w_fantrax_draft_results  (Playwright — live startup-draft capture)
#
# **Purpose:** Capture the live **startup-draft board** (`getDraftResults`) for
# league `v744203wmmvjqzv6` — the E-step (extract) of the event-sourced
# `fact_roster_transactions` ledger (ADR-0003/0004). The startup is a snake/
# linear DRAFT (not an auction); each completed pick is a `startup_draft`
# acquisition event.
#
# **Why a script (like 04a, not a notebook):** it is re-run repeatedly **during
# the live draft** (between picks) to refresh availability for the 05a board, and
# it drives a headless Playwright session — same operational shape as
# `04a_fantrax_weekly_scrape.py`. Auth is **reused** from 04a's proven scraper
# (persistent `.pw_profile`, server-verdict re-login) — no duplicated login code.
#
# **Request (recovered from the 2026-06-14 /draft-results HAR):** POST
# `fxpa/req?leagueId=...` with `msgs = [getDraftResults, getFantasyLeagueInfo,
# getRefObject(FantasyDraftPickType)]`. The draft board itself is served via a
# service worker, so a DevTools HAR cannot persist its body — we fetch it
# directly through the authenticated request context instead.
#
# **Outputs:**
# - `data/raw/fantrax_draftresults_{season}.json` — verbatim API response
#   (audit/replay; the schema source for the ledger parse). data/raw is gitignored.
#
# **Run:**
#   pip install playwright python-dotenv && playwright install chromium
#   # first run only, to clear any Cloudflare/captcha gate:
#   #   set CFG.headless = False  (or run 04a once headful — same profile)
#   python notebooks/04w_fantrax_draft_results.py
#
# Identity (downstream, in the parse step — not here): player `scorerId ->
# gsis_id/player_key` via `dim_fantrax_crosswalk` (04z); team `teamId ->
# team_key` via `dim_fantasy_teams.fantrax_team_id` (01c, ADR-0005).

# %%
import importlib
import json
import sys
from pathlib import Path

# ---- Reuse 04a's authenticated scraper (auth, persistent profile, retry) -----
# 04a is the single source of truth for the Fantrax session. Import it by file
# (leading-digit module name -> importlib, not a bare `import`). It lazy-imports
# Playwright, so importing here is safe even where Playwright isn't installed.
for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "04a_fantrax_weekly_scrape.py").exists():
        sys.path.insert(0, str(_p))
        break
fx = importlib.import_module("04a_fantrax_weekly_scrape")
CFG = fx.CFG  # league_id, endpoint, ui_version, timezone, user_data_dir, raw_dir, snapshot_season

# %%
# ---- Request payload (from the /draft-results HAR, 2026-06-14) ---------------
# getDraftRanks (04a) used api_version 182.4.8; the draft-results page sent
# 183.1.5. Bump this when Fantrax updates the UI (the 'v' field).
DRAFT_API_VERSION = "183.1.5"
DRAFT_REF_URL = f"https://www.fantrax.com/fantasy/league/{CFG.league_id}/draft-results"


def draft_results_payload(division_id: str | None = None) -> dict:
    """Exact getDraftResults bundle the draft-results page POSTs. getDraftResults
    = completed picks; getFantasyLeagueInfo = draft/league settings (rounds, etc.);
    getRefObject(FantasyDraftPickType) = pick-type reference (feeds dim_draft_pick).

    The page's own POST sends `data:{}` and the server returns the *caller's*
    division (this is a 2-division / 28-team league: Riddell + Wilson). Pass
    `division_id` to target the other division — the response echoes
    `selectedDivisionId`, which we verify actually switched."""
    draft_data = {"divisionId": division_id} if division_id else {}
    return {
        "msgs": [
            {"method": "getDraftResults", "data": draft_data},
            {"method": "getFantasyLeagueInfo", "data": {}},
            {"method": "getRefObject", "data": {"type": "FantasyDraftPickType"}},
        ],
        "uiv": CFG.ui_version,
        "refUrl": DRAFT_REF_URL,
        "dt": 1, "at": 0,
        "tz": CFG.timezone,
        "v": DRAFT_API_VERSION,
    }


def _filled(resp: dict) -> int:
    """Count picks that have been made (carry a scorerId) in a response."""
    picks = resp["responses"][0]["data"].get("draftPicksOrdered", [])
    return sum(1 for p in picks if p.get("scorerId"))


# %%
# ---- Capture -----------------------------------------------------------------
def capture() -> dict:
    """POST the draft-results bundle for **every division** via 04a's authenticated
    request context (28-team league = 2 divisions; one call returns only the
    caller's). Self-heals auth like 04a's fetch(). Writes one raw file per division
    (`fantrax_draftresults_{season}_{divisionId}.json`); the ledger parse reads all
    of them (each pick carries its own `divisionId`/`teamId`). Returns the default
    response (carries the `divisions` list)."""
    from playwright.sync_api import sync_playwright

    scraper = fx.FantraxScraper(CFG)

    def _post(ctx, page, division_id=None, what="getDraftResults"):
        payload = draft_results_payload(division_id)
        raw = scraper._post_json(ctx, payload, what)
        if scraper._session_dead(raw):
            scraper._login(page)
            raw = scraper._post_json(ctx, payload, what)
            if scraper._session_dead(raw):
                ctx.close()
                raise RuntimeError(
                    "Still WARNING_NOT_LOGGED_IN after login. Check .env creds, or "
                    "run once with CFG.headless=False to clear a Cloudflare/captcha "
                    "gate (see data/raw/login_debug.png)."
                )
        return raw

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            CFG.user_data_dir, headless=CFG.headless,
        )
        page = ctx.new_page()
        page.set_default_timeout(CFG.nav_timeout_ms)

        # 1) default call — also tells us the full division list.
        default = _post(ctx, page)
        ddata = default["responses"][0]["data"]
        divisions = ddata.get("divisions", [])
        default_div = ddata.get("selectedDivisionId")
        print(f"[info] divisions: {[(d.get('name','').strip(), d.get('id')) for d in divisions]}")
        print(f"[info] default division: {default_div}")

        # 2) one call per division (explicit divisionId), saved per-division.
        seen = {}
        for d in divisions:
            did = d.get("id")
            raw = default if did == default_div else _post(ctx, page, did)
            got = raw["responses"][0]["data"].get("selectedDivisionId")
            out = Path(CFG.raw_dir) / f"fantrax_draftresults_{CFG.snapshot_season}_{did}.json"
            out.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            flag = "" if got == did else f"  ⚠ server returned {got}, not {did} (divisionId param ignored?)"
            print(f"[ok] {d.get('name','').strip():10} {did} -> {out.name} | picks made: {_filled(raw)}{flag}")
            seen[did] = got
        ctx.close()

    if len(set(seen.values())) < len(seen):
        print("[warn] divisions did not all switch — the `divisionId` param may be "
              "wrong. Fallback: switch the division in the Fantrax draft-results UI "
              "and re-run, or capture each division's HAR separately.")
    return default


# %%
if __name__ == "__main__":
    raw = capture()
    print("\n=== RESPONSE SCHEMA (top levels, default division) ===")
    fx.summarize_schema(raw, max_depth=4)
    resps = raw.get("responses", [])
    print(f"\n[info] {len(resps)} msg responses")
    for j, r in enumerate(resps):
        d = r.get("data")
        keys = list(d.keys()) if isinstance(d, dict) else type(d).__name__
        print(f"  responses[{j}].data: {keys}")
