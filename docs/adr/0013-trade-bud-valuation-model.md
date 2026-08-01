# Stance-scoped asset valuation with position ceiling and pick/player commensuration

- Status: **accepted** — all five decisions built. Decisions 4–5 designed via HITL grilling 2026-08-01 ([#47](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/47)/[#51](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/51)), implemented 2026-08-01 ([#49](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/49))
- Date: 2026-07-31 (decision 4 corrected 2026-08-01; decisions 4–5 designed via HITL grilling 2026-08-01, see [#47](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/47)/[#51](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/51); decisions 4–5 implemented 2026-08-01, see [#49](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/49))
- Scope: `mouserat_trade-bud/backend/`, `notebooks/04e_dim_position_ceiling.ipynb`, `data/dim_position_ceiling.parquet`

## Context

The original trade-bud asset valuation blended offensive percentile ranks (across 562 players) and IDP percentile ranks (across 123 defenders) into `player_blended_values` as a single currency. This mispriced mixed offensive/defensive trade packages. Furthermore, draft picks were min-max normalized on their own isolated pick-value curve (0–100), causing high-round future draft picks to exceed elite tier-1 players (e.g. 2027 R1 Early reaching 108.4 vs Josh Allen at 100.0).

## Decision

1. **Sqrt-Compressed Position Ceiling (`dim_position_ceiling`)**:
   Calculate positional scarcity using Value Over Replacement (VOR = `max_fpts - replacement_fpts`) per conference. Sqrt-compress VOR (`ceiling = sqrt(VOR)` with `CEILING_EXPONENT = 0.5`) and rescale top = 100 to preserve rank order while compressing extreme gaps:
   - QB: 100.0 / RB: 99.6 / WR: 76.1 / TE: 66.3 / LB: 49.9 / DB: 40.4 / DL: 34.3

2. **Stance-Scoped Asset Pricing**:
   Valuations are evaluated under three team stances (`contending`, `balanced`, `future`):
   - **Contending**: Unadjusted base board values.
   - **Balanced**: Standard baseline board values.
   - **Future-Focused**: Applies a smooth age multiplier `clip(1 + (26 - age) * 0.03, 0.70, 1.20)`.

3. **Pick Stance Scalars**:
   Draft picks apply stance scalars to reflect temporal preference:
   - `contending`: 0.85
   - `balanced`: 1.00
   - `future`: 1.25

4. **Pick / Player Commensuration via Quantile Mapping** — **BUILT** (grilled and signed off 2026-08-01, [#47](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/47); implemented 2026-08-01, [#49](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/49)).
   *Supersedes the linear-rescale mechanism recorded (in error, no code written) on 2026-07-31.*

   For a pick priced by source `S` (KTC or DraftSharks) with curve value `v`:
   find `v`'s percentile rank within `S`'s covered player pool (KTC `value` /
   DS `ds_value` on `fact_dynasty_ranking_metrics` — 463 / 256 players), then
   read off the value at that same percentile of our-scale `value`
   (`data_access.player_values(stance)`), restricted to that same
   source-covered subset, via linear interpolation between order statistics
   (`numpy.percentile` semantics). Monotone by construction, no new hand-set
   constant — rejected the linear-rescale (wrong mechanism, see below) and
   raw value-matched lookup (noisy/non-monotone: rank-correlation source-
   rank↔our-value only 0.945 KTC / 0.873 DS, with real inversions).

   Source blending is **unchanged**: `resolve_pick_value` still averages
   whichever curve sources cover a given `draft_year` (KTC 2026-2028, DS
   2027-2028 only) — now applied to quantile-mapped values instead of raw
   curve percentiles ([#48](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/48), folded into this decision, no separate design needed).

   `_STANCE_SCALAR` (0.85/1.00/1.25) survives, applied *after* quantile
   mapping, then the blended result is **clamped at the source pool's own max
   our-value** — the mechanical enforcement of "no pick, under any stance,
   prices above the highest-valued player it was anchored against." That is
   what closes the 108.4-above-Josh-Allen failure mode for good, rather than
   relying on the scalar happening to stay small enough.

   Round-coverage fallback is unchanged: a pick beyond a source's max covered
   round still floors to that source's last-covered-round price (e.g. KTC
   stops at round 4; 2026 R5+ floors to the R4 price) — quantile mapping only
   changes *how* a covered round is anchored, not this separate rule.

   The mechanism originally recorded (2026-07-31, no code) was a linear
   rescale onto the global player max (`9997.0`), putting a 2027 R1 Early
   (`7115`) at 71.2 base / 89.0 under the future scalar. KTC points are not
   linear in rank: 7115 is the **19th** most valuable asset in a 464-player
   pool (95.9th percentile), so the linear form priced a top-19 asset like a
   mid-tier starter — wrong mechanism, independent of the "no code" error.

5. **Player-Side Scale Fix — Age-Tilt Re-Rank** — **BUILT**
   (grilled and signed off 2026-08-01, [#51](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/51); implemented 2026-08-01, [#49](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/49)).

   The `future` stance's age tilt (decision 2) was applied to the *finished*
   value (`ceiling x percentile`, itself capped at 100), so a tilt >1.0 could
   push a player above 100 — e.g. Jeremiyah Love to 111.5 (percentile 0.978,
   ceiling 99.6, tilt ~1.15). Every other stance caps at 100; `future`
   shouldn't be the exception.

   Fix: fold age into the *ranking*, not the final value. For board-ranked
   players, compute `score = board_percentile * age_tilt`, re-rank that score
   within position to get a new percentile (0→1 by construction — the top
   scorer is always exactly 1.0), then multiply by ceiling last. This cannot
   exceed the ceiling by construction — no clamp or rescale needed, and
   (unlike a post-hoc clamp) it doesn't flatten the exact players the tilt
   exists to reward. Rejected: accept >100 and fix the docstrings (breaks the
   0-100 contract every other stance honors for no real gain); post-hoc
   rescale of the whole position (a *global* compression that dilutes players
   the tilt never touched).

   Scoped to the `ranked` pool only — fallback (fpts-ordered, unranked)
   players keep today's untouched floor-compression math, no age tilt.
   `_age_multiplier`'s constants (pivot 26, slope 0.03, clamp 0.70 to 1.20)
   are reused unchanged, just relocated to operate on `percentile` pre-rerank
   instead of `value` post-ceiling.

## Consequences

- Positional scarcity properly reflects 28-team dual-conference IDP starters without inflating IDP over elite offensive skill players.
- `export_static.py` emits 3 stance-scoped JSON payload sets (`contending`, `balanced`, `future`) that re-rank chips seamlessly in the static UI.
- **Now true (2026-08-01, #49)**: mixed player/pick packages evaluate in one currency. `pick_value.resolve_pick_value` quantile-maps each curve value onto our-scale player value within the source's own covered pool, blends unweighted across sources, applies `_STANCE_SCALAR`, then clamps at the max our-scale value among the pool(s) it was anchored against — a pick can never price above the best player it was anchored against (2027 R1 Early future-stance: 108.4 → 98.4, confirmed below Josh Allen). `data_access.player_values`'s age tilt is folded into the ranking (`score = board_percentile * age_tilt`, re-ranked within board/position pre-ceiling) instead of the finished value, so it cannot exceed the position ceiling by construction (Jeremiyah Love future-stance: 111.5 → 99.6, exactly the RB ceiling). This closes the same class of defect as the `player_blended_values` bug in the Context above.
- **Process consequence**: this ADR reached `accepted` with a green verification run behind it (`check_data_model.py` OK, 27 pytest passed) because **no test under `mouserat_trade-bud/` existed at the time** — all 27 tests lived in `tests/test_04v_minor_contracts.py` and `tests/test_etl_helpers.py` and touched none of this code. A passing suite that cannot exercise the change is not evidence about the change. ADR-0008's standard applies here and had not been extended to this subproject until #49, which added `tests/test_pick_commensuration.py` asserting both invariants (no pick prices above the highest-valued player in its anchoring pool; no player value exceeds its position's ceiling) parametrized across all 3 stances — 6 tests, all passing against real repo parquet.
