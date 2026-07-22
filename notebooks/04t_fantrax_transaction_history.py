# %% [markdown]
# # 04t_fantrax_transaction_history  (Playwright — trade/transaction event log)
#
# **Purpose:** Capture Fantrax's trade transaction history for league
# `v744203wmmvjqzv6` via the internal `fxpa/req` RPC `getTransactionDetailsHistory`
# -- there is no public REST endpoint for this (confirmed: 6 method-name guesses
# against the public `fxea/general` API all failed -- see
# .claude/memory/mouserat-trade-bud.md Checkpoint 3.5/6). Same reverse-engineered
# JSON-RPC surface as `getDraftRanks` (04a), `getTeamRosterInfo` (04v),
# `getDraftResults` (04w).
#
# **Why a script (like 04a/04u/04v/04w, not a notebook):** drives a Playwright
# session against the authenticated persistent profile -- same operational
# shape as the rest of the Fantrax cluster. Auth is reused from 04a, no
# duplicated login code.
#
# **Request:** POST `fxpa/req?leagueId=...`, `msgs=[{method:
# getTransactionDetailsHistory, data: {leagueId, team, pageNumber}}]`. The page's
# own default omits `team`/`pageNumber` and the server defaults to the viewer's
# own division + page 1 -- `team: "ALL"` (confirmed live against
# `displayedLists.teams`) returns every division, and `pageNumber` pages past
# the `maxResultsPerPage` (20) cap. This script loops team="ALL" across every
# page up to `totalNumPages`.
#
# **Output:** `data/raw/fantrax_txn_history_{season}.json` -- list of verbatim
# per-page API responses (audit/replay; parsed downstream by 02d into
# `fact_roster_transactions` `event_type="trade"` rows).
#
# **Run:** python notebooks/04t_fantrax_transaction_history.py

# %%
import importlib
import json
import sys
from pathlib import Path

for _p in (Path.cwd() / "notebooks", Path.cwd(), Path.cwd().parent):
    if (_p / "04a_fantrax_weekly_scrape.py").exists():
        sys.path.insert(0, str(_p))
        break
fx = importlib.import_module("04a_fantrax_weekly_scrape")
CFG = fx.CFG

TXN_REF_URL = f"https://www.fantrax.com/fantasy/league/{CFG.league_id}/transactions/history"
OUT_PATH = Path(CFG.raw_dir) / f"fantrax_txn_history_{CFG.snapshot_season}.json"


# %%
def txn_payload(page_number: int) -> dict:
    return {
        "msgs": [{"method": "getTransactionDetailsHistory",
                  "data": {"leagueId": CFG.league_id, "team": "ALL", "pageNumber": page_number}}],
        "uiv": CFG.ui_version,
        "refUrl": TXN_REF_URL,
        "dt": 1, "at": 0,
        "tz": CFG.timezone,
        "v": CFG.api_version,
    }


# %%
def capture() -> list[dict]:
    """POST getTransactionDetailsHistory for team=ALL, page 1..totalNumPages.
    Self-heals auth like every other scraper in this cluster. Returns the list
    of raw per-page responses (`responses[0]["data"]` carries `table.rows` +
    `paginatedResultSet`)."""
    from playwright.sync_api import sync_playwright

    scraper = fx.FantraxScraper(CFG)

    def _post(ctx, page, page_number, what):
        raw = scraper._post_json(ctx, txn_payload(page_number), what)
        if scraper._session_dead(raw):
            scraper._login(page)
            raw = scraper._post_json(ctx, txn_payload(page_number), what)
            if scraper._session_dead(raw):
                ctx.close()
                raise RuntimeError(
                    "Still WARNING_NOT_LOGGED_IN after login. Check .env creds, or "
                    "run once with CFG.headless=False to clear a Cloudflare/captcha "
                    "gate (see data/raw/login_debug.png)."
                )
        return raw

    pages = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            CFG.user_data_dir, headless=CFG.headless,
        )
        page = ctx.new_page()
        page.set_default_timeout(CFG.nav_timeout_ms)

        raw = _post(ctx, page, 1, "getTransactionDetailsHistory p1")
        pages.append(raw)
        total_pages = raw["responses"][0]["data"]["paginatedResultSet"]["totalNumPages"]
        print(f"[info] totalNumPages={total_pages}")

        for pn in range(2, total_pages + 1):
            pages.append(_post(ctx, page, pn, f"getTransactionDetailsHistory p{pn}"))

        ctx.close()

    return pages


# %%
if __name__ == "__main__":
    pages = capture()
    OUT_PATH.write_text(json.dumps(pages, indent=2), encoding="utf-8")
    n_rows = sum(len(pg["responses"][0]["data"].get("table", {}).get("rows", [])) for pg in pages)
    n_sets = len({row.get("txSetId") for pg in pages
                  for row in pg["responses"][0]["data"].get("table", {}).get("rows", [])})
    print(f"[ok] captured {len(pages)} page(s), {n_rows} row(s), {n_sets} trade set(s) -> {OUT_PATH}")
