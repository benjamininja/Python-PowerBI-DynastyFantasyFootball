# Data model

!!! note "Stub"
    This page will describe the star schema of `dim_*` and `fact_*` tables and
    how they join. Until then, see
    [docs/DATA_MODEL.md](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/blob/main/docs/DATA_MODEL.md),
    which is generated from `docs/data_model.yml`.

The main groups of tables:

- **Players and identity:** `dim_nfl_players` (keyed by `gsis_id`),
  `dim_rookie_prospect` (keyed by `player_key` until a prospect signs), and the
  crosswalks that map each source's own player ids to both.
- **League structure:** teams, conferences and divisions, seasons, scoring
  periods, contract types.
- **Rosters and money:** the ledger of roster moves, the roster as it stood at
  each period's lineup lock, dead money, trades, draft picks.
- **In-season results:** points by scoring period and the weekly matchups.
- **Rankings:** rookie rankings by source and phase, and one dynasty fact
  holding every source's values and ranks as rows.
