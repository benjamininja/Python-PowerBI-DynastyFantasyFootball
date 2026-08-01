---
name: trade-bud-valuation
description: mouserat_trade-bud asset valuation = position ceiling x within-position percentile, stance-selected board + age/pick knobs (ADR-0013, all 5 decisions built as of 2026-08-01, #49) — quantile-mapped picks, age-tilt-folded-into-rank players, both invariant-tested in tests/test_pick_commensuration.py
metadata:
  type: project
---

# Asset valuation redesign (2026-07-31) — ADR-0013

**Locked formula.** `value = position_ceiling(pos) x within_position_percentile`,
where the percentile comes from the ranking board the *stance* selects.

Five decisions, locked in [ADR-0013](docs/adr/0013-trade-bud-valuation-model.md):

1. **Stance selects a ranking SOURCE.** Contending reads the DraftSharks
   *redraft* tree (`dsr_*`); Balanced/Future read the *dynasty* boards (`ds_*`
   + KTC + FantasyPros). Same rule for offense and defense.
   **AMENDED 2026-07-31** — the original form of this decision ("a source,
   *never* a tuned weight") was reversed by Ben after the browser click-through
   proved Balanced and Future produced byte-identical values on both tabs (2
   distinct value sets across 3 chips): there is only one dynasty board set, so
   two of three stance chips were a visible no-op. Future is now differentiated
   by two hand-set knobs, and they are the only two in the system:
   - `data_access._age_multiplier` — `clip(1 + (26 - age) * 0.03, 0.70, 1.20)`,
     applied to the finished value, **future stance only**. Continuous, not
     bucketed, so nobody loses value overnight on a birthday. Missing
     `birth_date` → 1.0 (ignorance is not evidence of age).
   - `pick_value._STANCE_SCALAR` — `{contending: 0.85, balanced: 1.00,
     future: 1.25}` on the pick curve.
   Verified after: 3 of 3 distinct on both tabs, zero console errors.
2. **Both DraftSharks trees get pulled.** Redraft ordering is expert-produced
   and is not derivable from the dynasty columns (measured rank spearman 0.792;
   rookie QBs sit ~650 places higher in dynasty, kickers ~600 higher in redraft).
3. **Replacement level is a 14-team, per-conference computation.** The two
   conferences are genuinely separate player pools — a player rostered in
   conference A is not acquirable by a conference-B manager.
4. **Ceiling is a MULTIPLIER on the within-position percentile, never the whole
   valuation.** That is the guard against one position owning the whole board.
5. **Pick / Player Commensuration — BUILT 2026-08-01 (#49).** A parallel
   agent session had once recorded this as "Resolved 2026-07-31" (linear
   rescale on the global player max `9997.0`); that was corrected — no code
   was ever written under that record, and the mechanism was wrong anyway
   (see below). The real design was grilled with Ben ([#47](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/47),
   closed 2026-08-01): **quantile mapping** — a pick's percentile within its
   source's covered player pool maps onto the same percentile of our-scale
   player value, restricted to that source-covered subset, via linear
   interpolation between order statistics. Stance scalar survives, applied
   after mapping, then clamped at the source pool's own max our-value.
   Implemented in `pick_value.py` (`_source_pool`, `_percentile_of`,
   rewritten `resolve_pick_value`; `_with_percentiles` deleted). KTC's fact-
   table pool is `source_name=="KTC", metric_key=="value"`; DraftSharks'
   pick-curve label maps to `source_name=="DynastySharks",
   metric_key=="ds_value"` on `fact_dynasty_ranking_metrics` (same entity,
   different label per ingest pipeline — see `_SOURCE_METRIC`). Verified:
   2027 R1 Early future-stance 108.4 → 98.4, below Josh Allen.
6. **Player-side >100 overflow under `future` — BUILT 2026-08-01 (#49).**
   The age tilt (decision 1's second knob) was applied to the finished
   value, so it could push a player past the 100 ceiling every other stance
   honors (Jeremiyah Love → 111.5). Grilled with Ben ([#51](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/51),
   closed 2026-08-01): fold age into the *ranking* instead — blend
   `board_percentile * age_tilt` into a score, re-rank that score within
   (board, position_group) (0→1 by construction), multiply by ceiling last.
   Can't exceed the ceiling by construction. Scoped to the `ranked` pool
   only; fallback (fpts-ordered) players untouched. Implemented in
   `data_access.player_values` (rerank happens on the per-board `ranks`
   frame, before the cross-board average that produces `ranked`; the old
   post-value `_age_multiplier` call is deleted). Verified: Jeremiyah Love
   future-stance 111.5 → 99.6, exactly the RB ceiling (percentile 1.0).

## Why the old code was wrong

`data_access.player_blended_values(fmt)` percentiled each source's overall rank
**within a whole format pool**, and `pareto._FORMAT_BY_POSITION_GROUP` then
routed offense to `SF` and IDP to `IDP` and **summed the two percentiles as one
currency**. An 80th-percentile DB and an 80th-percentile QB are drawn from
unrelated pools, so every mixed offense/IDP package was mispriced. Both the
blend and the format map are deleted.

## `dim_position_ceiling` (notebooks/04e)

Grain `(snapshot_date, conference, position_group)`, conference in {A, B, ALL}.
VOR = `max_fpts - replacement_fpts`, where replacement = **best free agent** at
that position (opportunity cost: what you can get for nothing). `ALL` averages
VOR across conferences *before* rescaling, so a price never depends on which
conference copy is traded. Rescaled so the top position = 100.

`ceiling = vor ** CEILING_EXPONENT`, rescaled so the top position = 100.
**`CEILING_EXPONENT = 0.5` (sqrt), set 2026-07-31** — the notebook's one knob.
At `1.0` (raw VOR) the *ordering* was right but the magnitude was untradeable:
WR1 Ja'Marr Chase priced 57.9, below RB48 and QB25, and the top 50 assets
league-wide held zero WR, TE or IDP. A concave transform is monotone, so no
position's rank moves — only the gaps narrow, and Chase lands at ~RB26. `vor`
is stored raw, so the exponent is re-settable without re-pulling anything.

Result, and the *ordering* is what was predicted rather than tuned for:

| pos | max_fpts | replacement | vor | ceiling (sqrt) | raw-VOR ceiling |
|---|---|---|---|---|---|
| QB | 411.4 | 14.8 | 396.6 | 100.0 | 100.0 |
| RB | 458.6 | 65.1 | 393.4 | 99.6 | 99.2 |
| WR | 334.9 | 105.2 | 229.7 | 76.1 | 57.9 |
| TE | 274.6 | 100.2 | 174.4 | 66.3 | 44.0 |
| LB | 350.5 | 251.7 | 98.9 | 49.9 | 24.9 |
| DB | 321.8 | 257.1 | 64.7 | 40.4 | 16.3 |
| DL | 287.4 | 240.8 | 46.6 | 34.3 | 11.7 |

**LB outscores TE on raw points (350.5 vs 274.6) yet prices at half of it** —
the offense/defense meta-scarcity, falling out of VOR with no weighting knob.
QB replacement really is near-zero (best FA ~20 fpts): 28 teams roster
essentially every NFL starter in superflex. That is real, not an artifact.

## The ingest defect this uncovered

The first ceiling run produced nonsense (TE had *zero* free agents). Root cause
was **not** a missing pull — it was a parse-time filter asymmetry in
`04a_fantrax_weekly_scrape.py::extract_ranked_board`: offense rows survived only
with a non-null global Fantrax ADP (offense-only, ~282 players) while IDP rows
survived on active-roster alone (~1374). Offense was truncated 3-5x. See
[fantrax-players-grid](fantrax-players-grid.md).

## Commensuration + player-scale fix — BUILT 2026-08-01 (#49)

Full design detail lives in [ADR-0013](../../docs/adr/0013-trade-bud-valuation-model.md)
decisions 4-5 (quantile mapping for picks, age-tilt re-rank for players) — see
locked decisions 5-6 above for the summary. Probe data and rejected
alternatives (linear rescale, raw value-matched lookup, post-hoc clamp,
global rescale) are on GitHub issues [#45](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/45)/[#47](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/47)/[#51](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/51),
not duplicated here.

Both defects are fixed as of #49: `pick_value._with_percentiles` is deleted
(replaced by quantile mapping + pool-max clamp); `player_values()` folds the
age tilt into the pre-ceiling rank so it cannot exceed 100 under any stance.
`mouserat_trade-bud/` now has test coverage —
`tests/test_pick_commensuration.py` (repo-root `tests/`, not under the
subproject) asserts both invariants (no pick prices above the highest-valued
player in its anchoring pool; no player value exceeds its position's
ceiling), parametrized across all 3 stances, 6 tests, run against real repo
parquet with the same one-shot `lru_cache` memoization `export_static.py`
uses (otherwise `resolve_pick_value` re-derives the whole player universe
per pick).

## Fallback for uncovered players

Boards cover ~97% of rostered copies on the dynasty pool, ~92% on redraft
(QB redraft weakest at ~72%). Unranked players are ordered among themselves by
fantasy points, then **compressed into the band below the worst ranked player at
that position**. Ranking them on the open 0-1 scale instead put the best
unranked QB at 1.000 — ahead of every QB the experts actually rated — because
his pool was only the leftovers. This bug was caught and fixed; do not
reintroduce it.

Related: [[mouserat-trade-bud]], [[data-model]], [[fantrax-players-grid]].
