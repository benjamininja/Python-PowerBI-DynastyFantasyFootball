# Supabase schema: three schemas, registry-generated DDL, natural keys, locked-down RLS

- Status: accepted. Designed through HITL grilling on 2026-10-02 ([#75](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/75)); not yet built.
- Date: 2026-10-02
- Amends: [ADR-0014](0014-supabase-system-of-record-static-serving.md) consequence "no consumer cutover work". The published snapshot now carries tighter types (decision 8), so Power BI, the bot and trade-bud each get a type pass at cutover. Their read path (the parquet snapshot) is unchanged.
- Scope:
  - `supabase/migrations/` and a new `migrate.yml` workflow
  - `docs/data_model.yml` (the registry) and a DDL generator
  - the `etl_helpers` storage seam (#77) and its snapshot export
  - writers `02d`, `02e`, `04u`, `04y`; the consumers of `data/*.parquet`

## Context

- ADR-0014 made Supabase Postgres the System of Record and kept serving on the parquet snapshot. ADR-0015 put the ETL on GitHub Actions, confined Owner PII to `shared.owner`, and moved ETL state (`etl_run_log`, `change_poll_state`, `review_*`) into the database.
- **Only the ETL connects to the database.** League members get data only through the bot and trade-bud, which read the snapshot.
- The seam inventory ([#74](../research/storage-seam-inventory.md)) found 27 tables. Each one already declares its columns, dtypes and grain in `docs/data_model.yml`.
- Measured against the parquet on 2026-10-02:
  - **Grain breaks:**
    - `fact_dynasty_ranking_metrics` has 1,812 Composite rows with a null `source_player_id`.
    - `fact_fantasy_teams` has 15 duplicates on `(team_key, gsis_id)`.
    - `fact_trade_log` has no declared grain. 90 of its 93 pick legs have no Original Owner, and one row is an exact duplicate.
  - **Clean FK edges:** `gsis_id` (2 orphans, both in combine), `team_key`, `contract_id`, `metric_key`, `asset_id`, `season_id`.
  - **Dirty FK edges:** `player_key`→`dim_rookie_prospect` has orphans in 7 tables. `position_raw`→`dim_position` has 7–16 unmapped values per table. `scorer_id`→`dim_fantrax_crosswalk` has 4,285 orphans in `fact_minor_eligibility`.
- Fantrax now reports a `Minor` contract that `dim_contract` lacks ([#79](../research/inseason-schema-extraction.md)). ADR-0011 is to be reconciled first.

## Decision

1. **Three schemas, nothing in `public`.**
   - `football`: every dim and fact.
   - `shared`: `owner` now; leagues and people later (ADR-0014's per-sport target).
   - `ops`: `etl_run_log`, `change_poll_state`, `review_*`.
2. **Table names equal the parquet file stems** (`football.dim_nfl_players`), keeping the `dim_`/`fact_` prefixes. The export is a 1:1 name→file map.
3. **The registry generates the DDL.**
   - `docs/data_model.yml` gains `sql_type`, `pk` and `fk` per table.
   - A generator diffs the registry against the existing migrations and writes a new timestamped `supabase/migrations/*.sql` for review. Both are committed.
   - A test fails if the registry and the migrations drift.
   - The generator rejects any identifier that is not unquoted snake_case.
4. **Primary key = the registry grain.** Natural and composite keys; no surrogate ids.
5. **Grain fixes before PKs:**
   - `04y` sets `source_player_id = gsis_id` and `source_uid = 'Composite|<gsis_id>'`; the existing Composite rows are backfilled.
   - `fact_fantasy_teams` gains `scorer_id`, and its grain becomes `(team_key, scorer_id)`, Fantrax's native roster key. `gsis_id` and `player_key` stay as nullable columns.
   - **`fact_trade_log` PK = `(transaction_id, asset_id)`**, with `asset_id` → `dim_roster_asset` (ADR-0004). Every pick has an Original Owner, so all unowned pick legs are resolved to a `pick_ref` and minted as assets before the table loads. That also removes the exact duplicate.
6. **Foreign keys on clean edges only.**
   - `DEFERRABLE INITIALLY DEFERRED` FKs on `gsis_id`, `team_key`, `contract_id`, `metric_key`, `asset_id` and `season_id`, so a dim's full replace and its facts commit in one transaction. The 2 combine orphans are fixed first.
   - Dirty edges (`player_key`, `position_raw`, `scorer_id`) are post-run checks (#88) that file to `ops.review_check`. Each one is promoted to a real FK once it is clean. *Per [ADR-0008's amendment](0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88) (decision 10), they file one row per distinct orphan key, scoped to what can be acted on.*
   - The `contract_id` FK is provisional until the `Minor` contract is settled (ADR-0011). *Settled by [ADR-0019](0019-minor-is-a-pre-1st-contract-stage.md): the FK is a clean edge once `dim_contract` has its `Minor` row.*
7. **The EAV fact stays as it is** (one table, same grain). It adds a CHECK `(metric_num IS NOT NULL OR metric_text IS NOT NULL)` and the `metric_key` FK. NaN is normalized to NULL on write.
8. **Tight types at cutover, through to the snapshot.**
   - Nullable integers become `integer`, ISO date strings become `date`, and every all-null column gets a declared type.
   - The parquet export carries those types (`Int64`/`pd.NA`, `date32`). The Power BI M type steps, the bot's formatting and the trade-bud export are adjusted in the same cutover.
   - `divisionId` is renamed `division_id`, across the `02d`/`04u` writers, the registry and the PBI `sourceColumn` cascade.
   - Data tables stay tz-naive (the seam rejects tz-aware input). `ops` tables use `timestamptz`, because they are never exported.
9. **RLS on every table, two logins.**
   - `etl_writer`: no BYPASSRLS. It gets DML grants and an explicit `TO etl_writer USING (true)` policy per table, emitted by the generator. It never uses `service_role` (ADR-0015).
   - A **read-only login is created now**, with SELECT policies on `football` and `ops`, and never on `shared`.
   - `anon` and `authenticated` get no grants and no policies. None of the three schemas is exposed to the Data API.
10. **`shared.owner` is hand-kept and never read in plaintext.**
    - The owner maintains its rows in the SQL editor.
    - `etl_writer` has no grant on the table. It has EXECUTE on one SECURITY DEFINER function, `shared.pii_token_hashes()`, which returns sha256 hashes of lowercased name and username tokens.
    - The PII check hashes the tokens in each data commit and compares them against that list. It runs in the data-commit job, which holds the main-environment secret. PR checks stay email-shape only, because PR jobs get no main-environment secrets.
11. **`ops` tables.**
    - `etl_run_log`: `run_id` uuid PK, `trigger` (daily | poll | weekly | manual), `started_at`, `finished_at`, `status` (running | failed | committed | published), `git_sha`, `snapshot_commit_sha`, `rows_written` jsonb (`{table: n}`), `error`. Every run inserts a row, which is what keeps the project from pausing.
    - `change_poll_state`: `team_key` PK → `dim_fantasy_teams`, `period`, `roster_hash`, `last_polled_at`, `hash_changed_at`, `pending_since` (debounce).
    - **Review queues, interim until after cutover:**
      - Typed tables `review_fantrax_crosswalk`, `review_dynasty_crosswalk` and `review_fuzzy_matches` mirror today's CSV columns, plus `created_at`, `resolved_at` and `resolution`.
      - `review_check` (`check_name`, `table_name`, `row_key` jsonb, `detail` jsonb, `run_id`, `created_at`, `resolved_at`) holds post-run check findings and Drift. *Amended by [ADR-0008's amendment](0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88) (decisions 8–9): it adds `last_seen_at`, a `pending` state for findings inside their grace, and a partial unique index giving one open row per `(check_name, table_name, row_key)`; rows auto-resolve when no longer seen.*
      - A follow-up issue is committed to replace manual orphan review with another resolution approach.
12. **Migrations apply from Actions.**
    - `migrate.yml` runs `supabase db push` in the main-only environment when `supabase/migrations/**` changes on `main`, before the next ETL run.
    - PRs validate migrations against a throwaway Postgres service container, with no secrets.
13. **Scope.** This ADR covers the conventions plus DDL for the 27 current tables and the `ops`/`shared` tables. In-season tables (#81, #86, #96) are added later through the same registry. `dim_contract` gains `Minor` only after ADR-0011 is reconciled (*settled by [ADR-0019](0019-minor-is-a-pre-1st-contract-stage.md)*).

## Alternatives considered

- **Everything in `public` (plus `shared`).** Rejected: `public` is the schema the Data API exposes, and it would need a move when another sport joins.
- **ETL state in `football`.** Rejected: the export would have to skip those tables by name rather than by schema.
- **Dropping the `dim_`/`fact_` prefixes.** Rejected: the seam and the export would need a name map.
- **Hand-written migrations, or a registry derived from them.** Rejected: that means two places to edit per column, or a SQL parser just to rebuild the registry.
- **Surrogate `id` PKs plus a unique grain.** Rejected: every export grows an `id` column, and ids aren't stable across a reload.
- **Moving Composite to its own table, or computing it on read.** Rejected: every consumer of Composite would change.
- **`(team_key, asset_id)` for `fact_fantasy_teams`.** Rejected: every unresolved roster row would need an asset minted first.
- **`(transaction_id, leg_seq)` for the trade log.** Rejected by the owner, because every pick has an Original Owner and the key should say which pick moved.
- **All FKs now, after a full data cleanup.** Rejected: it blocks #77/#93 on cleanup work. **No FKs at all** was rejected too: it leaves no DB-level gate on joins.
- **Mirroring pandas dtypes in phase 1** (what #74 recommended). Rejected by the owner: the database should check types from day one.
- **Keeping today's snapshot dtypes while the DB is strict.** Rejected: that gives two type truths. Consumers absorb the change once.
- **Keeping `divisionId` quoted.** Rejected: every hand-written query would need the quotes.
- **One login, with the read-only role deferred.** Rejected by the owner, who wants a read login ready now. **A writer with BYPASSRLS** was rejected too: RLS would then guard nothing that matters.
- **A PII denylist in an Actions secret**, or an email-only check. Rejected: the names would live in two places, or ADR-0015 decision 4 would go unmet.
- **One generic jsonb `review_item` table.** Rejected: jsonb is clumsy to edit by hand in the table editor.
- **A per-step run log.** Rejected: it duplicates the Discord summary and the Actions logs.
- **Pushing migrations by hand from the PC.** Rejected: the live schema could lag `main`, and it puts the PC back in the loop (ADR-0015).
- **Wide per-source tables instead of the EAV fact.** Rejected: it would reverse the 2026-06-12 refactor.

## Consequences

- **Prerequisites before the first backfill:**
  - the Composite, `fact_fantasy_teams` and combine-orphan fixes
  - the `division_id` rename
  - `fact_trade_log` added to the registry, with its pick legs resolved to Original Owners
  - declared SQL types for the all-null columns
- **The cutover is no longer consumer-neutral.** The snapshot's nullable integers become `Int64` and its date strings become dates. The PBI M types, the bot's rendering and trade-bud's JSON sanitizing each need a pass, tested against the golden round-trip.
- **#74's "mirror pandas in phase 1" guidance is superseded** for types. Its seam interface and migration order stand.
- **The generator owns more DDL than columns:** PKs, FKs, CHECKs, RLS policies and grants all come from the registry, so the registry grows `pk`/`fk`/`sql_type` entries.
- **Two credentials to rotate** (writer and reader) live in the main-only environment, and the owner's admin login stays personal.
- **Dirty edges get FKs as they become clean.** Each promotion is a registry edit plus a migration.
