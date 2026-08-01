# Stance-scoped asset valuation with position ceiling and pick/player commensuration

- Status: accepted
- Date: 2026-07-31
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

4. **Pick / Player Commensuration via KTC Scale**:
   Both player values (`fact_dynasty_ranking_metrics` where `source_name = 'KTC'`) and pick values (`dim_pick_value_curve` where `source_name = 'KTC'`) share KeepTradeCut's native point currency. Draft pick values are re-anchored directly to the player KTC scale (0–100) using the global player max (`9997.0` points).
   - Under Future-Focused stance, a 2027 R1 Early (`7115` KTC points) maps to **71.2** base / **89.0** stance-adjusted, placing top future picks appropriately below tier-1 elite superstars (100.0).

## Consequences

- All mixed player/pick trade packages evaluate in one unified, mathematically sound currency.
- Positional scarcity properly reflects 28-team dual-conference IDP starters without inflating IDP over elite offensive skill players.
- `export_static.py` emits 3 stance-scoped JSON payload sets (`contending`, `balanced`, `future`) that re-rank chips seamlessly in the static UI.
