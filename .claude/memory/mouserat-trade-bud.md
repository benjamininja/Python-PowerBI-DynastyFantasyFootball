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

v1 committed to branch `mouserat-trade-bud` (repo, not this app's own repo —
still an in-repo subfolder). Backend static-traced field-by-field against
the frontend's JS (all endpoint response keys match what the JS reads) —
strong signal the wiring is correct, but a real interactive browser
click-through still hasn't happened (no browser tool available in-session
either time). Backend was booted twice this session and died silently
between checks once already — don't assume `http://127.0.0.1:8420` is still
up without a `/health` check first.

## Round 2 (2026-07-18) — plan approved, not yet started

First real (partial) browser look surfaced concrete gaps. Grilled 4 open
decisions, all locked (see full rationale in the plan file — this is the
condensed version):
- **Same-conference trading is a real league rule**, must be backend-enforced
  (400 on cross-conference `/trade/evaluate`), not just a UI filter.
- **Confidence stays advisory-only this round** — no Pareto-math weighting
  yet, that's an explicit future round.
- **Injury tolerance fully deferred** — no data source exists
  (`fact_nfl_season_injuries` via nflreadpy is still just a documented future
  gap, not a spike target this round).
- **`fact_standings` still deferred.**
- **Risk-tolerance inference is NOT solved this round** — user wants it
  grilled as its own future session first (logged as a punch-list item, not
  built).

Full plan (all items, verification steps, execution checkpoints) is in
`C:\Users\benha\.claude\plans\critically-review-our-graceful-nebula.md`
under "Round 2 (2026-07-18)". Condensed shape:

**Phase 0 (repo-wide, do first, unrelated to trade-bud specifically):**
- 0a: generated + drift-checked Mermaid data-model diagram
  (`docs/data_model.yml` SSOT → `scripts/check_data_model.py` → rendered
  `docs/DATA_MODEL.md`, mirroring the existing `docs/sources.yml`/
  `check_sources.py`/ADR-0007 pattern exactly, new pre-commit hook alongside
  `check-sources`). Resolver tables (`dim_fantrax_crosswalk`,
  `dim_dynasty_crosswalk`, `dim_player_alias`, `dim_roster_asset`) render
  distinctly from direct-join tables via a flowchart (`graph LR`, not
  `erDiagram` — needed the styling freedom for dotted "via resolver" edges).
- 0b: `notebooks/00_fantasy_etl_flow.ipynb` — toggle-driven manual/
  future-schedulable orchestrator. Extends `scripts/run_pipeline.py`'s
  existing step model with a new orthogonal `"group"` tag
  (pre_season/rookie/regular_season/injury, independent of its existing
  calendar-based `"phases"`) and a `--group` CLI flag, rather than forking a
  second orchestration mechanism. Rookie toggle stops before the `03y`/`03z`
  human-review gate (matches `run_pipeline.py`'s existing deliberate
  exclusion). Injury toggle is an intentional no-op placeholder — zero
  injury notebooks exist yet.

**Phase A (trade-bud backend, do before Phase B):**
1. Fix `positional_strength.py`'s DL-shows-26/28-teams bug (groupby with no
   reindex silently drops teams with zero rostered players in a position
   group — needs reindex + zero-fill before ranking, so 0 DL depth correctly
   ranks as the strongest "need" signal instead of vanishing).
2. Wire the already-written-but-unused `data_access.player_age()` into
   `routers/assets.py`'s player dict.
3. Route `positional_strength.league_positional_strength()` (already exists,
   never routed) as `GET /positional-strength/league` for a real
   league-wide Positional Overview.
4. Conference trade-rule enforcement: `dim_fantasy_teams.conference`/
   `.division` already exist and are already returned by `GET /teams` — add
   `my_team`/`counterparty_team` to `TradeRequest` and 400 if asset
   ownership or conference doesn't match.
5. **Biggest item**: real Fantrax transaction-history ETL
   (`notebooks/04y_fantrax_transaction_history.py` or next free letter,
   reusing `FantraxScraper` from `04a` — same auth/session, no new auth
   work). Needs a HAR capture to reverse-engineer the `fxpa/req` RPC method
   for the transactions/history page (no public endpoint exists, confirmed).
   Extends `fact_roster_transactions` with `event_type="trade"` rows + a new
   `transaction_id` column to group multi-asset trades. Once real, replaces
   both the synthetic future-pick inventory (`data_access.draft_pick_inventory()`)
   and powers a real `infer_trade_activity()` signal in `profiles.py`.
6. Confidence-tier rework: make `"high"` actually reachable (currently dead
   code — only low/medium ever produced), make `LOW_CONFIDENCE_FIELDS` a
   real computed-per-team list instead of a static 3-item constant.

**Phase B (frontend, only after Phase A verified):**
1. Reconnect/Refresh button (today only re-checks on the `apiBase` field's
   `change` event).
2. Collapse the 2-step wizard into one page (Profiles on top, Analysis
   below, both always visible); both panels get independent team switchers
   (today Analysis is stuck with step-1's picks).
3. Positional Overview section rendering Phase A #3's league-wide endpoint.
4. Conference-filtered Counterparty dropdown (paired with Phase A #4's
   server-side 400 as the real backstop).
5. Real confidence UI once Phase A #6 lands (replace the current
   "ask the owner directly" block, which reads as nonsense today since none
   of those fields were ever actually computed).
6. Build-a-Trade panel: show player age (Phase A #2); relabel baskets from
   generic "Give"/"Receive" to `"{team_name} trades:"` per side.

**Deployment/Discord sharing**: explicitly out of scope for this round —
recommendation logged in the plan (Railway, mirroring `discord_bot`'s
pattern) but not committed to; revisit as its own follow-up later.

**Execution discipline**: the plan file itself has 7 numbered token-gated
checkpoints (target 125k-150k tokens each) with an explicit rule — update
the plan file + this memory file *before* every compact, never mid-item.

## Checkpoint 1 (2026-07-18) — Phase 0 DONE, verified

Both Phase 0 items shipped and pass their own checks clean:

- **0a**: `docs/data_model.yml` (24 tables: 12 dim/4 resolver/8 fact, seeded
  from this repo's data-model.md), `scripts/check_data_model.py`
  (validate/--render/--check, exact `check_sources.py` shape — validate
  cross-checks every declared column+dtype against the real
  `data/{name}.parquet` schema, not just a notebook-token search), generated
  `docs/DATA_MODEL.md` (Mermaid `graph LR`, resolver tables render as
  `{{hexagon}}` nodes, facts as `[(stadium)]`, dashed `-.via <resolver>.->`
  edges vs solid direct edges). `--check` passes clean. New `check-data-model`
  pre-commit hook registered after `check-sources`.
- **0b**: `run_pipeline.py`'s `build_steps()` steps each gained a `"group"`
  key (`pre_season`/`rookie`/`regular_season`), independent of the existing
  `"phases"` set; new `--group` CLI flag (AND-combines with `--phase`/
  `--steps`). Added 4 new rookie-group step entries (`03a`-`03d` only — the
  chain stops before `03x`/`03y`/`03z` exactly like the scheduled path
  already does). `notebooks/00_fantasy_etl_flow.ipynb` is the thin
  front-end: boolean toggles → `--group` arg → `run_pipeline.main()` called
  directly (no second subprocess layer) — smoke-tested via
  `nbconvert --execute`, ran the correct 5-step `regular_season` chain
  end-to-end in dry-run, exit 0.
- **One real bug found+fixed**: `run_pipeline.main()`'s unconditional
  `sys.stdout.reconfigure(...)` crashed under a Jupyter kernel (`OutStream`
  has no `.reconfigure`) — the notebook literally couldn't call `main()`
  without this fix. Guarded with `hasattr(sys.stdout, "reconfigure")`, zero
  behavior change for the real scheduled-script path.

Full per-item detail also recorded in the plan file's Phase 0 section
(`C:\Users\benha\.claude\plans\critically-review-our-graceful-nebula.md`).

Backend liveness is unknown at this point in time — `/health`-check
`http://127.0.0.1:8420` before assuming it's up in a future session.

## Checkpoint 1b (2026-07-18) — Phase A #1 DONE, verified; pausing here

Fixed `mouserat_trade-bud/backend/positional_strength.py`'s
`_team_position_strength()`: reindexed the full `(all_team_keys ×
positions)` cross (fill_value=0) before ranking, instead of ranking only the
groups that happened to exist. Verified directly (ran
`positional_strength.league_positional_strength()` and grouped by
`position_group`): all 7 groups (QB/RB/WR/TE/DL/LB/DB) now show
`n_teams == 28`, 196 total rows. DL's 26/28 was the visible symptom; the bug
was general (any position group with a zero-roster team anywhere would have
silently dropped that team).

**Next action**: Phase A item 2 — wire the already-written
`data_access.player_age(gsis_id, players=None)` (confirmed still present at
`data_access.py:143`, unused) into the player dict `routers/assets.py`'s
`team_assets()` builds, passing the already-loaded `players_dim` frame in to
avoid a re-read per player. Then item 3 (route
`league_positional_strength()` as `GET /positional-strength/league` — trivial
now that #1 makes it return 28/28 by construction). Checkpoint 2 targets
after items 2-3 land.

## Checkpoint 2 (2026-07-18) — Phase A #2-3 DONE, verified; pausing here

- **#2**: `routers/assets.py`'s `team_assets()` now selects `birth_date`
  into `players_dim` and adds `"age": da.player_age(r["gsis_id"],
  players=players_dim)` to each player dict — no re-read per player.
  Verified via a direct call for a real team: returned real float ages
  (e.g. 25.14, 24.76, 22.97...).
- **#3**: `routers/positional.py` gained a second router (`league_router`,
  prefix `/positional-strength`) with `GET /positional-strength/league` ->
  `ps.league_positional_strength().to_dict(orient="records")`; registered in
  `main.py` right after `positional.router`. Verified: 196 rows, exactly 28
  teams per each of the 7 position groups (built directly on #1's fixed
  reindex, so 28/28 by construction, not coincidence).

**Next action**: Phase A item 4 — same-conference trade-rule enforcement.
Add `my_team`/`counterparty_team` fields to `TradeRequest` in
`routers/trade.py`; resolve each give/receive asset's real current owner
(`fact_fantasy_teams.team_key` for players, `draft_pick_inventory()
.current_owner` for picks) and 400 if any give-asset isn't owned by
`my_team`, any receive-asset isn't owned by `counterparty_team`, or the two
teams aren't in the same `conference` (`dim_fantasy_teams.conference`/
`.division` already exist, already returned by `GET /teams` — no new ETL
needed for the check itself). This is Checkpoint 3's target per the plan
file's execution-checkpoint list — a self-contained item, appropriate to
pause after landing given its own dedicated checkpoint slot.

## Checkpoint 3 (2026-07-18) — Phase A #4 DONE, verified; pausing here

- **#4**: `routers/trade.py`'s `TradeRequest` gained `my_team`/
  `counterparty_team` fields. `POST /trade/evaluate` 400s if the two teams
  aren't in the same `conference`, or if any give-asset isn't owned by
  `my_team` / any receive-asset isn't owned by `counterparty_team`.
- **Design correction made mid-implementation (important, re-derive-proof
  this if touching trade ownership again)**: the original plan text said
  "resolve each asset's real current owner" via a `gsis_id -> team_key`
  dict. That's wrong for this league. `fact_fantasy_teams` is a
  **duplicate-player league** roster fact — confirmed via
  `.claude/memory/data-model.md`'s `fact_roster_placement` grain note
  ("duplicate-player league, one copy per conference") and confirmed
  directly against real data: 413 of 522 rostered `gsis_id`s currently
  appear under **two** different `team_key`s (one per conference — the same
  real NFL player is a separate fantasy asset in each conference). A
  last-write-wins dict collapses both valid owners into one and produces
  false "not owned by" rejections. Fixed by making ownership a
  `{(gsis_id, team_key)}` membership set (`_asset_owners()` /
  `_owned_by()` in `routers/trade.py`) instead of a single-valued lookup —
  picks stay a plain dict since `draft_pick_inventory().current_owner` is
  genuinely single-valued (one owner per `pick_ref`).
- Verified with 4 live cases against real parquet data (same-conference
  team pair, cross-conference team pair, a real player + pick asset):
  valid same-conference trade evaluates normally; cross-conference trade
  400s with the conference-mismatch message; a give-asset owned by a
  *different* team than `my_team` 400s with the ownership message; a real
  pick-asset ownership check passes.

**Next action (superseded by Checkpoint 4 findings below — re-read before
resuming)**: Phase A item 5 — Fantrax transaction-history ETL (the
largest, riskiest remaining item). Needs a HAR capture of
`https://www.fantrax.com/fantasy/league/v744203wmmvjqzv6/transactions/history`
to find the `fxpa/req` RPC method + payload shape (same reverse-engineering
approach `04w_fantrax_draft_results.py` already used for draft results — no
public REST endpoint exists for this). New script
`notebooks/04y_fantrax_transaction_history.py` (or next free letter),
importing `FantraxScraper` from `04a_fantrax_weekly_scrape.py` for auth
(same `.pw_profile` persistent session / re-login fallback — do not
reimplement). Extends `fact_roster_transactions` with `event_type="trade"`
rows + a new `transaction_id` column (to group multi-asset trade rows
together — nothing currently links related rows). Per the plan file's
explicit guidance: if the HAR/RPC reverse-engineering runs long, pause at
the natural sub-seam (HAR captured + RPC method identified, before
parsing/writing) rather than forcing a finish to stay in-budget — this is
flagged as the plan's most unpredictable remaining item.

## Checkpoint 4 (2026-07-18) — off-plan detour: Fantrax data-source outage +
a major discovery (public API); paused mid-implementation, NOT DONE

User asked (separately from the Phase A queue above) to run the pipeline to
bring teams up to current and pull existing transactions, to feed the app.
This surfaced a real production break plus a significant new capability —
both must be read before touching Fantrax ETL code again.

**#1 — `04a_fantrax_weekly_scrape.py` is permanently broken post-draft.**
Its entire weekly board pull is built on `getDraftRanks` (the draft-ranking
page). Now that the 2026 startup draft is complete, Fantrax returns, for
this league, `pageError.text: "The draft has already been completed, thus
you can no longer access this page."` — confirmed via the real raw capture
(`data/raw/fantrax_draftranks_2026_wkPRE.json`). This is NOT an auth/session
issue (`_session_dead()` correctly found no `WARNING_NOT_LOGGED_IN` and
didn't retry-login) — Fantrax has retired that page for good. Every
downstream pipeline step gated behind `04a_scrape` in
`scripts/run_pipeline.py`'s `needs` chain (`04z_crosswalk` → `04v` → `02d` →
`02e`) got skipped as a result. **No fix has been implemented for 04a
itself** — still broken, no decision made yet on how/whether to repoint it
(candidate: the Players grid, `getPlayerStats` + a `divisionId` param it
doesn't send today — confirmed working directly against real data for
Riddell (`rhf63kfummvk3jnh`); Wilson is `svxeyvvgmmvk3jnh` — returns
`rankOv`/`age`/`salary`/`contract`/`fpts`/`fptsPerGame`/`status`(owning
team) but NOT a true adp/percent_drafted field, since there's no more draft
market. This repoint is now lower-priority than the public-API path below
and may not be needed at all — revisit only if the public API (#2) doesn't
cover a given field).

**#2 — Immediate workaround, already executed successfully.** Traced
`run_steps()` in `scripts/run_pipeline.py`: a step is only skipped if its
upstream actually ran and *failed* (`status.get(d) in ("failed",
"skipped")`); a step simply absent from `--steps` has no status entry at
all, so the dependency check doesn't block it. Ran
`--steps 04z_crosswalk,04v_minor_contracts,02d_ledger,02e_derive` directly
(skipping the broken `04a_scrape`) — **succeeded end to end**
(04z 16s, 04v 60s, 02d 2s, 02e 1s), on branch `mouserat-trade-bud` so the
commit step auto-skipped (by design — only commits from `main`). This
refreshed `fact_roster_placement`/`fact_roster_transactions`/
`fact_fantasy_teams` off `04v`'s own live `getTeamRosterInfo` pull (a
different, still-working internal RPC) and `04z`'s crosswalk (which only
needs whatever `fact_fantrax_adp` snapshot already exists on disk, not a
fresh one) — **this is the "teams to current + existing transactions"
refresh the user asked for, and it's done, verified, uncommitted.**

