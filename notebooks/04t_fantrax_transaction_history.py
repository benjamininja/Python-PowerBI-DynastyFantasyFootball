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
# getTransactionDetailsHistory, data: {leagueId, team, view, maxResultsPerPage,
# pageNumber}}]`. `team: "ALL"` (confirmed live) returns every division in one
# call. **`view` is a required filter, not a default-everything param** --
# confirmed 2026-07-25 via a user-captured HAR of the real UI (Claim/Drop |
# Trade | Lineup tabs each send a different `view` value: `"TRADE"` or
# `"CLAIM_DROP"`). Earlier runs of this script omitted `view` entirely and got
# whatever the account's server-side UI state happened to default to -- one
# run returned only trade rows, a later run only claim/drop rows -- which
# briefly looked like a rolling-window data-loss bug but wasn't: nothing was
# ever windowed out, the query was just scoped to one view at a time. Fix:
# loop both views explicitly. Also adopted from the HAR: `maxResultsPerPage:
# "500"` (string) instead of the unset default (20), to minimize page-loop
# calls; `pageNumber` still pages past whatever cap actually applies, so the
# loop stays correct even if a view's row count exceeds 500 someday.
#
# **Output:** `data/raw/fantrax_txn_history_{season}.json` -- list of verbatim
# per-page API responses across both views (audit/replay; parsed downstream
# by 02d into `fact_roster_transactions` trade/claim/drop events).
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
VIEWS = ("TRADE", "CLAIM_DROP")


def txn_payload(page_number: int, view: str) -> dict:
    return {
        "msgs": [{"method": "getTransactionDetailsHistory",
                  "data": {"leagueId": CFG.league_id, "team": "ALL", "view": view,
                            "maxResultsPerPage": "500", "includeDeleted": False,
                            "pageNumber": page_number}}],
        "uiv": CFG.ui_version,
        "refUrl": TXN_REF_URL,
        "dt": 1, "at": 0,
        "tz": CFG.timezone,
        "v": CFG.api_version,
    }


# %%
def capture() -> list[dict]:
    """POST getTransactionDetailsHistory for team=ALL, once per view in VIEWS,
    page 1..totalNumPages within each view. Self-heals auth like every other
    scraper in this cluster. Returns the flat list of raw per-page responses
    across both views (`responses[0]["data"]` carries `table.rows` +
    `paginatedResultSet`) -- each row's own `transactionCode` field
    (TRADE/CLAIM/DROP) is what downstream parsing branches on, not which
    view fetched it."""
    from playwright.sync_api import sync_playwright

    scraper = fx.FantraxScraper(CFG)

    def _post(ctx, page, page_number, view, what):
        raw = scraper._post_json(ctx, txn_payload(page_number, view), what)
        if scraper._session_dead(raw):
            scraper._login(page)
            raw = scraper._post_json(ctx, txn_payload(page_number, view), what)
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

        for view in VIEWS:
            raw = _post(ctx, page, 1, view, f"getTransactionDetailsHistory {view} p1")
            pages.append(raw)
            total_pages = raw["responses"][0]["data"]["paginatedResultSet"]["totalNumPages"]
            print(f"[info] view={view} totalNumPages={total_pages}")

            for pn in range(2, total_pages + 1):
                pages.append(_post(ctx, page, pn, view, f"getTransactionDetailsHistory {view} p{pn}"))

        ctx.close()

    return pages


# %%
if __name__ == "__main__":
    pages = capture()
    OUT_PATH.write_text(json.dumps(pages, indent=2), encoding="utf-8")
    n_rows = sum(len(pg["responses"][0]["data"].get("table", {}).get("rows", [])) for pg in pages)
    n_sets = len({row.get("txSetId") for pg in pages
                  for row in pg["responses"][0]["data"].get("table", {}).get("rows", [])})
    codes = {}
    for pg in pages:
        for row in pg["responses"][0]["data"].get("table", {}).get("rows", []):
            c = row.get("transactionCode")
            codes[c] = codes.get(c, 0) + 1
    print(f"[ok] captured {len(pages)} page(s), {n_rows} row(s), {n_sets} tx set(s), "
          f"by transactionCode={codes} -> {OUT_PATH}")
