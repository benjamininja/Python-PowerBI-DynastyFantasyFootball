---
name: mouserat-trade-bud
description: New trade-diagnostic subproject (mouserat_trade-bud/) — architecture decisions and build status, grilled 2026-07-17
metadata:
  type: project
---

## What / why

New trade-decision tool for the 28-team IDP dynasty league, requested
2026-07-17. Jumping-off point: [Spunkylysis/hod-decision-engine](https://github.com/Spunkylysis/hod-decision-engine)
(a baseball keeper-league app — single static HTML/JS talking directly to
Supabase, fed by an external ETL; 3-step wizard: Configure/Connect → Owner
Profiles trade-psychology questionnaire → Analysis with rotisserie-category
gap table + Pareto-efficiency trade diagnostic + Kahneman/Thaler bias
framing). Explicitly a jumping-off point, not a clone target — grilled
through a full redesign to fit points-based IDP dynasty football instead of
category-based (roto) baseball.

**Full plan (context, all 12 grilled decisions, 3-slice implementation
shape, verification steps) is written to**
`C:\Users\benha\.claude\plans\critically-review-our-graceful-nebula.md`
**— approved by the user 2026-07-17.** That plan file is the source of
truth for implementation; this memory entry is a pointer + the decisions
condensed, so a future session doesn't have to re-derive them if the plan
file itself is ever cleaned up.

## Key decisions (condensed — see plan file for full rationale)

1. **Location**: `mouserat_trade-bud/` subfolder **inside this repo**, not a
   separate repo — avoids cross-repo data coupling, direct in-repo imports
   of `data/*.parquet` and `discord_bot/capmath.py`.
2. **Backend**: local FastAPI app under `mouserat_trade-bud/backend/`, reads
   this repo's parquet directly + imports `capmath.py` (no reimplementing
   cap logic). Supabase is a deliberate later migration, not v1.
3. **Frontend**: single dependency-free static HTML file (no build step),
   calling local FastAPI endpoints.
4. **Need/surplus signal = positional strength**, not category gap (baseball
   roto categories have no football analog). Per position (offense + IDP
   DL/LB/DB), rank team vs league; surplus = strong end, need = weak end of
   the same ranking.
5. **Time horizon = one stance field**: **Contending / Balanced /
   Future-Focused** — replaces both the reference app's "Philosophy" and
   confusing single-season "Target year" fields.
