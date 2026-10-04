# `notebooks/`

ETL notebooks that build the Parquet tables in `../data/`. Numbered in run order.

## Numbering convention

`NN<letter>_name` — the **group prefix** is the project pattern; the **letter** is
order within the group (`x`/`y`/`z` reserved for late-stage / apply / resolver steps):

| Prefix | Domain |
|---|---|
| **01** | Core **dimension** tables (registries, transformers, seeds) |
| **02** | Core **fact** tables (combine metrics, schema seeds) |
| **03** | **Rookie-ranking** tables & processes (draft-class expert ranks → `fact_rookie_rankings`) |
| **04** | **Dynasty-ranking** tables & processes (whole-roster value/ranks → `fact_dynasty_ranking_metrics`, plus Fantrax) |

> **Run convention:** execute every notebook with **CWD = repository root** (not `notebooks/`),
> so relative paths like `data/...` resolve. The shared module is imported via a small
> bootstrap that adds `notebooks/` to `sys.path` regardless of CWD.

## Environment setup

`requirements.txt` at the repo root is the single source of truth for the
`.venv` dependency list — install/refresh with:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Includes `nbformat`/`nbclient`/`nbconvert`, needed only for headless notebook
execution (`python -m nbconvert --to notebook --execute --inplace ...` — CI,
Claude Code, scheduled jobs), not for interactive VS Code editing. If a
notebook run fails on `ModuleNotFoundError`, add the package here rather than
`pip install`-ing it ad hoc — this file is what keeps re-runs reproducible.

## Running the `.py` scripts

Launch the `.py` scripts (`04a`, `04w`, `02d`, `02e`, …) through the repo-root
launcher so they always use the project venv:

```powershell
.\run.ps1 notebooks\04w_fantrax_draft_results.py        # extra args pass through
```