**#3 — Major discovery: Fantrax has a public, no-auth REST API** at
`https://www.fantrax.com/fxea/general/*` — confirmed live with plain
`curl`, no session/cookies/login needed at all. Endpoints found by probing:
- `getAdp?sport=NFL` — real, current, global NFL ADP (not league-scoped).
  Could restore a genuine `adp` field for `fact_fantrax_adp` going forward,
  instead of nulling it post-draft.
- `getLeagueInfo?leagueId=v744203wmmvjqzv6` — matchup schedule + team
  names/ids.
- `getDraftPicks?leagueId=v744203wmmvjqzv6` — returns
  `{futureDraftPicks: [...], currentDraftPicks: [...]}`.
  `futureDraftPicks` = 280 rows (28 teams × 5 rounds × 2 years, 2027+2028),
  each `{year, round, currentOwnerTeamId, originalOwnerTeamId}` — **3 of the
  280 already show real trades** (current ≠ original). This is real
  pick-trade ownership with **no HAR/RPC reverse-engineering needed** —
  directly replaces the synthetic future-pick generation in
  `mouserat_trade-bud/backend/data_access.py:102`
  (`draft_pick_inventory()`), which today fabricates one pick per
  team/division/round with `original_owner == current_owner` always (no
  trades reflected) and flags them `is_synthetic=True`. `currentDraftPicks`
  (only 5 rows, oddly-numbered rounds 28/31/32) looked like something
  unrelated to this league's normal round structure — not investigated
  further, low priority.
- `getTeamRosters?leagueId=...` — full per-team roster: `rosterItems` with
  `id` (scorerId), `position`, `salary`, `contract`, `status`
  (ACTIVE/RESERVE/etc). A public no-auth alternative to `04v`'s existing
  internal authenticated `getTeamRosterInfo` pull — value relative to what
  `04v` already provides was **not fully worked out** before this pause;
  don't assume it's needed for anything `04v` doesn't already cover without
  re-checking.
- `getStandings?leagueId=...` — exists; bonus for the still-deferred
  `fact_standings` (not in scope now, just noting it exists).
- **Confirmed does NOT exist**: any transactions/trade-log method. Tried
  `getTransactionHistory`, `getTradeHistory`, `getTeamTransactions`,
  `getLeagueTransactions`, `getActivity`, `getTransactionsList` — all
  `"Unable to find method"`. **The real trade EVENT log (who traded whom,
  when) still requires the original Phase A item 5 HAR/internal-RPC
  reverse-engineering plan** — only pick *ownership* is solved for free by
  the public API; the event-sourced ledger is not.

**Decisions locked this window (both from direct user answers, not
inferred):**
- Scope for today, confirmed: build a new script pulling **both**
  `getTeamRosters` (current rosters) **and** `getDraftPicks` (real pick
  ownership) from the public API. Not yet written.
- Pick-ref scheme for the real future-pick replacement, confirmed:
  `pick_ref = year|teamId|round` (not the made-pick scheme's
  `draft_season|divisionId|Soverall_slot`, since the public API gives no
  division/slot for unslotted future picks). **`is_synthetic` goes away
  entirely** for these rows (this IS real ownership) — replaced by a new
  `is_slotted=False` flag. Confirmed by re-reading
  `mouserat_trade-bud/backend/routers/assets.py` and `data_access.py`
  before deciding: nothing consuming today's synthetic picks actually reads
  division/overall_slot for *future* picks — only `draft_season`, `round`,
  and `is_synthetic` are used, so dropping the fake slot/division
  assignment is safe.

**NOT yet done (this is the real next-action list, supersedes anything
above that references Phase A item 5 as "next"):**
1. ~~Write the new ETL script~~ **DONE, see Checkpoint 5 below.**
2. ~~Rework `draft_pick_inventory()`~~ **DONE, see Checkpoint 5 below.**
3. Check `mouserat_trade-bud/backend/pick_value.py` (`value_for_pick_row`)
   for any other `is_synthetic` reference before removing the flag.
4. `04a`'s board-scrape repoint (Players grid + divisionId, or just leaving
   it broken and relying on the public API for what it can cover) is an
   **open, unresolved decision** — not blocking today's two items above,
   but flag it before the next scheduled `run_pipeline.py` run tries
   `04a_scrape` again and fails the same way.
5. Cleanup note: temp inspection files this session
   (`data/raw/_inspect_playersgrid_*.json`,
   `_inspect_getplayerstats_direct.json`) were already deleted — `data/raw`
   is fully gitignored so there was never a leak risk, just noise.

Paused here per the standing execution-checkpoint discipline (write state,
then actually stop) — mid-way through gathering requirements for item 1
above when the pause was requested. Resume at item 1.

## Checkpoint 5 (2026-07-18) — public-API ETL + backend rework DONE, verified

Resumed at Checkpoint 4's item 1 and finished both off-plan items.

**New script: `notebooks/04u_fantrax_public_api.py`** (04e-04u were free;
chose `04u` — last free letter, adjacent to the existing v/w/x/z Fantrax
cluster). Reuses 04a's own `LeagueConfig` (`league_id`/`raw_dir` live there,
not on `etl_helpers.CFG` — mirrors 04w's `importlib.import_module` pattern).
Plain `requests.get` — no Playwright, no auth needed for this API surface.

- `getDraftPicks` → `dim_draft_pick_future.parquet` (new table, grain
  `pick_ref`). `pick_ref = f"{year}|{original_owner_team_key}|{round}"` per
  the locked scheme (teamId = **original** owner — that's the pick's natural
  identity pre-draft, since there's no slot yet). `original_owner`/
  `current_owner` resolved from Fantrax's native teamId via
  `dim_fantasy_teams.fantrax_team_id` (same FK 02d/04w already use).
  `divisionId` isn't in the API response for future picks — derived from
  the original owner's `dim_fantasy_teams.division` name via a small
  hardcoded `DIVISION_ID_BY_NAME` dict (Riddell=`rhf63kfummvk3jnh`,
  Wilson=`svxeyvvgmmvk3jnh`, same strings the user supplied earlier this
  session). `pick_in_round`/`overall_slot` are `pd.NA` (genuinely unknown
  pre-draft) — `is_slotted=False` on every row. Verified live: 280 rows
  (28 teams × 5 rounds × 2 years, matching the league exactly), 3 already
  traded (current_owner ≠ original_owner), `pick_ref` uniqueness asserted
  and holds.
- `getTeamRosters` → **not written as a table** (ADR-0003: `fact_fantasy_teams`
  is a ledger-replay projection, never independently scraped — writing this
  as a fact would violate that). Used only for a print-only reconciliation
  check against `fact_roster_placement`'s latest snapshot (active-roster
  count per team). Verified live: **all 28 teams match exactly** — 04v's
  authenticated internal-RPC pull and Fantrax's public API agree, so no
  discrepancy to chase.