6. **Stance auto-inferred** (roster age-curve + standings), pre-selected in
   UI, one-click override — reduces setup friction by design (pre-set
   buttons encourage use, per user's own read of the reference app).
7. **Cap tightness** = separate inferred signal → feeds a **risk threshold**
   dimension, does NOT factor into the stance calculation.
8. **Two profile modes only**: My Profile + Counterparty (both
   auto-inferred + override). Reference app's third "Unknown Owner" mode
   collapses into a helper panel shown only for low-confidence fields on a
   Counterparty (not a top-level mode).
9. **Draft picks are first-class tradeable assets** alongside players —
   deliberate scope expansion beyond the (player-only) baseball reference;
   user was emphatic this is core to the "fun"/GM feel of the league.
10. **Pick valuation = new `dim_pick_value_curve` table** (revised
    2026-07-17 — see plan file for full reasoning). Both KTC RDP and
    DraftSharks publish generic (year, round[, tier]) bucket values, not
    per-team/slot values, so they can't resolve to a specific
    `dim_draft_pick` row and don't belong in the player-identity
    `fact_dynasty_ranking_metrics` EAV. New small reference table instead:
    grain `(snapshot_date, source_name, draft_year, round, tier)` — KTC
    gives 3 tiers/round (Early/Mid/Late), DraftSharks gives 1 flat
    value/round for future years (skip its current year — already drafted).
    Cross-source blending + resolving a real pick to a curve value is a
    Slice 2 concern. Two deferred notes: (a) forecasting angle — correlate
    KTC devy/rookie-rank data to pick value pre-draft; (b) both source
    charts are built on a 12-team grid vs our 28-pick rounds — Slice 2 must
    fit/interpolate.
11. **Player asset value for Pareto math** = existing blended dynasty
    ranking value (not raw season points) — consistent with pick valuation.
12. **No persistence in v1** — profiles are ephemeral/session-only,
    deliberately deferred (the reference app's Save button was broken/silent
    -fail; rather than inherit that surface, v1 just doesn't have it).

## Build status

Plan approved 2026-07-17. **Slice 1 done (2026-07-17)**:
`notebooks/04d_draftpick_value_curve.ipynb` scrapes KTC RDP + DraftSharks
dynasty-TE-premium-superflex into `data/dim_pick_value_curve.parquet`
(46 rows on first run: KTC 2026/2027/2028 × 4 rounds × 3 tiers minus gaps,
DraftSharks 2027/2028 × 5 rounds flat). Registered in `notebooks/README.md`
and `.claude/memory/data-model.md`. Ran clean end-to-end via
`.venv/Scripts/python.exe -m jupyter nbconvert --execute` (PATH must have
`.venv/Scripts` first, or the kernel launches under anaconda's python and
`thefuzz` import fails — anaconda base lacks it).

Design note: decision #10 was **revised mid-Slice-1** after pulling both
source pages directly — see the plan file's decision #10 for the full
reasoning (both sources publish generic year/round bucket values, not
per-team/slot values, so a new `dim_pick_value_curve` table replaced the
originally-planned EAV rows in `fact_dynasty_ranking_metrics`).

**Slice 2 done (2026-07-17)**: `mouserat_trade-bud/backend/` — FastAPI app
(`main.py`, `data_access.py`, `pick_value.py`, `positional_strength.py`,
`profiles.py`, `pareto.py`, `routers/{teams,positional,assets,trade}.py`).
Booted locally (`uvicorn main:app --port 8420`) and smoke-tested against
real data for team A09: `/teams`, `/teams/{k}/profile?mode=my|counterparty`,
`/teams/{k}/positional-strength`, `/teams/{k}/assets`,
`POST /trade/evaluate` all returned correct-shaped results.

Two more data gaps surfaced and resolved mid-slice (same plan-gate pattern
as Slice 1's pick-value pivot):

- **No blended cross-source player value existed** (only KTC has a raw
  `value` metric; DynastySharks/FantasyPros only have ranks). User chose to
  build the blend now: `data_access.player_blended_values(fmt)` converts
  each source's `*_overall_rank` to a within-source percentile and averages
  available sources — same 0-100 scale used for pick values, so Pareto math
  compares players and picks directly.
- **No forward-looking pick ledger exists** — `dim_draft_pick` only holds
  the completed 2026-2027 draft; `fact_roster_transactions` has exactly one
  `event_type` (`startup_draft`), no pick-trade feed, even though Fantrax's
  live platform may already have pick trading enabled/used (confirmed via a
  second scan at the user's request — nothing in this repo's data reflects
  it). `data_access.draft_pick_inventory()` synthesizes a 2027/2028,
  rounds 1-5, one-per-team baseline (`is_synthetic=True`,
  `original_owner == current_owner`) as a placeholder. **A real Fantrax
  pick-trade ETL source is a concrete future Slice-1-style task**, not yet
  scoped.

`positional_strength.py` mirrors `discord_bot/rankings.py`'s established
format-scoping convention (SF for offense QB/RB/WR/TE, IDP/FantasyPros-only
for DL/LB/DB) rather than inventing a new one. `profiles.py`'s stance
inference is age-curve only — **no `fact_standings`/wins table exists in
this repo**, so decision #6's "age-curve + standings" is age-curve only
until that data is ETL'd (another future gap, not blocking).

`data_access.py` imports `discord_bot/capmath.py` for cap math per decision
#2, but had to monkeypatch its module-level `fetch_parquet` (which normally
hits the GitHub Contents API — the bot's deploy target has no local repo
checkout) to a local parquet reader, since this backend runs inside the
repo and should never make a network call for its own data.

New file `mouserat_trade-bud/backend/requirements.txt` (fastapi, uvicorn,
httpx, pandas, pyarrow) — installed into the repo's `.venv` directly
(mirrors `discord_bot/requirements.txt`'s own-tracked-list pattern, not
merged into root `requirements.txt` since this is a separate runtime
lifecycle, not part of the ETL pipeline).

**Slice 3 done (2026-07-17)**: `mouserat_trade-bud/frontend/index.html` —
single dependency-free static file (dark theme, card/chip styling per
decision #3), calling the Slice 2 endpoints above directly via `fetch`.
Two-step flow (Owner Profiles → Analysis) exactly as scoped: profile step
has My/Counterparty team pickers with stance chips pre-selected from the
backend's inference and a one-click override; the counterparty's
low-confidence-fields helper panel renders only for that mode (decision #8).
Analysis step shows both teams' positional-strength tables
(surplus/neutral/need tags), a give/receive asset picker mixing players and
picks (decision #9), and a live Pareto bar + plain-language diagnostic
("favors my team / counterparty by X%") on every basket change.

**Not yet done — visual/browser verification.** No browser automation tool
was available this session; only did an API-level smoke test (booted
`uvicorn main:app --port 8420`, curled `/trade/evaluate` with a real
player+pick payload — correct response). **Someone needs to actually open
`mouserat_trade-bud/frontend/index.html` in a browser against the running
backend and click through both steps** before calling v1 done — this is
explicitly unverified, not confirmed working end-to-end as a UI.

**Next action**: open the frontend in a browser and walk the golden path
(pick My Team + Counterparty → Analysis → build a give/receive basket →
confirm the Pareto bar/diagnostic update). Also on the punch list for a
real Slice 2 follow-up (not urgent): a real Fantrax future-pick-trade ETL
source to replace the synthetic pick inventory, and a `fact_standings`
table so stance inference can use standings as decision #6 originally
intended.