`run.ps1` pins `.venv\Scripts\python.exe`. Don't use VS Code's "Run Python File"
or a bare `python x.py` — those pick the *selected* interpreter (usually anaconda
base), which lacks `playwright` and ships a broken `pyarrow`
(`Repetition level histogram size mismatch`). The repo has two venv folders
(`venv\` and `.venv\`); the launcher pins the correct one.

## Shared module

- **`etl_helpers.py`** — single source of truth for `LeagueConfig`, `clean_player_name`,
  `generate_player_key`, `parse_height_to_inches`, `_make_session`, `_parse_rank_date`,
  `add_players_from_source`, `ingest_ranking_source`, `append_review`. The notebooks import
  from it rather than carrying copies.
- **`etl_checks.py`** — the publish-gate check suite (ADR-0008 amendment, #115).
  It runs Table Gates (grain, required keys, schema, shrink) with parameters from
  `docs/data_model.yml`, plus domain checks (coverage), and files Review findings
  to `data/review/review_check.csv`. `scripts/run_pipeline.py` runs it after each
  Chain; `--check-only` runs it alone.

## Notebooks

| # | Notebook | Output |
|---|---|---|
| 01a | `01a_dim_rookie_prospect.ipynb` | `dim_position`, `dim_school`, `dim_rookie_prospect` |
| 01b | `01b_dim_contract_seed.ipynb` | `dim_contract` |
| 01c | `01c_dim_fantasy_teams_seed.ipynb` | `dim_fantasy_teams` (from Google Sheet) |
| 01d | `01d_dim_nfl_teams_seed.ipynb` | `dim_nfl_teams` |
| 01e | `01e_dim_nfl_players_seed.ipynb` | `dim_nfl_players` (maps nflverse names → canonical schema) |
| 01f | `01f_dim_season_seed.ipynb` | `dim_season` (calendar spine, current+2; ADR-0004) |
| 02a | `02a_fact_nfl_combine_pro_day_metrics.ipynb` | `fact_nfl_combine_pro_day_metrics` |
| 02c | `02c_fact_rookie_rankings_seed.ipynb` | `fact_rookie_rankings` (schema seed) |
| 02d | `02d_fact_roster_transactions.py` | `fact_roster_transactions` ledger + `dim_roster_asset` + `fact_draft_pick` (replay from 04w JSON), plus the trade / claim / drop legs and `fact_trade_log` from 04t's capture. Each move's contract is read off `fact_roster_state` by the Scoring Period Fantrax says the move takes effect in (the `week` cell): a draft pick and a claim read the first Roster State inside the stint they start, a trade and a drop the latest one before they take effect; else it is defaulted (`Minor` if minors-eligible; ADR-0019). A pick's or a claim's salary is read off the preseason capture (`fact_preseason_salary`) or that first Roster State, else the draft-season ADP salary floored at the league minimum (pick) or the inherited salary / league minimum (claim) |
| 02e | `02e_fact_fantasy_teams_derive.py` | `fact_fantasy_teams` (ledger replay → current roster/contracts). `roster_status` is stamped from the newest Scoring Period in `fact_roster_state` (Starter → `Active`, Bench → `Reserve`, IR → `Inj Res`, Minors → `Minors`) |
| 03a | `03a_fantasypros_rankings.ipynb` | FantasyPros PPR + Superflex (scraped) |
| 03b | `03b_walterfootball_rankings.ipynb` | WalterFootball positional ranks (scraped) |
| 03c | `03c_ktc_rankings.ipynb` | KeepTradeCut consensus (scraped) |
| 03d | `03d_draftsharks_rankings.ipynb` | DraftSharks top-90 (scraped) |
| 03x | `03x_manual_rankings.ipynb` | RotoBaller, mystery_iono, DLF, FantasyCalc, FP IDP (Excel) |
| 03y | `03y_dim_player_alias.ipynb` | `dim_player_alias` (backfill from archived reviews) |
| 03z | `03z_apply_fuzzy_review.ipynb` | Applies `data/review/review_fuzzy_matches.csv` decisions |
| 04a | `04a_fantrax_weekly_scrape.py` | `fact_fantrax_adp` — **scheduled script** (Task Scheduler), Playwright |
| 04b | `04b_ktc_dynasty_rankings.ipynb` | `fact_dynasty_ranking_metrics` (overall/positional rank folded in as metric_keys) + `dim_dynasty_crosswalk` (KTC, embedded-HTML scrape) |
| 04c | `04c_dim_dynasty_metric.ipynb` | `dim_dynasty_metric` — curated index for `metric_key` (label/group/order/direction); matrix column axis |
| 04d | `04d_draftpick_value_curve.ipynb` | `dim_pick_value_curve` — KTC RDP (Early/Mid/Late tercile) + DraftSharks dynasty TE-premium-SF (flat per-round) pick-value buckets by `(snapshot_date, source_name, draft_year, round, tier)`. Not part of the player-identity EAV — mouserat_trade-bud pick valuation, resolved to real `fact_draft_pick` rows in that project's backend |
| 04p | `04p_fantrax_league_info.py` | Fantrax's public no-auth `getLeagueInfo` — **scheduled script** (after 01f): `dim_scoring_period` (all 17 Scoring Periods with exact bounds, `is_playoff`, and the Update-Set state `open` / `closing` / `closed`) + `dim_division` (the season's Division name per Conference; replaces the Sheet-sourced `01g`, now in `archive/`). Fails, and holds the Chain, unless each Fantrax division maps to exactly one Conference. No period is `closed` until the scoring Close checks land (#118, #116) |
| 04r | `04r_fantrax_roster_state.py` | Fantrax's public no-auth `getTeamRosters?period=N` — **scheduled script** (after 04p): `fact_roster_state`, the Roster State of each regular-season Scoring Period (Roster Slot `Starter` / `Bench` / `IR` / `Minors`, salary, contract), replace-by-`(season_id, period)`. Reads every period that has started and is not `closed`, never one past the period Fantrax calls current (Fantrax answers a future period with the current roster). Fails, and holds the Chain, on a reply for the wrong period, a team set other than `dim_fantasy_teams`', an unknown status or a contract not in `dim_contract`. `02d`, `02e` and `04e` read it |
| 04s | `04s_fantrax_inseason_capture.py` | Internal `fxpa/req` RPC, logged in — **manual run** for now (#118 makes it a scheduled step): raw capture only, `data/raw/fantrax_inseason_{season}_schedule.json` (every week's matchups and scores) + `_p{NN}.json` per Scoring Period (`getLiveScoringStats` with the bench view, so Starters and non-starters; `getStandings`, plus two by-period standings probes). Each file is stamped `captured_at`. Nothing parses it yet: `fact_period_scoring`, `fact_matchup` and `fact_standings` are #118's next PRs |
| 04t | `04t_fantrax_transaction_history.py` | Internal `fxpa/req` RPC `getTransactionDetailsHistory` (`team="ALL"`, all pages): raw trade-history capture `data/raw/fantrax_txn_history_{season}.json` — parsed downstream by `02d` into `fact_roster_transactions` `trade`/`trade_away` events (player assets) + `fact_trade_log` (all traded assets, incl. picks; trade-activity signal for mouserat_trade-bud) |
| 04u | `04u_fantrax_public_api.py` | Fantrax's public no-auth `fxea/general` REST API: `getDraftPicks` → `fact_draft_pick_future` (real 2027-2028 pick ownership, incl. pick-for-pick trades). Manual run |
| 04v | `04v_minor_contracts.py` | Minors eligibility — **scheduled script** (after 04a), read-only: Fantrax's own minors-eligibility verdict (GP ≤ 19) → `fact_minor_eligibility`. `02d` reads it for the `Minor` default when no Roster State row covers a move (ADR-0019). Roster Slots, salaries and contracts come from `04r`, not from here |
| 04w | `04w_fantrax_draft_results.py` | Raw `getDraftResults` JSON per division (live startup-draft capture) — parsed downstream by `02d` |
| 04x | `04x_manual_dynasty_rankings.ipynb` | ↑ same dynasty tables ← DynastySharks (SF/TEPP) + FantasyPros (SF/IDP) from `data/raw/DynastyRankings_2026_ManualExtraction.xlsx` |
| 04z | `04z_fantrax_crosswalk.ipynb` | `dim_fantrax_crosswalk`; back-fills fact FKs |

The `.py` rows (`02d`, `02e`, `04a`, `04p`, `04r`, `04v`, `04w`) are the headless Fantrax
scraper/replay cluster — launched via `run.ps1` (see above), not notebooks.

## Scheduled pipeline (orchestrator)

The weekly refresh runs through `scripts/run_pipeline.py`, a **phase-aware
orchestrator** (INSEASON / PRESEASON / OFFSEASON, derived from 04a's week
label + the season calendar). It runs, in dependency order:
`01f → 04p → 04r → 01e → 04a → 04z → (04a --backfill-gp, in-season) → 04v → 02d → 02e
→ (04b, offseason)`, surfaces review-queue row counts, commits refreshed
`data/*.parquet` (allowlisted data-only commit — see CONTRIBUTING.md), and
notifies via Discord webhook (`DISCORD_WEBHOOK_URL` in `.env`, optional).

- Entry point: `.\run_weekly.ps1` (console log →
  `data\outputs\pipeline_runs\`); register the Windows scheduled task
  reproducibly with `.\scripts\register_scheduled_task.ps1` (default
  Thursday 06:00; `-Unregister` to remove).
- Testing: `.\run.ps1 scripts\run_pipeline.py --dry-run [--phase X]
  [--steps a,b] [--no-commit] [--no-push]`.
- `--profile dynasty` appends `04b → 04c → 04y` (run after refreshing the
  04x manual Excel).
- **Never scheduled**: the live-draft chain (`04w → 02d → 02e → 05a`), the
  03-group rookie chain (manual Excel gates), and review applies (`03z`,
  `apply_fantrax_crosswalk_review`). No step writes to Fantrax — the one
  write-side path (`04v --apply`) was removed along with its contract
  worklist (ADR-0011).

### Dynasty rankings (04) — single EAV fact

Dynasty sources expose **incompatible metric vocabularies** (KTC trade value/tiers/trends;
DynastySharks 1/3/5/10-yr projections; FantasyPros best/worst/avg/std-dev). The 2026-06-12
refactor (ADR-0002) collapsed the former two-layer backbone+companion model into **one
long EAV fact** — even rank is just another metric:
- `fact_dynasty_ranking_metrics` — **long EAV** (`metric_key → metric_num/metric_text`),
  grain `snapshot_date × source_name × source_player_id × format`. Overall/positional rank
  fold in as source-prefixed metric_keys (`ktc_overall_rank`, `fp_positional_rank`, …);
  new sources/metrics add rows, never columns. (The separate `fact_dynasty_rankings`
  ranking backbone is **retired**.)
- `dim_dynasty_crosswalk` — `(source, source_player_id) → gsis_id + player_key` (unified across sources).
- `dim_dynasty_metric` — curated index for `metric_key` (`metric_label`/`metric_group`/`metric_order`/`direction`); use as the matrix **column axis**, sort `metric_label` by `metric_order`. The 6 per-source rank rows are generated from `SOURCE_PREFIX` (one source list shared with `04b`/`04x`).

Formats are a dimension (`SF`, `TEPP`, `IDP`, …). Sources: KTC = `04b` (scrape),
DynastySharks + FantasyPros = `04x` (manual Excel). Identity is resolved by the
**shared** `etl_helpers.resolve_dynasty_crosswalk` (one matcher for all sources;
each source notebook upserts its own rows + passes nickname overrides).

## Credentials (not in git)

- `.env` — Fantrax login for `04a` (`FANTRAX_EMAIL`, `FANTRAX_PASSWORD`). Gitignored.
