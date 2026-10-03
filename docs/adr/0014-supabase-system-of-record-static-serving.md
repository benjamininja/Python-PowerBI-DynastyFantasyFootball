# Supabase is the ETL's system of record; serving stays a static published snapshot

- Status: accepted. Designed through HITL grilling on 2026-09-26 ([#72](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/72)); not yet built. Amended by [ADR-0015](0015-etl-on-github-actions-owner-pii-confined.md) (2026-09-27): the ETL runs on GitHub Actions, so the rejected Actions keep-alive's "DB credentials in Actions secrets" reason no longer holds; Change Poll host and interval are set there.
- Date: 2026-09-26
- Amends: [ADR-0012](0012-static-export-for-trade-bud.md). Its "no database" framing and its rejected Supabase alternative are re-scoped to *serving*; the rest of ADR-0012 stands.
- Scope:
  - the `etl_helpers` storage seam (#74/#77)
  - `supabase/migrations/`
  - `scripts/run_pipeline.py` (snapshot publish)
  - the consumers of `data/*.parquet`: Power BI, `discord_bot/`, `mouserat_trade-bud/`

## Context

Storage is moving off parquet-in-git (map #69) because the in-season ETL (maps #70/#71) moves to a **daily run with a weekly update-set**. The owner set two priorities:

1. **ETL data correctness is first-class.** Bad data is death.
2. **The app and bot stay live for league members at all times.**

Established by inspection and research ([#73](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/73), [#80](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/80)):

- **Our serving is already always-on without a database.**
  - trade-bud is static JSON on GitHub Pages (ADR-0012).
  - The Discord bot on Railway reads parquet from GitHub.
  - Neither one can pause.
- **The reference app (HoD) is live.** It is GitHub Pages querying Supabase client-side, fed by a weekly TRUNCATE-reload. That weekly write is the only thing keeping its free project inside the 7-day inactivity window. A longer idle stretch pauses the project, and the app goes down with it.
- **Supabase Free:**
  - pauses after 7 days without DB activity; dashboard visits don't count
  - has **no backups** and no PITR
- **Supabase Pro:** $25/mo per org; no pause, daily backups kept 7 days, 8 GB.
- **Size is not a constraint.**
  - Our ~4 MB of parquet is roughly 20–60 MB in Postgres with indexes.
  - HoD is about 12 tables of at most a few thousand rows each.
  - In-season growth, per year:
    - player-week snapshot: ~20k rows (28 teams × ~40 players × 17 weeks)
    - nflverse weekly: ~40k rows
  - That totals a few MB a year, so both leagues fit inside 500 MB for years. **Uptime and backups, not size, drive the tier.**
- **Fantrax has no webhooks.** The public `fxea` API has no transactions method, but `getTeamRosters` is public, historical, and changes whenever a trade or add/drop completes.
- **Power BI service refresh against Supabase needs an on-prem gateway.** Microsoft's cloud does not trust Supabase's CA.

## Decision

1. **Supabase Postgres is the system of record.**
   - Every ETL write goes through the storage seam (`etl.write_table`) into Postgres.
   - PK, unique and FK constraints reject bad or duplicate rows *at write time*. This is the correctness gate parquet never had.
2. **Consumers read a published snapshot, never the store.**
   - After a run, the seam exports the record to `data/*.parquet`.
   - `run_pipeline.py` commits that export to `main` (the existing change-detected commit).
   - Power BI, the bot and trade-bud read only that snapshot, so serving survives a paused or unreachable database.
3. **Publish only a good run.**
   - The snapshot is exported only after the run's DB transaction commits and its post-run checks pass (the test strategy is #88).
   - A failed run publishes nothing, and the last good snapshot keeps serving.
   - *Amended by [ADR-0008's 2026-10-03 amendment](0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88) (#88): the publish unit is a Chain. A failed Chain publishes nothing and the other Chains still publish.*
4. **The snapshot refreshes on change, not just on schedule.**
   - Refresh triggers:
     - the daily run
     - the weekly update-set
     - a **Change Poll**: a no-auth hash of each team's current-period `getTeamRosters`
   - When the hash changes, the Change Poll triggers the authed transaction path (`04t` → `02d` → `02e` → upsert → export).
   - The poll's host and interval belong to [#87](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/87)/[#82](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/82).
5. **Free-tier pause and backups.**
   - **Keeping the project active:** the daily run continues year-round, including the off-season, and every run inserts an `etl_run_log` row, so the project never reaches 7 idle days.
   - **If the project pauses anyway:** the run fails loudly in the Discord run summary, serving continues from the snapshot, and resuming is a manual dashboard click.
   - **Backup:** schema = `supabase/migrations/`; data = the git snapshot.
6. **Power BI stays on the parquet snapshot.**
   - The `File.Contents(...parquet)` M sources are untouched.
   - That means no gateway, no CA workaround and no rewrite of the 17 table sources.
7. **Staged hosting.**
   - **Now:** Free tier.
   - **Trigger for Pro + live reads:** any one of these:
     - a combined multi-sport league app
     - user writes or auth
     - linking with James's HoD project
   - **Target shape:** **one "league platform" project**, with a schema per sport (`football`, `baseball`) plus `shared` (owners, leagues, people). Both apps link through `shared`.

## Alternatives considered

- **Supabase as a serving mirror, with parquet as the truth.** Rejected. The database would add no integrity gate, only a second write and a component that can pause.
- **Hybrid record by table:** in-season facts in Postgres, everything else in parquet. Rejected because it creates two sources of truth.
- **The app and bot read Supabase live now, as HoD does.** Rejected for now. The app dies whenever the project pauses or has an outage, which effectively means paying for Pro to get uptime we already have free. This is the target once the staged trigger fires.
- **Pro now, but still serving the snapshot.** Rejected. Its backups mostly duplicate the git snapshot, so this is $25/mo for little gain.
- **Parquet fallback write when Supabase is unreachable.** Rejected. It means two write paths plus a reconcile step, and the reconcile is exactly where bad data gets in.
- **A GitHub Actions `select 1` keep-alive.** Rejected. It puts DB credentials in Actions secrets and still gives no backup. The run log does the same job.
- **Power BI through the Npgsql connector.** Rejected. It needs an on-prem gateway for service refresh, a CA install and an M rewrite, all for freshness the snapshot already matches.

## Consequences

- **Map #69 loses its consumer-cutover work.**
  - No Power BI M rewrite.
  - No bot REST client.
  - No trade-bud secrets in `pages.yml`.
  - ADR-0012's "no server, no database, no secrets in production" stays true.
- **New work graduates into #69:**
  - the seam's Postgres backend and its export step
  - an `etl_run_log` table
  - a **restore drill**: rebuild an empty project from migrations plus the snapshot. It must pass before cutover.
- **Snapshot commits to `main` become more frequent** (daily runs plus change polls). They are change-detected and allowlist-verified exactly as now, so this is churn, not risk.
- **Freshness is bounded by the Change Poll interval** plus about 2 minutes for the Pages rebuild and the bot's next fetch. It is not instant.
- **The RLS posture still applies to our ETL-only store.**
  - HoD's anon-writable RLS stays rejected.
  - RLS is on for every table.
  - Access is split into a writer role for the ETL and a read-only role, held for the future live-read stage.
- **The CLAUDE.md storage rule changes.** Postgres is the record, `data/*.parquet` is the published snapshot, and the Fabric-migration note is dropped.
