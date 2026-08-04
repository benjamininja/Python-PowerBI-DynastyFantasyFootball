# RESUME — trade-bud: FA-claim wayfinder map + 2nd live-test bug (2026-08-04)

**Files touched this session**: `mouserat_trade-bud/frontend/index.html`
(uncommitted, local `main`), `.claude/memory/mouserat-trade-bud.md`,
`PLAN.md`, plan file `C:\Users\benha\.claude\plans\lucky-sleeping-snowglobe.md`.

**Next task**: Run `gh issue create` for the wayfinder map + its 2 child
tickets (plan approved, not yet executed on GitHub) — see "Wayfinder map to
create" below.

## Code changed this session (uncommitted)

`evaluateTrade()` (`mouserat_trade-bud/frontend/index.html:691-695`) —
early-return branch (both baskets empty) now also resets `giveTotal`/
`receiveTotal` text to `'0'` and `barGive`/`barReceive` widths to `'0%'`.
Bug: after a team swap correctly cleared the basket, the old Give/Receive
totals and bar kept displaying (`onTeamChange`'s clear worked; only the
total display didn't refresh). Not yet committed, not yet rebuilt into
`_site/`.

**Command to run next**: from `mouserat_trade-bud/`,
```
../.venv/Scripts/python.exe export_static.py
```
then restart the `:8500` server (kill existing PID first — check with
`netstat -ano | grep ':8500'`), then have Ben hard-refresh and re-verify the
Give/Receive totals reset correctly on a team swap. Then commit → new
branch → PR (same convention as #53).

## Wayfinder map to create (approved plan, not yet run)

Full spec in `C:\Users\benha\.claude\plans\lucky-sleeping-snowglobe.md`.
Summary: destination = spec for closing the FA-claim identity-resolution
gap (12 roster rows, `acquired_method="claim"`, null `gsis_id`/`player_key`).
Reframed by an Explore pass: claims use the *same* identity-resolution path
as everything else (`02d_fact_roster_transactions.py:158-175`); the real gap
is `04z_fantrax_crosswalk.ipynb`'s match universe never including `04t`
claim/drop scorer_ids. 9 of 12 nulls are likely just stale pipeline output
(crosswalk already resolved them 2026-07-31; `dim_roster_asset` last built
2026-07-26).

Tickets to create as children of the map (label `wayfinder:map`):
1. `wayfinder:task` — rerun `04z_fantrax_crosswalk.ipynb` then
   `02d_fact_roster_transactions.py`, diff the 12 known nulls against
   refreshed output, report which scorer_ids are still genuinely unresolved.
2. `wayfinder:grilling`, blocked by (1) — how to extend `04z`'s match
   universe to cover claim-only players (always union `04t` scorer_ids?
   handle no-longer-rostered names? one-off backfill vs. standing change?).

Out of scope for this map: the older 17-row `acquired_method="startup_draft"`
null-identity gap (separate, already-logged).

## Also resolved this session (informational, no action needed)

The "$0 minors contract" report from last session was **not a code bug** —
root cause was a stale served `_site/` build (source was already correct,
`export_static.py` just hadn't been rerun since the prior fixes). Fixed by
rebuild + server restart. Lesson banked in
[mouserat-trade-bud.md](mouserat-trade-bud.md): always rebuild+restart after
an `index.html` edit before asking Ben to re-verify.
