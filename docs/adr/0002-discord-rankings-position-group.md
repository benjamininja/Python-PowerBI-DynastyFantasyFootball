# Discord rankings board groups by `position_group` and re-ranks per field

- Status: accepted
- Date: 2026-06-13
- Scope: `discord_bot/rankings.py`

## Context

The 2026-06-12 single-EAV refactor retired `fact_dynasty_rankings` and dropped
each source's own position label from the fact. The bot now reads
`fact_dynasty_ranking_metrics` (the source-prefixed `{ktc,ds,fp}_positional_rank`
keys) and gets player identity — including position — from `dim_nfl_players` via
`gsis_id`.

`dim_nfl_players` exposes two position columns:

- `position` — granular nflverse codes (DE, DT, NT, OLB, ILB, MLB, CB, FS, SS, …)
- `position_group` — coarse (offense QB/RB/WR/TE; defense DL/LB/DB)

Each dynasty source ranks within *its own* position scheme, which is not the
nflverse granular scheme. Verified against the regenerated 2026-06-13 snapshot:
FantasyPros ranks IDP sub-positions **separately** (DE 1..29 and DT 1..15 each
start at 1). The source's original position label no longer exists on the fact,
so it cannot be reconstructed.

## Decision

1. Group the board by `dim_nfl_players.position_group`, not `position`.
2. Re-rank 1..N within each displayed group by source positional-rank order
   (`groupby("position").rank(method="first")`).

## Alternatives rejected

- **Group by granular `position`** — shatters each source's single rank list
  across many fields with duplicate-looking `#1`s. IDP exploded to 11 fields
  (CB/DB/DE/DT/FS/ILB/LB/MLB/OLB/S/SAF) with non-contiguous, co-ranked numbers.
- **Keep raw source rank under `position_group`** — DL/LB/DB still show co-ranked
  entries (two `#1`s) because the source ranked sub-positions separately.
- **Reconstruct the source's exact grouping** — impossible; the source position
  label was dropped from the fact in the refactor.

## Consequences

- Offense is unaffected — `position_group` == `position` for QB/RB/WR/TE, and the
  re-rank is a no-op there (the source already ranks within those positions).
- IDP collapses to clean DL/LB/DB fields with a contiguous 1..N sequence.
- The board's position vocabulary is now `position_group` codes
  (QB/RB/WR/TE/DL/LB/DB); the `position` command arg expects those.
- Displayed rank is the **board-ordinal within the field** — equal to the
  official source positional rank for offense, diverging for IDP where the
  source grouped differently (user-chosen; coherent with the field label).
- Dual-eligible players land in their registry `position_group` (e.g. Travis
  Hunter, registry CB → `DB`, appears in a small DB field on the SF board).
- **Do not revert grouping to `position`** — it is a known regression that
  produces fragmented, duplicate-ranked fields.