- Registered in `notebooks/README.md`'s table and `docs/data_model.yml`
  (new `dim_draft_pick_future` entry, edges to `dim_season`/
  `dim_fantasy_teams` mirroring `dim_draft_pick`'s existing edges) —
  `scripts/check_data_model.py --render` then `--check` both pass clean.

**Backend rework, `is_synthetic` → `is_slotted`, all verified live:**
- `data_access.draft_pick_inventory()`: deleted the entire
  `_FUTURE_YEARS`/`_FUTURE_ROUNDS` synthesis block. Now just
  `pd.concat([dim_draft_pick (is_slotted=True), dim_draft_pick_future
  (is_slotted=False, already has the column)])`. Verified: 1260 total rows
  (980 slotted + 280 unslotted), matches expectation exactly (980 = the
  2026 startup grid; 280 = the new future table).
- `routers/assets.py:team_assets()`: tradeable-pick filter changed from
  `(~inv["is_made"]) | inv["is_synthetic"]` to
  `(~inv["is_made"]) | (~inv["is_slotted"])` — same boolean shape, just the
  renamed column (unmade-slotted OR any-unslotted picks are tradeable).
  `picks_out` dict's `"is_synthetic"` key renamed to `"is_slotted"`.
- `pick_value.py:value_for_pick_row()`: real future picks have no
  `pick_in_round` (unslotted) — `resolve_pick_value()` needs one for its
  tier lookup. Fix: when `is_slotted=False` or `pick_in_round` is NA, fall
  back to the division's middle slot number (`(n_teams+1)//2`), which
  resolves to `_tier_for_slot`'s "Mid" tier — a neutral placeholder until
  the pick is actually made/traded to a real slot. Verified live for team
  `A09`: 10 tradeable future picks (2027/2028 × rounds 1-5), values
  decaying correctly round-over-round (86.7 → 4.4 for 2027, 74.0 → 2.4 for
  2028) — sane market-value shape.
- `routers/trade.py` needed **no change** — its `pick_owner = dict(zip(
  inv["pick_ref"], inv["current_owner"]))` already works unchanged against
  the new real rows.

**Still open (unchanged from Checkpoint 4, not touched this window):**
- `04a`'s board-scrape repoint — still an open, unresolved decision, still
  not blocking, still flagged for before the next scheduled pipeline run.
- Phase A #5 (real trade **event log**, not pick ownership — that part is
  now fully solved) still needs the HAR/internal-RPC approach; no public
  endpoint exists for it (confirmed, 6 method names tried, all failed).
- All data changes this window (new parquet, `docs/data_model.yml`/
  `DATA_MODEL.md`, `notebooks/README.md`, the backend files) are
  **uncommitted** on `mouserat-trade-bud` — per standing project rule,
  commit only when the user explicitly asks.

Resume at Phase A #5 (Fantrax transaction-history ETL, event-log only) when
told to continue — the plan file's Phase A #5 description already reflects
the narrowed scope (see Checkpoint 4's `## Checkpoint 3.5` note in the plan
file and the plan's own Phase A #5 section).

## Checkpoint 6 (2026-07-18) — Phase A #5 HAR capture done, RPC found, PAUSED before parse/write

Per the plan's own note ("if it runs long, pause mid-item at the natural
sub-seam — HAR capture + RPC method found, before parsing/writing"): that
sub-seam is reached. Discovery-only script
`notebooks/04y_transaction_history_capture.py` (NOT registered in
notebooks/README.md — throwaway capture tool, delete/archive once the real
ETL script lands) navigates to
`https://www.fantrax.com/fantasy/league/v744203wmmvjqzv6/transactions/history`
via 04a's authenticated persistent context (no login needed — session was
already live) and logs every `fxpa/req` request/response pair. Output:
`data/raw/fantrax_txn_history_capture.json`.

