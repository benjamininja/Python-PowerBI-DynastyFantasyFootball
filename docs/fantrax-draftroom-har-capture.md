# Fantrax draft-room HAR capture (gating prerequisite for the ledger build)

This is the **user-owned** capture step that unblocks the
`fact_roster_transactions` ledger build (ADR-0003/0004). We need the real
request/response shapes of the live draft-room endpoints — the exact method
names are unknown, which is why we capture rather than guess.

> **Security:** a HAR "with content" contains your Fantrax **session cookies**.
> Save only under `data/raw/` (already gitignored). **Never commit it.** Do not
> paste the cookie/token values into chat — the JSON response bodies are what we
> need, not the auth headers.

## What we need

Two endpoints, both POSTs to the same fxpa gateway used by
[04a](../notebooks/04a_fantrax_weekly_scrape.py):
`https://www.fantrax.com/fxpa/req?leagueId=v744203wmmvjqzv6`

| # | Purpose | Likely method (confirm via capture) | Feeds |
|---|---|---|---|
| A | **Completed draft picks** — who drafted whom, at which pick/round, ideally salary-at-pick | `getDraftResults` / `getDraftRoom` / `getLiveDraft*` (unknown) | `fact_roster_transactions` (`startup_draft` events) |
| B | **Pick inventory / draft order** — each team's owned picks by round/season | `draftPicks.go` (per ADR-0004; may be a `.go` servlet, not fxpa) | `dim_draft_pick` + `pick_allocation` events |

For each we need: the **request payload** (`msgs[].method` + its `data` object)
and the **full response JSON**.

## Steps (Chrome/Edge DevTools)

1. Log into Fantrax; open league `v744203wmmvjqzv6`.
2. `F12` → **Network** tab. Check **Preserve log**. Filter to **Fetch/XHR**
   (or type `req` in the filter box).
3. Open the **Draft Room / Draft Results** view (the board of completed picks).
   Let it load; scroll so all picks render. Then open the **Draft Picks / future
   picks** view (the per-team pick inventory).
4. In the Network list, find the POSTs to `fxpa/req` (and any `*.go` request the
   picks view fires). Click each:
   - **Payload** tab → note `msgs[0].method` and its `data`.
   - **Response** tab → confirm it carries the picks/inventory.
5. Save the bodies (either approach):
   - **Per-response (preferred, no cookies):** right-click the request →
     *Copy → Copy response* → paste into a file:
     - draft results → `data/raw/fantrax_getDraftResults_sample.json`
     - pick inventory → `data/raw/fantrax_draftPicks_sample.json`
     - Also record each request's `method` + `data` in a one-line comment or a
       `data/raw/fantrax_draftroom_payloads.txt`.
   - **Full HAR (has cookies — keep local):** right-click anywhere in Network →
     *Save all as HAR with content* → `data/raw/fantrax_draftroom_<YYYYMMDD>.har`.

## Hand-off

Tell the assistant the saved filenames (and the confirmed method names). The
build then proceeds: `dim_season` → `dim_roster_asset`/`dim_draft_pick` →
`fact_roster_transactions` parse → `fact_fantasy_teams` derivation + 05a
availability join. See `PLAN.md` → "GRILL 2026-06-14 — v1 scope RESOLVED".