**RPC found**: `getTransactionDetailsHistory` (data: `{leagueId}`), bundled
in the same 3-msg call as `getFantasyLeagueInfo` + `getFantasyTeams`. `uiv=3`,
`v="184.2.4"` (bump from 04w's `183.1.5`), `refUrl` = the transactions/history
page URL itself.

**Response shape** (`responses[0].data`):
- `paginatedResultSet`: `{totalNumPages, pageNumber, maxResultsPerPage=20,
  totalNumResults}` — this capture returned only 1 page / 20 results (the
  default view), so pagination + a full-history pull are NOT yet solved.
- `filterSettings`/`displayedSelections`: `{positionOrGroup: "ALL", view:
  "TRADE", adminMode: false, includeDeleted: false, team: "DIV_<divisionId>",
  executedOnly: true}` — **defaults to the viewer's current division only**
  (captured as `DIV_svxeyvvgmmvk3jnh` = Wilson), same per-division split 04w
  already handles for draft results. Getting both divisions/all teams needs
  an explicit `team` filter value per call (exact "all teams" value not yet
  confirmed — could be omitting `team` entirely, or a different sentinel).
  `displayedLists.tabs` shows a second view, `LINEUP_CHANGE` — out of scope,
  we only want `TRADE`.
- `table.rows`: **one row per traded asset, not per trade** — multi-asset
  trades group via a shared `txSetId` (this IS the `transaction_id` column
  item 5 already called for). First row of a group carries `numInGroup`
  (count) and the shared `date` cell (`rowspan`); subsequent rows in the
  same `txSetId` omit both.
  - **Player rows**: `scorer: {scorerId, name, teamShortName, posShortNames,
    ...}` populated (same scorer shape as 04a's board).
  - **Pick rows**: `scorer` present but empty (`team: false, rookie: false,
    minorsEligible: false` only), and instead carry `draftPickDisplayParts:
    {roundInfo: "Round <b>N</b> (<OriginalOwnerTeamName>)", year: "<b>YYYY</b>
    Draft Pick"}` — HTML-bolded text, needs regex-stripping (same `<[^>]+>`
    pattern 04a already uses for `posShortNames`). This maps directly onto
    04u's `pick_ref = year|original_owner|round` scheme, EXCEPT the owner
    here is a **team name string**, not a `teamId`/`team_key` — needs a
    name-based resolve via `dim_fantasy_teams.team_name` (or similar), not
    the numeric-id FK path 04u used.
  - Both row types share `cells`: `[{key:"from", teamId, content:teamName},
    {key:"to", teamId, content:teamName}, {key:"date", content, rowspan},
    {key:"week", content}]` — `teamId` here IS the numeric Fantrax id (same
    FK as everywhere else), so player-row ownership resolves the same way
    04u/04w already do (`dim_fantasy_teams.fantrax_team_id`).
  - `resultCode`/`executed`: only `"EXECUTED"`/`true` seen so far (filter was
    `executedOnly: true` by default) — other resultCode values (pending/
    reversed/deleted) not yet confirmed; `deleted`/`disabled` boolean flags
    also present per-row, meaning worth checking `includeDeleted: true` once
    the real parse is built, in case reversed trades matter for the ledger.

**NOT yet solved (next session's actual work, in order)**:
1. Confirm the `team` filter value(s) needed to pull **all** teams/both
   divisions in one call (or whether it must be called once per division
   like 04w, using each division's `DIV_<id>` string — `DIVISION_ID_BY_NAME`
   already exists in `04u_fantrax_public_api.py`, reuse it).
2. Confirm pagination behavior beyond `maxResultsPerPage=20` — full league
   history is almost certainly >20 rows; need `pageNumber` looped like 04a's
   `fetch_player_stats` already does.
3. Write the real ETL script (proper name/registration this time — NOT
   `04y_transaction_history_capture.py`, which stays a throwaway/deletable
   discovery tool). Follow 04w's pattern (import `FantraxScraper`/`CFG` from
   04a, `_post_json`/session-dead retry).
4. Parse rows into `fact_roster_transactions` extension: new
   `transaction_id` column = `txSetId` (groups multi-asset trades — nothing
   currently links related rows, exactly the gap item 5 flagged).
   `event_type="trade"`. Player asset -> `gsis_id` via
   `dim_fantrax_crosswalk` (scorerId). Pick asset -> parse
   `draftPickDisplayParts` (strip HTML, extract round/year/owner-name) and
   resolve the owner name to `team_key` (name-based lookup — check
   `dim_fantasy_teams` for an exact team-name column; 04u only had
   `fantrax_team_id` numeric FK, this is name-keyed instead, likely needs a
   small resolve helper or a mapping built once from `displayedLists.teams`
   in the same response, which already gives `{name, id}` pairs — that `id`
   IS the numeric teamId, so may be simpler to build a `team_name ->
   fantrax_team_id -> team_key` chain per-call rather than parsing the
   owner name out of `roundInfo` at all — reconsider this at parse time,
   don't assume the regex-based approach is the only path).
5. Once real trade rows land: `infer_trade_activity(team_key)` in
   `profiles.py` (trade count over N seasons -> real tier, Phase A #6
   dependency) becomes buildable; `"trade_activity_preference"` can then
   come out of `LOW_CONFIDENCE_FIELDS`.
6. **Note for future-me**: 04u's `dim_draft_pick_future.current_owner` is
   already real/live (Fantrax's own bookkeeping via the public API) —
   this event-log ETL is NOT needed to fix pick ownership (that's already
   solved). Its value here is purely the **trade-activity signal** +
   historical audit trail for `fact_roster_transactions`. Don't re-litigate
   pick ownership when building this.

All work this checkpoint is a new throwaway discovery file
(`notebooks/04y_transaction_history_capture.py`) + its output JSON in
`data/raw/` (gitignored) — nothing touches tracked tables/backend yet.
Uncommitted, as expected (commits only on request).

## Checkpoint 7 (2026-07-19) — Phase A #5 DONE, verified. Two live design
## decisions made mid-implementation (both confirmed with user via
## AskUserQuestion — not re-litigate).

**Both Checkpoint-6 open questions confirmed live** (probe against the real
API, no more guessing): `team: "ALL"` in the `getTransactionDetailsHistory`
request switches from viewer's-own-division to all 28 teams (confirmed: 26
total trade sets vs. the single-division default); `pageNumber` pages past
the `maxResultsPerPage=20` cap (confirmed: page 2 returned 32 more rows).
`04y_transaction_history_capture.py` (the throwaway probe) is **deleted** —
its job is done.

**Real capture script**: `notebooks/04t_fantrax_transaction_history.py`
(new, registered-quality but not yet added to `notebooks/README.md`/
`run_pipeline.py` — do that before this is "fully" shipped). Mirrors 04w's
exact shape (import `FantraxScraper`/`CFG` from 04a via `importlib`,
`_post_json`/session-dead retry, no page.goto navigation needed — POSTs
directly through the authenticated request context). Loops `team="ALL"` +
`pageNumber` 1..`totalNumPages`. Verified live: 2 pages, 125 rows, 26 trade
sets → `data/raw/fantrax_txn_history_2026.json` (gitignored). **Letter
note**: `04y`/`04z` were already taken (`04y_composite_dynasty_metrics.ipynb`,
an existing committed notebook not currently listed in README's table;
`04z_fantrax_crosswalk.ipynb`) — used `04t` instead (first free letter
before the `u-z` late-order Fantrax cluster).

**Row schema, fully mapped from the live capture** (125 rows): every row is
`EXECUTED`/not-deleted; `cells` always carries `from`/`to` **with real
`teamId`** directly (huge simplification — no team-name parsing needed for
ownership at all, contrary to Checkpoint 6's expectation); `date` is
HTML-rowspan'd onto only the first row of each `txSetId` group (forward-fill
within group); player rows carry `scorer.scorerId`; pick rows carry
`draftPickDisplayParts` (`roundInfo` HTML-bolds round + an optional
`(OwnerName)` suffix, `year` HTML-bolds the draft year). **Real discovery**:
current-season (2026) pick rows go up to **round 35** with **no owner-name
suffix** at all (`"Round 30 Pick 9"` — a real 28-team startup with deep
bench/taxi rounds, not a data error); only future-year (2027+) rows carry
the `(OwnerName)` suffix (`"Round 1 (Notorious (W))"`).

**Design decision 1 (confirmed via AskUserQuestion)**: pick-asset trade rows
do NOT get a `dim_roster_asset`/`asset_id` — `dim_draft_pick.original_owner`
is itself still null (deferred), and current-season rows have no owner hint
at all, so there's no stable identity to mint against yet. Player-asset
trades get full `asset_id` resolution via the existing bridge; pick assets
are logged with raw round/year/owner-hint fields only.

**Design decision 2 (confirmed via AskUserQuestion, found DURING
implementation, not anticipated at Checkpoint 6)**: putting pick rows into
`fact_roster_transactions` with `asset_id=NA` would have silently corrupted
`02e_fact_fantasy_teams_derive.py` — its replay does
`ledger.drop_duplicates(["team_key","asset_id"], keep="last")` over the
**whole ledger unconditionally**, so any team with >1 pick-only trade would
have all but the last NaN-asset_id row collapsed into one bogus roster line
(`gsis_id`/`player_key` both null). Fix: **new `fact_trade_log.parquet`**
(grain: one row per traded asset — players AND picks — `transaction_id` =
Fantrax's `txSetId` groups a multi-asset trade's legs;
`team_key_from`/`team_key_to` from the real `cells` teamId, no parsing) is
the source for `profiles.infer_trade_activity(team_key)` (count distinct
`transaction_id`). `fact_roster_transactions` stays untouched in shape
except for two NEW event_types added by `02d`'s new trade-parsing section:
`trade_away` (TERMINAL, added to `02e`'s `TERMINAL` set) on the old team,
`trade` on the new team — **inheriting the player's existing contract terms
from their last ledger row on the old team** (a trade moves a contract, it
doesn't reset it to year 1). `event_seq` uses a new `TRADE_SEQ_BASE=100_000`
namespace (disjoint from startup `<=980` and minor `1000+`).

**Verified live** (`02d` then `02e` rerun): `02d` → `fact_trade_log`: 125
rows / 26 trades; `fact_roster_transactions`: +64 rows (32 `trade_away` + 32
`trade`) = 999 total ledger rows; 3 traded players had no prior ledger row
on their `from` team (pre-ledger free-agent adds — contract fields left NA
for those legs only, flagged via a `[warn]`, not blocking). `02e` rerun:
938 active roster rows (935 startup + 3 net-new from those unresolved-source
legs — arithmetic checks out), all 28 teams present in the cap-committed
summary, no crash, no NaN-asset_id corruption. Spot-checked 2 real trades by
hand: a player-for-player+picks trade (asset 294 moved B10→B06, asset 94
moved B06→B10 **with its real inherited contract** `9,797,000`/`4,898,500`
carried on both legs) and a pure pick-for-pick trade (3-for-3 rounds between
B10/B14, no players) — both parsed correctly.

**NOT yet done** (small, for whenever this is picked back up):
- Register `04t_fantrax_transaction_history.py` in `notebooks/README.md`'s
  table and (optionally) `run_pipeline.py`'s step list — not done this
  checkpoint, ETL correctness was the focus.
- `infer_trade_activity(team_key)` in `profiles.py` itself (Phase A #6
  dependency) — `fact_trade_log` now exists and is ready to be read, but the
  function isn't written yet.
- `draft_pick_inventory()` doesn't need any change from this ETL (04u's real
  `getDraftPicks` already handles pick ownership) — confirmed again, not
  revisited.

All work this checkpoint touches TRACKED files for the first time this
round: `notebooks/04t_fantrax_transaction_history.py` (new),
`notebooks/02d_fact_roster_transactions.py` (extended),
`notebooks/02e_fact_fantasy_teams_derive.py` (`TERMINAL` set +1 value), plus
regenerated `data/fact_roster_transactions.parquet`,
`data/fact_fantasy_teams.parquet`, `data/dim_roster_asset.parquet`, and new
`data/fact_trade_log.parquet`. All uncommitted, per standing rule (commits
only on request). `notebooks/04y_transaction_history_capture.py` and its
raw JSON output are deleted (throwaway, superseded by `04t`).

Resume at: register 04t in README/run_pipeline (quick), then build
`infer_trade_activity(team_key)` in `profiles.py` to close out Phase A #5
completely, then Phase A #6 (confidence-tier rework) when told to continue.

## Checkpoint 8 (2026-07-19) — Phase A #5 fully closed

Both small remaining items done:
- `04t_fantrax_transaction_history.py` registered in `notebooks/README.md`'s
  table (new row, right before `04u`). **Not** added to
  `run_pipeline.py`/`build_steps()` — confirmed `04u_fantrax_public_api.py`
  isn't registered there either (both are manual reverse-engineered pulls,
  same "run by hand" convention as `04w`'s live-draft chain), so `04t`
  matching that non-registration is consistent, not an oversight.
- `profiles.infer_trade_activity(team_key)` written in
  `mouserat_trade-bud/backend/profiles.py`: reads `fact_trade_log`, counts
  `nunique(transaction_id)` where the team appears as either
  `team_key_from` or `team_key_to`, tiers on that raw count —
  `inactive` (0), `occasional` (1-3), `active` (4+). Explicitly noted in the
  docstring/comment that this is a single-season count, not yet
  season-normalized (only one season of `fact_trade_log` exists so far —
  revisit the thresholds once more seasons accumulate). Wired into
  `build_profile()` (`**infer_trade_activity(team_key)`), and
  `"trade_activity_preference"` removed from `LOW_CONFIDENCE_FIELDS` (now
  just `["risk_tolerance", "injury_tolerance"]`) since it's a real signal now.

**Real bug caught during verification, not scope creep**: when I went to
test `infer_trade_activity` against real data, `data/fact_trade_log.parquet`
(written at Checkpoint 7) was **missing from disk** — `git status` showed it
wasn't tracked, and it hadn't survived whatever happened between sessions
(likely just never wrote to a durable location the working tree kept — this
repo's parquet outputs are normally committed by the pipeline's own
allowlisted auto-commit, but this file was generated ad hoc off-schedule
and never went through that path, so it had nothing keeping it alive
locally). Recovered cleanly, no data lost: the raw capture
`data/raw/fantrax_txn_history_2026.json` was still present (that IS
gitignored by design, `data/raw` is a standing exclusion, but it happened to
survive on disk), so rerunning `.\run.ps1 notebooks\02d_fact_roster_transactions.py`
regenerated `fact_trade_log.parquet` byte-for-byte equivalent in content
(125 rows/26 trades, 999 total ledger rows — identical to Checkpoint 7's
numbers) purely from that capture. Reran `02e` after
(938 active roster rows, matches Checkpoint 7 exactly). **Takeaway for next
time**: `fact_trade_log.parquet` and any other ad hoc/off-pipeline parquet
output in `data/` should get an explicit `git add` at some point if it needs
to survive between sessions reliably — the standing "commit only when asked"
rule still applies, but it's worth flagging to the user next time an
off-schedule table like this gets created, rather than assuming the working
tree alone is durable storage.

Verified `infer_trade_activity` against real (regenerated) data: 26 total
distinct trades league-wide; per-team counts ranged 0-13 (B10 highest at 13,
consistent with it being the team from the earlier player-for-player+picks
spot-check); tiers assigned correctly (e.g. B01/B03/B10/B11/A12 all hit
"active" at counts 4/5/13/5/5). `build_profile('B10', 'counterparty')`
confirmed to include a real `trade_activity`/`trade_activity_confidence`/
`trade_count` block and `low_confidence_fields` no longer lists
`trade_activity_preference`.

**Phase A item 5 is now fully DONE** — no remaining sub-items. All changes
this checkpoint uncommitted per standing rule: `notebooks/README.md` (new
`04t` row), `mouserat_trade-bud/backend/profiles.py` (new function +
`LOW_CONFIDENCE_FIELDS` edit), regenerated `data/fact_trade_log.parquet` +
`data/fact_roster_transactions.parquet` + `data/fact_fantasy_teams.parquet`
+ `data/dim_roster_asset.parquet` (content-identical to Checkpoint 7's
numbers, just re-derived from the still-present raw capture).

Resume at: Phase A item 6 (confidence-tier rework — make "high" reachable
in `infer_stance`/`infer_risk_threshold`, make `LOW_CONFIDENCE_FIELDS`
computed-per-team rather than the current static 2-item list), then Phase B,
when told to continue.

## Checkpoint 9 (2026-07-19) — Phase A #6 done, Phase A fully closed

`mouserat_trade-bud/backend/profiles.py` changes:
- `infer_stance`: added a second, tighter age band on each side of the
  existing medium bands — `_STANCE_YOUNG_AGE_HIGH = 23.0` (below this,
  `"Future-Focused"` at `"high"` confidence) and `_STANCE_OLD_AGE_HIGH = 30.0`
  (above this, `"Contending"` at `"high"`). The existing 25.0/27.5 bands
  still produce `"medium"` when the age is less extreme but still on the
  young/old side.
- `infer_risk_threshold`: same pattern — `_RISK_LOW_HIGH = 0.05` /
  `_RISK_HIGH_HIGH = 0.40` on either side of the existing 0.10/0.30 medium
  bands, `"high"` confidence when `cap_room_pct` is far enough from the
  medium zone.
- `infer_trade_activity`: confidence is now `"low"` when `trade_count == 0`
  (can't tell "genuinely inactive owner" from "no attractive offers came
  their way this season yet") and `"medium"` otherwise — was hardcoded
  `"medium"` before.
- New `low_confidence_fields(profile)` function replaces the static
  `LOW_CONFIDENCE_FIELDS` constant (renamed to
  `_STATIC_LOW_CONFIDENCE_FIELDS = ["risk_tolerance", "injury_tolerance"]` —
  same two fields, still no data source, untouched per the locked
  Round-2 decision). The new function starts from that static base and
  appends `"stance"` / `"risk_threshold"` / `"trade_activity"` whenever that
  field's own confidence resolved to `"low"` for the specific team being
  profiled. `build_profile()` now calls `low_confidence_fields(profile)`
  instead of returning the static constant directly.

**Verified against all 28 real teams** (not just one spot-check):
`risk_confidence` reaches `"high"` for 3 teams (`cap_room_pct` > 0.40 —
e.g. A10 at 0.436, B06 at 0.404, A12 at 0.409); 11 teams get `"trade_activity"`
dynamically appended to `low_confidence_fields` (zero trades this season —
e.g. A09/A01/A02/A03/B05); `stance_confidence` never reaches `"high"` with
today's actual roster ages (no team's avg age crosses 23 or 30) — this is
expected and not a bug, the threshold mechanism is confirmed correct via the
risk-threshold and trade-activity cases, it's just that no team's age
happens to be that extreme right now. `build_profile('B10', 'counterparty')`
spot-checked: `trade_activity: "active"` (13 trades, matches Checkpoint 8),
`"trade_activity"` correctly absent from `low_confidence_fields` since B10
has real trade history.

**Phase A is now fully DONE — all 6 items verified against real data**, not
just implemented. All changes uncommitted per standing rule (only file
touched this checkpoint: `mouserat_trade-bud/backend/profiles.py`).

Resume at: Phase B (frontend, `mouserat_trade-bud/frontend/index.html`) —
start with item 1 (Reconnect/Refresh button, smallest independent piece),
then items 2-3 (layout rework, positional overview UI) as one cluster, then
4-6 (conference-filtered pickers, real confidence UI, Build-a-Trade panel
with ages/named-team labels) as the closing cluster — matching the plan
file's own checkpoint-sizing note. When told to continue.

## Checkpoint 10 (2026-07-19) — Phase B done, all 6 items; round closed pending user's own visual check

All 6 items landed in one pass in `mouserat_trade-bud/frontend/index.html`:

1. Reconnect button next to `apiBase`, calls `init()`.
2. Wizard removed. Single page: a shared Teams panel (My/Counterparty
   selects) on top — one switcher per side, not duplicated per-panel (the
   plan's literal wording suggested each panel gets its own switcher; picked
   the simpler single-shared-switcher design instead, since duplicate
   selects for the same team would need explicit two-way sync and add
   surface area for no real benefit). Owner Profiles panel below it, then
   Analysis (Positional Overview, Positional Strength, Build a Trade) all
   always visible — no step/tab gating. `onTeamChange(mode)` fires on
   either select: updates state, reloads that side's profile immediately,
   and re-runs `loadAnalysis()` once both teams are set.
3. New `loadOverview()` renders `/positional-strength/league` (196 rows) as
   a team x position-group table (28 rows x 7 columns), colored with the
   existing `.tag.surplus/need/neutral` classes; loads once on `init()`,
   independent of team selection.
4. `refreshCpOptions()` filters the Counterparty select to teams sharing
   `myTeam`'s `conference` — real UI backstop in front of the Phase A #4
   server-side 400. Edge case handled: switching `myTeam` after a `cpTeam`
   was already picked, if the old counterparty falls outside the new
   conference, clears its selection AND the stale profile/positional-
   strength DOM (was initially going to leave this unhandled — added after
   noticing the DOM would otherwise silently show a stale team).
5. Confidence badges (`.tag`, colored by high/medium/low) replace the old
   unconditional "ask the owner directly" block; the helper panel with the
   actual field list now only renders when `low_confidence_fields.length`
   (real per Phase A #6). Added a trade-activity signal line to the profile
   body — that data has existed in the API since Checkpoint 8 but was never
   rendered anywhere in the UI until now.
6. Player assets show age inline (list + basket). Pick assets fixed to read
   `is_slotted` — the JS was still checking a stale `is_synthetic` key that
   Checkpoint 5 retired from the backend entirely, so the "future pick"
   marker had been silently dead code since then. Basket headers relabeled
   to `"{team_name} trades away:"` once both teams are picked.

**Real bug found and fixed during verification (not pre-known, surfaced by
curling the live backend, not by code reading alone)**: `routers/trade.py`'s
`TradeRequest` gained required `my_team`/`counterparty_team` fields at
Phase A #4 (Checkpoint 3), but the frontend's `evaluateTrade()` POST payload
was never updated to send them — every trade evaluation would have 422'd
from the moment Phase A #4 shipped, and this would only have shown up the
first time someone actually tried to build a trade in the browser. Fixed:
`state.myTeam`/`state.cpTeam` now included in the payload.

**Verification performed**: booted `uvicorn main:app --port 8420` against
real data; curled `/teams`, `/positional-strength/league`,
`/teams/{k}/profile?mode=counterparty`, `/teams/{k}/assets` and confirmed
every field the rewritten JS reads (`age`, `is_slotted`, `trade_activity`/
`trade_count`/`trade_activity_confidence`, `low_confidence_fields`) is
actually present with the expected shape; POSTed a real same-conference
trade payload (with `my_team`/`counterparty_team`) to `/trade/evaluate` and
got back a correct Pareto result. Opened `index.html` in the OS default
browser pointed at the live backend.

**Not independently confirmed**: actual on-screen rendering/click-through —
no browser-automation tool was available this session, so "browser
click-through" per the plan's Phase B verification section was not done by
me directly. The API-contract verification above is strong evidence the
wiring is correct (every field name/shape matches on both sides), but per
this repo's own UI-testing standard (CLAUDE.md), a claim of "the UI works"
requires someone to actually look at it. **User should click through the
already-open browser tab (backend still running on :8420)** before
considering this round fully closed.

All Phase B changes uncommitted per standing rule — only file touched:
`mouserat_trade-bud/frontend/index.html`.

Resume at: nothing plan-mandated remains — Phase A and Phase B are both
implemented and verified at the level available without a browser tool.
Next step is user-driven: confirm the UI on screen, then decide whether to
commit this round's work (Phase A #6 + all of Phase B) and move to the
punch-list items (risk-tolerance grill session, injury-tolerance data
source, `fact_standings`, confidence-weighted Pareto math, deployment).

## Round 3 (2026-07-19/20): Draft picks as team assets in PBI — IMPLEMENTED, not yet Desktop-verified

Full design in the plan file's "Round 3" section (superseded/extended by
Round 4 below — see there for the current shape). Summary of what landed:
new `pbi/mouserat2/Mouserat2.SemanticModel/definition/tables/Dim_DraftPick.tmdl`
(9 columns: PickRef/DraftSeason/Round/PickInRound/OverallSlot/OriginalOwner/
CurrentOwner/IsMade/IsSlotted), M-query unions `dim_draft_pick.parquet` +
`dim_draft_pick_future.parquet` via `Table.Combine`, drops `divisionId`.
Two new relationships in `relationships.tmdl`
(`Dim_DraftPick_to_Dim_FantasyTeams_via_CurrentOwner`,
`Dim_DraftPick_to_Dim_Season_via_DraftSeason`). `cultures/en-US.tmdl` got
10 new minimal (non-thesaurus-expanded) linguistic entries. **Discovered
mid-implementation, not in the original plan text**: `model.tmdl` needed
`ref table Dim_DraftPick` + a `PBI_QueryOrder` entry — without this the
table silently fails to register. `check_data_model.py --check` passed
clean (no ETL-side change needed, both source parquets were already
registered). **Not yet done**: user's own Power BI Desktop open+verify
(1260 rows, `CurrentOwner` relationship resolves clean, per-team pick
count sanity check) was never confirmed back.

**Note**: this entire table gets renamed/reshaped by Round 4 below before
that Desktop verification should happen — no need to verify the
now-superseded `Dim_DraftPick` name.

**Same window**: fixed a real frontend regression the user caught by
screenshot — the tab-restructure from an earlier session had silently
collapsed the two-team "Positional Overview" matchup panel's original
per-team `Pos | Rank/28 | Signal-word` tables into a merged wide table
that only showed a bare colored rank number (lost the rank fraction and
the surplus/need/neutral word label). Recovered the original
`renderPositional(tableId, labelId, rows, teamName)` function verbatim via
`git show HEAD:mouserat_trade-bud/frontend/index.html` (the file's one and
only formal commit, `6a0d68e`) and reapplied it to the two-team panel only
— the league-wide 28-team tab (which uses the newer merged-table
`renderOverviewTable`) was untouched since it wasn't the subject of the
complaint. User's own browser confirmation of this fix is still
outstanding.

## Round 4 (2026-07-21): Fact_DraftPick rebase + DraftType + original_owner fix — DONE, VERIFIED, ROUND CLOSED

Full plan lives in the plan file (`C:\Users\benha\.claude\plans\critically-review-our-graceful-nebula.md`,
"Round 4" + "Implementation status" + "Resume-at checklist" sections) — **all
9 implementation items done and verified against real data this session**.
Summary, so this survives a compact even if the plan file isn't re-read:

**Decisions locked:**
1. **`Dim_DraftPick` → `Fact_DraftPick`**, full top-to-bottom rename
   including the parquet files themselves: `data/dim_draft_pick.parquet` →
   `fact_draft_pick.parquet`, `dim_draft_pick_future.parquet` →
   `fact_draft_pick_future.parquet`, `type: dim` → `type: fact` in
   `docs/data_model.yml`. Reasoning: the table is an ownership-assignment
   table (FKs out, no descriptive attributes of its own) — structurally
   identical to `Fact_FantasyTeams`, not a dimension. User explicitly chose
   the full-rename option over a PBI-only-rename option when asked.
2. **`draft_type` ("Startup"/"Rookie") explicit in the parquet**, not
   PBI-derived. New `etl_helpers.classify_draft_type(rounds, threshold=5)`:
   per write-batch, if that batch's max `round` > 5 → `"Startup"` else
   `"Rookie"`. Chosen over a season-literal hardcode specifically because
   the user flagged **future one-off "abandoned team" re-startup drafts
   will recur infrequently** alongside the normal annual 5-round rookie
   drafts — a round-count rule handles both without a maintained exception
   list.
3. **New `dim_contract` row for picks** (`contract_id="Pick"`,
   `contract_type="draft_pick"`, `cap_hit_pct=0`, `cap_exempt=True`) so
   `Fact_DraftPick` can carry a `ContractID` FK (added via PBI M-query
   constant, not in the parquet — mirrors how Round 3 added `is_slotted`).
   User confirmed **all pick rows point at the same single contract row**
   (flat, no per-pick variation). This is explicit **prep** for a
   **future, not-this-round** union of `Fact_DraftPick` into a single
   players+picks asset table — user's words: "ultimately... perhaps a
   union."
4. **`original_owner` (100% null in the real/2026-startup file) IS being
   fixed this round** — reopened after the user correctly pushed back on
   an earlier "no prior-owner concept in a startup draft" justification
   from before a prior compact. **Root cause confirmed via direct
   inspection of the raw capture**
   (`data/raw/fantrax_draftresults_2026_*.json`, via the
   `fantrax-payload-analyst` agent): `getDraftResults`'s
   `draftPicksOrdered` objects only carry `teamId` (current, post-trade
   owner) — no `originalTeamId`/`tradedFrom`/equivalent field exists
   anywhere in Fantrax's API response, confirmed by listing every key on
   the object (`defaultPositionId, divisionId, modifiedDate, pickNumber,
   pickTime, positionId, round, scorerId, statusId, teamId, type`) and by
   checking `getFantasyLeagueInfo`/`getRefObject` responses too (neither
   carries slot-assignment data). The `02d_fact_roster_transactions.py`
   comment ("deferred: needs draftPicks.go") was accurate — this was a
   known gap, not a deliberate design choice. The user reads the original
   order visually off Fantrax's own GRID view UI
   (`fantrax.com/fantasy/league/v744203wmmvjqzv6/draft-results?view=GRID`)
   — that page reconstructs it client-side, not from any API payload we
   can pull.

   **Fix — REVISED again same session, no blocking data collection**: user
   overrode the hand-seed plan — instead, **infer the draft order directly
   from round 1 of the draft's own captured data**. `dp[dp.round==1]`'s
   `(divisionId, pick_in_round) -> current_owner` *is* the original order,
   by definition (no reconciliation attempted against possible round-1
   trades — accepted as ground truth). New
   `etl_helpers.expand_snake_draft_order(round1_order, total_rounds)`
   expands that to all rounds via the snake rule, computed inline inside
   `02d_fact_roster_transactions.py` from data already in hand — no new
   parquet, no seed notebook, no user-supplied data. Round 1 rows get
   `original_owner = current_owner` directly; rounds 2+ get the
   snake-expanded value. Same logic generalizes automatically to any
   future one-off "abandoned team" startup re-draft (re-derives from that
   draft's own round 1 each time). **The earlier
   `dim_draft_order.parquet`/`01h_dim_draft_order_seed.ipynb`/user-pastes-
   the-order plan is fully dropped** — nothing blocking remains in Round 4.
5. **Deliberately NOT rewritten**: historical/point-in-time docs (ADRs
   `0003`/`0004`/`0006`, this file's own checkpoint log,
   `.claude/memory/project-fantasy-football.md`) keep saying
   `dim_draft_pick` — they're a record of what was true when written. Only
   living reference docs (`docs/data_model.yml`, generated
   `docs/DATA_MODEL.md`, `notebooks/README.md`, `data/README.md`,
   `.claude/memory/data-model.md`) get the rename.

**Implementation order** (per the plan file, current numbering after the
round-1-inference revision): #1-4 (ETL helper `classify_draft_type`, both
notebook path/column changes, contract seed), #5-6
(`expand_snake_draft_order` helper + `original_owner` backfill inline in
`02d`, fully self-contained now), #7 (`data_access.py`/`pick_value.py`
path updates), #8 (`docs/data_model.yml` + generated docs + memory), #9
(PBI TMDL rename/new columns/relationships) — #9 last since it depends on
the renamed/enriched parquets existing.

**Final implementation status (2026-07-21, same session — round closed):**
All 9 plan items done, reruns executed, verified against real/live data:
- **#1-4, #7-8 (code/docs)**: as before — `etl_helpers.py` helpers,
  `02d`/`04u` path+column changes, `01b` new `"Pick"` contract row,
  `data_access.py`/`pick_value.py` path updates, `docs/data_model.yml` +
  `notebooks/README.md` + `data/README.md` + `.claude/memory/data-model.md`
  all rewritten to the `fact_draft_pick*` framing.
- **Reruns executed**: `01b` (nbconvert) → `dim_contract.parquet` now 11
  rows incl. `Pick` (`cap_hit_pct=0.0`, `cap_exempt=True`); `02d` →
  `fact_draft_pick.parquet` (980 rows, `draft_type`="Startup" for all 980,
  `original_owner` populated 980/980); `04u` (live Fantrax call) →
  `fact_draft_pick_future.parquet` (280 rows, `draft_type`="Rookie" for all
  280).
- **`original_owner` inference verified on real trade data**: 82 of 980
  slots show `current_owner != original_owner` — spot-checked round 9,
  e.g. divisionId `rhf63kfummvk3jnh` slot 123 (`A08` current vs `A12`
  original) and slot 126 (`A12` current vs `A04` original), consistent with
  a real multi-round pick swap between those teams. Confirms the
  round-1-inference + snake-expansion logic is correctly reconstructing
  trades, not just passing a spot-check on one preselected team.
- **Orphaned old-named files removed**: `git rm data/dim_draft_pick.parquet`
  (was tracked), `rm data/dim_draft_pick_future.parquet` (was untracked).
- **`check_data_model.py --render`+`--check` pass clean.** Found+fixed one
  real remaining drift missed by the earlier doc-only pass:
  `dim_roster_asset`'s edge in `docs/data_model.yml` still pointed at
  `dim_draft_pick` (line ~324) — fixed to `fact_draft_pick`. Bare
  schema-validate mode still shows 6 pre-existing dtype FAILs
  (`contract_year`, `event_date`, `draft_round`, `pick_in_round`,
  `pick_overall` on `fact_fantasy_teams`/`fact_roster_transactions` —
  nullable-float-vs-int64 and ms-vs-us datetime drift) — confirmed
  unrelated to this round, not fixed, flagged as a pre-existing gap for a
  future pass.
- **Backend boot confirmed live**: `uvicorn main:app --port 8421` against
  the renamed parquet files; `curl /teams` and `curl /teams/A09/assets`
  both returned correctly (35 players + 10 picks, `asset_id` shaped like
  `"2027|A09|1"`, values computed) — `draft_pick_inventory()` reads
  `fact_draft_pick`/`fact_draft_pick_future` with no breakage.
- **#9 PBI TMDL rename/enrichment done**: `Dim_DraftPick.tmdl` deleted (was
  untracked — Round 3 never got committed, so this was a plain delete, not
  a git mv), `Fact_DraftPick.tmdl` written (`queryGroup: 'Fact Tables'`,
  new `DraftType`+`ContractID` columns, M query adds `contract_id="Pick"`
  via `Table.AddColumn`); `relationships.tmdl` — both relationships renamed
  to `Fact_DraftPick_to_*`, new
  `Fact_DraftPick_to_Dim_Contract_via_ContractID` added; `model.tmdl` —
  `PBI_QueryOrder`+`ref table` renamed; `cultures/en-US.tmdl` — all 9
  `dim_draft_pick*` entity keys renamed to `fact_draft_pick*` (grep-verified
  0 stray old-name refs across the whole `pbi/` tree), 2 new entries added;
  `Dim_Contract.tmdl` header "10 rows"→"11 rows".

**Not independently confirmed**: opening the `.pbip` in Power BI Desktop to
visually verify row counts/relationships — the TMDL source is complete and
internally consistent (pattern-matches existing tables exactly, grep-clean),
but the actual Desktop open-and-look-at-it step is still worth doing before
calling this fully shipped end-to-end.

Resume at: nothing plan-mandated remains for Round 4. If a future round
wants to tackle it: the 6 pre-existing dtype drift FAILs noted above
(unrelated to this round, found as a side effect of running
`check_data_model.py`), or the actual Power BI Desktop visual open/verify
step.

## Checkpoint 11 (2026-07-25) — 04t `view` fix + FA claim/drop ledger events

**04t data-loss scare: resolved, was never a windowing bug.** A user-captured
browser HAR of the real Fantrax transactions UI showed
`getTransactionDetailsHistory` takes a **required `view` filter**
(`"TRADE"` vs `"CLAIM_DROP"` are two separate filtered result sets, matching
the page's own tabs). `04t` never set it, so each run silently returned
whichever view the account's server-side UI state happened to default to —
one run all trades, the next all claim/drop. Nothing was ever evicted
server-side. Fix: `04t` now loops `VIEWS = ("TRADE", "CLAIM_DROP")`, paging
each to completion, with `maxResultsPerPage="500"` (also from the HAR; the
unset default is 20). Verified live: 180 rows / 80 tx sets,
`transactionCode={None: 125, 'CLAIM': 53, 'DROP': 2}`. **Trade legs carry
`transactionCode: null`, not `"TRADE"`** — that's what `02d` branches on.

**`02d`'s trade section rewritten into a unified transaction section**
(trade + claim + drop). Verified: `02d` → `{'claim': 53, 'trade_away': 32,
'trade': 32, 'drop': 2}`, 1094 ledger rows; `02e` → 1027 active roster rows,
no team over cap, and `TERMINAL`'s `"drop"` branch firing for the first time
since it was written.

Three things changed beyond the pre-agreed design, all forced by real
problems found during implementation:

1. **One shared chronological `event_seq` (`TXN_SEQ_BASE = 100_000`)** across
   trade/claim/drop, ordered by each row's real parsed datetime (tiebreak:
   drop → trade → claim). The originally-planned separate
   `CLAIM_DROP_SEQ_BASE = 200_000` only holds while every claim postdates
   every trade — it breaks the first capture containing a trade newer than an
   earlier claim, because 02e's last-event-wins ranks purely on `event_seq`.
2. **`_trade_season_id`'s `month >= 8` heuristic was wrong** — it filed all 26
   real (June/July 2026) trades under `season_id="2025-2026"`, a season absent
   from `dim_season` entirely. Replaced by `_season_id_for(dt)`, which reads
   `dim_season`'s own `season_fantasy_start_date`/`end_date` spans
   (2026-03-01..2027-02-28). **This lookup is the primitive the Minors
   season-boundary rule needs next.**
3. **Txn types now replace-by-`event_type`**, not `(season_id, event_type)` —
   forced by #2, since correcting the season would strand the old partition as
   orphans. Safe: rebuilt in full from the 04t capture every run.

**Contract-on-claim rule (user-locked)**: *"if they were already a FA contract
then they have a league minimum of 2 million. if they were rostered and
released then they retain salary and contract for the season."* Implemented as
a forward walk over the txn stream with running `copy_terms[(team_key,
asset_id)]` + `conf_terms[(conference, asset_id)]` state seeded from the
non-txn ledger. A claim inherits only a contract held **this season in this
conference** — conference scoping is load-bearing (duplicate-player league,
one copy per conference; the other side's copy must not donate its contract) —
else falls back to `dim_contract`'s existing `FA` row ($2,000,000, cap-exempt,
no new seed needed). Side benefit: this also fixed chained trades, which
previously resolved against stale prior-run rows still sitting on disk.

**Spot-checks**: asset 562 (`05jel`) claimed by B05 07-23 at FA/$2M then
dropped by B05 07-24 — clean pair, terms carried onto the drop. Asset 75
(`06anf`) dropped by B09 mid-startup-draft, inheriting `1st`/$19.2M via
conference history; B06's own copy stays active, since last-event-wins is per
`(team_key, asset_id)` and a drop by a team that never rostered the copy is
inert. All 53 claims hit the FA fallback — expected, genuine undrafted-FA adds
with no prior ledger history.

**Deferred, confirmed viable**: `getTeamRosters?leagueId=...&period=N`
(public no-auth `fxea/general` API) genuinely time-travels — per Fantrax's own
developer docs, *"retrieved for the upcoming/current period... or you can
specify any period"* — and returns real `contract.name`/`salary` per roster
item (live-tested at `period=1`). This is the right backstop for a future
claim whose player has no ledger history because their drop predates our
capture window (04t/02d only start ~2026-07-19). Not wired in: the league is
still entirely inside period 1 (preseason), so `period` can't disambiguate
finer than the ledger's own datetime ordering already does, and no player in
today's data needs it.

## Checkpoint 12 (2026-07-25) — Thread B closed + Minors-stash rule shipped (ADR-0010)

**Thread B closed.** Booted the backend and swept all 28 teams via
`/teams/{k}/assets`: exactly **5** startup (2026-2027) picks tradeable
league-wide — A03 overall 385/428/441, A08 430/458 — matching the Fantrax CSV
ground truth exactly. The 40 stale B-conference rows are gone. `routers/
assets.py`'s `(~is_made) | (~is_slotted)` filter was never wrong; the bug was
purely stale `fact_draft_pick.parquet`. Backend left running on port 8420.

**Thread A shipped** — the Yo-Yo "(rostered or FA)" durability rule, corrected.
Full rationale in **`docs/adr/0010-minors-stash-season-boundary.md`** (read that
first; this is the working context around it).

Two findings reshaped the round before any code was written, both confirmed by
direct inspection — **these are the load-bearing facts to not lose**:

1. **No player holds a `Minor` contract.** `fact_roster_placement` is 987 `1st`
   + 5 `FA`, zero `Minor` — even though 125 players sit in the Minors *squad
   section*. So `derive_minor_events()` has never emitted a single event and the
   ledger has zero `minor_assignment`/`minor_graduation` rows. Squad placement
   and contract type are completely decoupled in the live data.
2. **The clock the rule pauses doesn't tick.** `contract_year` is written as the
   literal `1` at every writer in the repo (`02d` lines 246/324/563, inherited
   elsewhere); nothing advances it across a season.

Consequence, and the user's explicit scope choice (offered 4 options via
AskUserQuestion, picked "codify rule + fix docs"): the rule is **prospectively
correct, presently inert**. Not a bug — recorded as such in ADR-0010's
Consequences so nobody later "fixes" logic that has correctly never fired.

**The bug in code form**: `derive_minor_events()` carried `prev` across a copy's
absence from placement snapshots, so a stash silently continued through an FA
gap of any length or timing. Fix: build the global snapshot grid from
`p["snap_seq"].unique()` (placement only holds rows where a copy was *present*,
so absence is only answerable against the full captured set) and reset
`prev = None` when a skipped period coincides with a season change. Fresh
`minor_assignment` fires naturally on reappearance = the locked "fresh
independent stash". **No new event type** — a `minor_stash_break` would have
carried no rows and forced changes to `02e`'s replay/`TERMINAL` and the PBI
model for nothing.

**Deviation worth remembering**: season identity comes from the placement row's
own `season` field, NOT `_season_id_for(capture_date)`. Fantrax labels each
snapshot with its own season, which is authoritative; `_season_id_for` would be
subtly wrong when a new season's `PRE` snapshot is captured before the prior
fantasy year's `season_fantasy_end_date`.

**Verification pattern worth reusing when data can't exercise a rule**: (a)
synthetic replay — lift the function out of the script via `exec` of a source
slice (02d runs top-to-bottom on import, so a plain import would re-run the
whole ETL) and assert event counts over a hand-built frame; all four cases
passed, boundary gap correctly produced 2 assignments with distinct keys. (b)
Real-data regression asserting **byte-identical** output (md5 over
`hash_pandas_object`) — with zero Minor contracts, a correct change *must* be a
no-op, so the no-op is the real test. Both held; 1094 ledger rows / 1027 active
roster rows unchanged. Scratch script deleted after use per the `workspace/`
rule.

**Also corrected**: `.claude/memory/data-model.md:64` now explicitly separates
GP **eligibility** (genuinely durable through FA) from contract **protection**
(stash-based, breaks at a season boundary) — conflating them in one sentence is
exactly how the rule drifted. Same split applied to `PLAN.md:77` and
`04v_minor_contracts.py`'s header. `04v`'s actual logic is untouched — it only
diffs eligibility vs contract type and never needed the distinction.

**Next**: the `contract_year` season-rollover clock (what makes ADR-0010
actually bite — deferred to its own round), and separately worth investigating
whether Fantrax genuinely doesn't use the Minor contract label or whether `04v`
fails to capture it for those 125 Minors-placed players. `getTeamRosters?
period=N` backstop still deferred. Nothing committed.

## Checkpoint 13 (2026-07-26) — Minor contract type RETIRED; ADR-0010 superseded by ADR-0011

**The premise of Checkpoint 12 was wrong.** Resumed by investigating the open
"why do no Minor contracts exist" question. The answer was not a capture bug —
the commissioner corrected it directly: *"there are no minor league contracts.
i believe this was an earlier assumption that has since updated to our current
process. minor eligible for 20 games with a standard contract - generally a
first, barring injuries. there was a previous thought to generate a contract
style but we are moving away from that."*

**Minors is exactly two independent things, and no third:**
- **Eligibility** — GP ≤ 19 career+current, Fantrax-computed, league-wide,
  rostered or FA.
- **Placement** — which squad section a copy occupies (Active/Reserve/Minors).
  The team's own lever, and the **sole** cap exemption.

Eligibility *permits* placement, doesn't compel it, and never touches the
contract. Data confirms: `fact_roster_placement` = 987 `1st` + 5 `FA`, zero
`Minor`; all 125 Minors-placed copies hold `1st`; 357 rostered copies are
eligible but only 125 are placed.

**Load-bearing discovery that reframed the "is 04v still needed?" question**
(user asked it directly, suspecting redundancy with `Fact_FantasyTeams`):
`04v` is the **sole writer** of `fact_roster_placement`. `02e:88-94` stamps
`roster_status` onto `fact_fantasy_teams` from its latest snapshot, and
`capmath.py:51` + the DAX `Active Roster Salary` exempt
`roster_status == "Minors"`. Kill 04v → `roster_status` goes null league-wide →
all 125 Minors-placed players start charging full salary. `04u` only reads it
for a reconciliation warning. **Read-only does not mean optional** — that
sentence is now in the ADR, the README, and data-model.md, because the natural
reading of "we stripped 04v down to pulls" is that it became skippable.

**Live hazard found and neutralized**: `04v`'s `build_worklist` had generated
`data/review/review_contract_actions.csv` = **5,698 rows, every one "set
contract → Minor"** (5,341 FA + 357 rostered), and `--apply` POSTs those to
Fantrax. Opt-in and never scheduled, so it never fired, but it was a loaded gun
regenerating on every run against a retired model. Deleted, with
`fa_contract_import.csv`. Both untracked.

**Shipped** (user approved scope "neutralize hazard + supersede docs", then
separately confirmed deleting the write-side outright: *"yes, this is accurate
- they no longer have value when stripped of purpose"*):
- `04v` 765 → ~390 lines, **read-only**. Deleted `build_worklist`,
  `apply_worklist`, `export_fa_csv`, `prev_eligibility`,
  `admin_roster_payload`/`build_field_map`/`edit_payload`, and all five CLI
  flags. **The repo now has no write path to Fantrax at all** — that
  grill-approved exception to the no-write-side rule is retired with the thing
  it existed for.
- `docs/adr/0011-minors-is-placement-not-contract.md` (new); ADR-0010 banner-
  marked SUPERSEDED.
- Corrected at source: `data-model.md` (both the placement and eligibility
  rows), `PLAN.md:75` (section retitled + closed — its "contract automation
  (Minor ↔ 1st)" premise is void), `notebooks/README.md`, `data/README.md`,
  `sources.yml` (+ re-rendered `SOURCES.md`), `run_pipeline.py`, and a stale
  executed-output cell in `00_fantasy_etl_flow.ipynb` that still printed the
  5,698-row worklist line.
- `tests/test_04v_minor_contracts.py`: dropped `TestBuildWorklist` (8 tests),
  added two that pin what matters now — Minors placement keeps an ordinary
  `1st` contract, and an unknown `statusId` passes through raw (this is how IR
  will surface). 27/27 pass; both `check_sources`/`check_data_model --check`
  clean.

**IR cap treatment — CLOSED 2026-07-26, no code change.** Commissioner decided
IR-placed players charge full salary (IR is a lineup convenience here, not cap
relief). The existing rule already charges anything whose `roster_status` isn't
the literal `"Minors"`, so an IR section appearing mid-season is handled
correctly on arrival. **Do not reopen this as a bug** — the `<> "Minors"`
literal is the decision, not a TODO.

Found while checking this: that literal lives in **four** places, not the two
recorded earlier — `capmath.py`, `02e`, and *both* PBI measures (`Active Roster
Salary`, `Remaining Salary Cap`). If which sections are exempt ever does change,
all four must change together or the bot and the report will disagree about who
is over the cap. Null `roster_status` charges too (35 rows today), by design.

**Inert cleanup — DONE 2026-07-26.** `dim_contract`'s orphan `Minor` row removed
(11 → 10, `01b` rerun), `derive_minor_events` + the `minor_assignment`/
`minor_graduation` event types deleted from `02d`, PBI row-count and contract-list
descriptions corrected. Verified a true no-op: `02d` → `02e` rerun byte-identical
(1094 / 1027 / 567, md5 per table).

**The one trap in that cleanup, worth remembering**: `derive_minor_events` shared
its block with a `mint_assets()` call that extends `dim_roster_asset` with copies
the startup draft never saw (post-draft FA adds). Deleting the block wholesale —
the obvious move — would have silently shrunk the asset bridge. Dead code sharing
a block with live code is not dead; check what else the block does before cutting.

**`getTeamRosters?period=N` backstop — CLOSED, will not build.** Probed live:
the endpoint does **not** serve historical state. `period=1/2/5/17/99` all return
identical rosters/contracts/salaries/status (only the echoed `period` differs;
17 == 99, so it clamps). Building it would be *worse* than the current FA
fallback — for a claim with no ledger history the player's current contract is
the one that claim created, so the lookup returns its own answer circularly and
writes a confidently wrong contract instead of an honest league minimum. Full
reasoning + re-probe condition is a comment at the fallback site in `02d`.

**Process learning worth keeping.** ADR-0010 was written the *previous day* and
was wrong at the **premise** level, not the detail level — it correctly codified
a rule for an entity that doesn't exist. Its verification passed honestly
(synthetic replay + byte-identical no-op regression) and proved only internal
consistency; a no-op on nonexistent data cannot tell you the entity shouldn't
exist. Its "presently inert" note was the right observation for the wrong
reason. No amount of code-side verification would have caught this — only
domain confirmation would. **When a rule's subject has zero rows in production,
that is a signal to go ask whether the subject is real, not merely a note to
record about test coverage.**

**Next**: the `contract_year` season-rollover clock is now **moot in its Minors
framing** (nothing was ever pausing); if it's still wanted it's a plain
contract-aging question. The IR cap decision above is the live one. Nothing
committed.

## Checkpoint 14 (2026-07-26/27) — ADR-0011 epic SHIPPED and MERGED (PR #33)

**Everything from Checkpoints 12-13 is now merged to `main`** as squash commit
`b5cfd15` (PR #33, 7 commits, 32 files, +1329/-882). Branch
`minors-adr0011-cleanup` deleted both ends. Main is green: 27/27 tests,
`check_sources --check` and `check_data_model --check` both clean. This closes
the whole Minors arc — nothing from it is left open.

### The three items completed this session, in order

**1. Inert cleanup — DONE, verified no-op.** `dim_contract` back to 10 rows
(orphan `Minor` row removed, `01b` rerun), `derive_minor_events` +
`minor_assignment`/`minor_graduation` deleted from `02d`, PBI row-count and
single-year-contract-list descriptions corrected, `data/README.md`'s ledger
event-type list fixed (it still said `minor_*`; the real types are
`startup_draft`, `trade`/`trade_away`, `claim`/`drop`). Proven by rerunning
`02d` → `02e` and md5-comparing per table: **byte-identical**
(`fact_roster_transactions` 1094, `fact_fantasy_teams` 1027,
`dim_roster_asset` 567).

**THE TRAP, worth remembering beyond this repo**: `derive_minor_events` shared
its `if PLACEMENT_PATH.exists():` block with a `mint_assets()` call that extends
`dim_roster_asset` with roster copies the startup draft never saw (post-draft FA
adds). Deleting the block wholesale — the obvious move when removing a dead
function — would have silently shrunk the asset bridge and surfaced much later
as a `KeyError` on some future trade/claim leg for an unminted scorer. The
`dim_roster_asset` count holding at 567 is what proves the mint survived.
**Dead code sharing a block with live code is not dead; read what else the block
does before cutting.**

**2. `getTeamRosters?period=N` backstop — CLOSED, deliberately NOT built.**
Probed the live endpoint *before* writing any code. Fantrax's developer docs
say it serves historical per-period roster state. **It does not.** Across
`period=1/2/5/17/99`: identical roster membership, contract, salary and status
(1031 items, zero diffs on every field that matters); the *only* thing that
changes is the echoed `period` value in the response, and `17 == 99` so it
clamps rather than erroring.

Not building it is the correct outcome, not a blocked one — **wiring it would
have been strictly worse than the fallback it was meant to improve.** The case
it exists to serve is a claim whose player has no ledger history; for exactly
that player, the contract Fantrax returns today *is* the one that claim
produced. The lookup would circularly hand back its own answer and write a
confidently wrong contract where the current code writes an honestly
conservative league minimum ($2M FA). Full reasoning + the re-probe condition
(revisit if `period` ever returns genuinely distinct rosters once real in-season
periods exist) is a comment at the fallback site in `02d`, deliberately placed
where someone asking "shouldn't this be smarter?" will hit it.

**3. Commits/PR — merged.** Grouped into 7 logical commits rather than one
blob: ADR-0011 correction / inert cleanup / backstop closure / `04t` two-view
capture / `dim_position` sort order / trade-bud cap panel / parquet refresh.

### Still true and still load-bearing (do not regress)

`04v` is read-only but **not optional** — sole writer of
`fact_roster_placement`, which `02e` stamps as `roster_status`, which capmath +
both DAX measures use for the cap exemption. Stop running it → `roster_status`
null league-wide → all 125 Minors-placed players charge full salary.

`roster_status == "Minors"` is hardcoded in **four** places, not two:
`discord_bot/capmath.py`, `notebooks/02e_fact_fantasy_teams_derive.py`, and
*both* PBI measures (`Active Roster Salary`, `Remaining Salary Cap`). Any future
change to which sections are cap-exempt must hit all four together or the
Discord bot and the Power BI report will disagree about who is over the cap.

### Decisions that produced no code (record, don't re-litigate)

- **IR charges full salary** (commissioner, 2026-07-26). No change needed — the
  existing rule already charges anything not literally `"Minors"`, so IR is
  handled correctly the day that section appears via `statusTotals`
  pass-through. The `<> "Minors"` literal is the decision, **not a TODO**.
- **`getTeamRosters?period=N`** — see item 2. Closed, not deferred.

### Open after this session

Nothing from the Minors arc. Remaining, unrelated and unstarted:
- `mouserat_trade-bud` UI has never been eyeballed in a browser — curl-verified
  for API shape only. Oldest outstanding item on this project.
- `contract_year` season-rollover clock — moot in its Minors framing; if still
  wanted it is a plain contract-aging question with no Minors dimension.
- 6 pre-existing dtype-drift FAILs in bare `check_data_model.py` validate mode
  (`contract_year`, `event_date`, `draft_round`, `pick_in_round`,
  `pick_overall`) — known logged gap, untouched, unrelated.
- Three untracked local files deliberately never committed: `Propmts.txt`
  (stray scratch note), `.claude/settings.json` (contains an absolute
  session-scratchpad path, machine-specific), `pbi/.claude/learnings.db`
  (binary). Worth gitignoring the latter two.

### Process learning from this session (distinct from Checkpoint 13's)

**Probe an external API's actual behaviour before building on its documented
behaviour** — and then ask the second question: would the naive implementation
be *worse* than doing nothing? Here both answers mattered. The docs were wrong
(no historical state), and even granting the docs, the design was circular for
its own use case. Either finding alone would have justified stopping; finding
them cost one throwaway probe script against ~an hour of building something
actively harmful. **"Deferred item" does not mean "item to build when you get
around to it" — re-validate the premise first, exactly like ADR-0010 taught.**

---

## Checkpoint 15 (2026-07-27) — GitHub Pages port: static-JSON design locked, exporter shipped

**Ask**: host the app from GitHub so a URL can be shared with the league. Ben
supplied his brother's already-hosted reference app as prior art —
[hod-decision-engine](https://github.com/Spunkylysis/hod-decision-engine) plus
its ETL, [fantasy-baseball-etl](https://github.com/Spunkylysis/fantasy-baseball-etl).

### Reference-app facts (inspected directly — expensive to re-derive)

- **Pages, legacy branch build, branch `pybaseball`, path `/`** →
  `spunkylysis.github.io/hod-decision-engine/`. That branch holds **exactly
  one file**, `index.html` (176KB). No build step, no Actions for the site.
- Data = **Supabase**, queried client-side; project URL + anon JWT hardcoded
  as `<input value="…">` defaults in the HTML.
- ETL repo: weekly cron `0 11 * * 1`, scrapes Fantrax, emits `batches/*.sql`,
  `load_supabase_actions.py` TRUNCATE-reloads Supabase via
  `secrets.SUPABASE_PASSWORD`.

**The insight that decided the design**: the two frontends are
architecturally the same. The *only* real difference is **where compute
lives** — his is SQL views inside the database (so a static page can reach
it), ours is Python/pandas in FastAPI (which Pages cannot run).

### Decision (AskUserQuestion): precompute to static JSON, serve from Pages

Rejected mirroring Supabase — its value is a live queryable DB with auth, and
we need neither half (no writes, no auth, no per-user state, inputs change
only when the ETL runs). Rejected FastAPI-on-Railway (Round 2's original
guess): a live server recomputing constants that dies and takes the app with
it.

**Facts that make static sound** (established, not assumed):
- Every GET is a pure function of committed parquet over ~1300 rows.
- **All 11 required parquet are git-tracked** (incl. `fact_trade_log`, the one
  that went missing at Checkpoint 8) → CI builds from a plain checkout, no
  scrape, **no secrets**.
- The frontend's whole network layer is **one function**, `api(path, opts)` at
  `frontend/index.html:214`, 6 call sites → retarget is a one-function change.
- **`/trade/evaluate` moving to JS duplicates no valuation logic.**
  `routers/assets.py:70` sets each player's `"value"` by calling
  `pareto.asset_value("player", …)` — the *same function* `/trade/evaluate`
  sums — and picks use `pv.value_for_pick_row(r, inv)`, exactly what
  `pareto._pick_value` resolves to. The values the client already holds are
  the values the endpoint sums. Only the ~6-line summation moves.

### Perf finding (measured)

`data_access.read_parquet` has **no caching**, and `pareto.asset_value`
re-reads `dim_nfl_players` (25k rows) + re-aggregates the 26k-row dynasty EAV
**per player**. Fine per API request (~45 assets), wasteful across a
1027-asset export: **1.04s → 0.23s per team (~29s → ~6s)** with `lru_cache` on
three readers, payloads **byte-identical**. Memoization lives in
`export_static.py` only — putting it in `data_access.py` would make the
long-lived dev server serve stale data after a pipeline run until restarted.

### Shipped

`mouserat_trade-bud/export_static.py` (new, ~150 lines) — calls the router
functions directly, no logic reimplemented. Ran clean: 28 teams, 196
positional rows, 56 profiles, 28 asset files, **411 KB total but only ~12 KB
per team** (UI loads two at a time). Also `.gitignore` entry for
`mouserat_trade-bud/_site/` so generated JSON can never be committed and
drift from `data/`.

### Privacy — settled

**The repo is already public**, so every number the app shows is already
published as parquet. A Pages site changes **discoverability, not exposure**.
Plan adds `<meta name="robots" content="noindex">` (shareable by link, not
search-indexed); one line, trivially removable.

### Next (steps 2-5, plan approved)

Parity check written but **NOT RUN — result unknown, do not assume it
passes**; rerun first, needs uvicorn on 8420. Then frontend retarget, Pareto
parity + the browser click-through (which finally closes the oldest item on
the project), then `.github/workflows/pages.yml` — **this repo's first
GitHub Action**; no `.github/` exists today.

**Requires Ben**: Pages is not enabled at all (API 404). Needs enabling with
build type **"GitHub Actions"** — a repo settings change, not to be done
unprompted. URL will be
`https://benjamininja.github.io/Python-PowerBI-DynastyFantasyFootball/`.

### Environment gotcha

`Set-Location` **persists across PowerShell tool calls**. After launching
uvicorn from `backend/`, a later `.venv\Scripts\python.exe` failed with "The
module '.venv' could not be loaded". Set-Location back to the repo root
explicitly, or use absolute paths.

---

## Checkpoint 16 (2026-07-27) — static port steps 2-5 shipped and verified

Steps 2-5 of the Round 10 plan are done. Only two items remain, both Ben's:
the browser click-through and enabling Pages.

### The parity check caught a real, silent, site-breaking bug

First run: **27 of 86 checks failed.** Not a checker artifact — the payloads
carry genuine NaNs (a player with no contract value, an unnamed roster copy).
The live API renders them `null`; `json.dumps` writes a bare `NaN` literal,
which **is not valid JSON**. `JSON.parse` rejects the *entire file*, so one
missing contract value would have blanked a whole team — 27 of 28 teams.

The export ran clean and looked fine. Only diffing against the live API
surfaced it. **This is the justification for the verify-against-the-original
step, in concrete form** — a precompute port's failure mode is silent.

Fixed in `export_static.py`: `_nulls_for_nan()` (recursive non-finite →
`None`) + `allow_nan=False` on the dump, so a future miss is a hard error, not
silent invalid JSON. Re-ran: **86 checks, 0 failures.**

**Trap worth remembering**: Python's `json.load` *accepts* `NaN` by default, so
a plain load-every-file sweep passes on this bug. Browser-strict validation
needs `parse_constant=` raising. All 32 emitted files pass that check.

### Second bug: OneDrive holds directory handles

`shutil.rmtree` failed `WinError 5` on `_site/data/assets` — files delete, then
`rmdir` fails, repeatably. Now `ignore_errors=True` + `exist_ok=True` on the
mkdir. Stale *files* (what would actually corrupt a build) still always go; a
surviving empty dir is harmless. CI on Linux unaffected. **Applies to any
generated directory under this repo — it lives in OneDrive.**

### Frontend retarget (step 3)

`api(path)` is now a static-path resolver; **all 6 call sites unchanged**,
including the `?mode=` query string. Per-file promise cache — `profiles.json`
holds all 56 profiles, so a team's second mode costs nothing. `/trade/evaluate`
POST replaced by `evaluateTradeLocal()`, mirroring `pareto.evaluate_trade`'s
summation over `value` fields already in the payload (comment there points at
`backend/pareto.py:45-70` to keep them in step). Backend/Reconnect controls →
"Data as of …" from `meta.json`. Added `noindex` + viewport.

### Pareto parity: exact — with one honest gap

Real mixed basket (A09→A01, 3 give / 3 receive, players and picks both sides):
`give_total`, `receive_total`, `delta`, `asymmetry_pct`, `favors` all match
`/trade/evaluate` **to full float precision**.

**There is no JS runtime on this machine** (no node/deno/bun — checked). So the
arithmetic was verified by transcription against the exported values. That
covers the actual risk (do the shipped values sum to what the endpoint
summed?), but **the JS itself is only exercised by the browser click-through.**

### Step 5

`.github/workflows/pages.yml` — repo's first Action. Push to `main` touching
`data/**.parquet` / `mouserat_trade-bud/**` / the workflow, plus
`workflow_dispatch`; checkout → setup-python 3.11 (pip cache) → install backend
requirements → export → upload-pages-artifact → deploy-pages. `concurrency:
pages` with `cancel-in-progress: false`. No secrets. `.gitignore` already had
`_site/`.

### Serving note

The site **must be served over HTTP** — relative `data/` fetches fail under
`file://`. `python -m http.server --directory mouserat_trade-bud/_site 8500`.

### Still open

1. **Browser click-through** — also closes the oldest item on the project (UI
   never browser-verified, carried since Round 5).
2. **Pages not enabled** (API 404) — needs build type "GitHub Actions", a repo
   settings change, not to be done unprompted. URL will be
   `https://benjamininja.github.io/Python-PowerBI-DynastyFantasyFootball/`.

All uncommitted per the standing rule.

---

## Checkpoint 17 (2026-07-28) — Pages enabled, PR #34 open, docs written

Round 10 is delivered end to end. Nothing is in flight; the only open items
are Ben's.

### Pages is live-configured

Enabled by request via
`gh api --method POST repos/benjamininja/Python-PowerBI-DynastyFantasyFootball/pages -f build_type=workflow`
-> `build_type: workflow`, `https_enforced: true`, `public: true`,
`status: null` (= enabled, nothing deployed yet). URL:
`https://benjamininja.github.io/Python-PowerBI-DynastyFantasyFootball/`
**404s until the first successful workflow run.**

### PR #34 — `trade-bud-static-pages` -> `main`, 4 commits

`86f6aa3` exporter + gitignore `_site/` · `c9f33bc` frontend retarget +
client-side Pareto · `1126702` Pages workflow (repo's first Action) ·
`e91c790` docs.

Green before commit: 27/27 tests, `check_data_model.py --check` and
`check_sources.py --check` both clean.

**The deploy fires automatically on merge** — the workflow triggers on
`mouserat_trade-bud/**`, which the PR touches. No manual dispatch needed.

### Documentation — the gap was wider than this round's changes

`mouserat_trade-bud/` had **no documentation at all**: no README, no ADR, no
`CLAUDE.md` section. Four files, not an amendment:

- **`docs/adr/0012-static-export-for-trade-bud.md`** — decision, both rejected
  alternatives (Supabase mirror, Railway FastAPI), and the consequences worth
  not rediscovering. Also records the NaN bug + the transferable verification
  lesson.
- **`mouserat_trade-bud/README.md`** (new) — two run modes and why one codebase
  serves both, layout, commands, gotchas.
- **`CLAUDE.md`** — new subfolder section, so the rules survive into future
  sessions instead of living only in an ADR someone has to think to open.
- **`README.md`** (trade-tool section + URL), **`PLAN.md`** (2026-07-28 working
  state, detail collapsed into the ADR per its own convention).

### Pre-existing drift found, deliberately not fixed

`CONTRIBUTING.md` documents a `main`/`dev` branch structure with PRs flowing
`dev -> main`. **There is no `dev` branch**, locally or on origin, and the last
five PRs all went feature-branch -> `main`. Followed actual practice; flagged
in the PR body rather than fixed, to keep this PR one logical change.

### Environment: PowerShell here-strings, third strike

`git commit -m @'...'@` failed twice — the message split at an inner quote and
git received fragments as pathspecs. Chaining `; git add ...` after the closing
`'@` makes it worse. **Fixed the pattern, not the instance**: write the message
to a scratchpad file and use `git commit -F` / `gh pr create --body-file`. Now
recorded in root `preferences.md` as a standing rule, since this has now cost
time in three separate sessions.

### Still Ben's, unchanged

1. **Merge PR #34** (deploy fires on merge).
2. **Browser click-through** — still the oldest outstanding item on the
   project. No JS runtime on this machine, so `evaluateTradeLocal()` and every
   DOM path remain unexecuted code; merging does not close this.
