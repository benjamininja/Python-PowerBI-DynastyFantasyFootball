# Daily runs, weekly finals

- Status: accepted. Decided in the grill-with-docs pass of 2026-11-05 ([#376](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/376), questions 11 to 20); not yet built.
- Date: 2026-11-05
- Amends: [ADR-0015](0015-etl-on-github-actions-owner-pii-confined.md) (the schedule) and [ADR-0016](0016-roster-state-from-snapshot-ledger-is-provenance.md) (the keys of the in-season facts). Neither decision is reversed.
- Scope:
  - the scheduled run and its per-step cadence
  - the week key and `snapshot_date` of the weekly-history tables
  - `fact_fantrax_adp` and `fact_minor_eligibility`
  - `CONTEXT.md` (Time)

## Context

- The owner wants fresh data every day, but history of one row set per week.
- Fantrax turns a Scoring Period over on Thursday. The weekly-history tables used a Monday turnover.
- Open Update-Sets are refreshed every run, so some steps must run daily in season.

## Decision

1. **A Daily Run** is the one scheduled run a day.
2. **Close Day** is the day after any Scoring Period ends, playoffs included, judged on the Eastern clock. In season it comes from `dim_scoring_period`. Off season it is a fixed weekday from config.
3. **Each step declares `cadence: daily | close_day`.** A `close_day` step catches up: it runs on the first Daily Run on or after the Close Day where it has not yet succeeded for that week, per `etl_run_log`.
4. **The week key** is `(season, period)` in season and the ISO week off season.
5. **Each run overwrites the current week's rows in place,** in both Postgres and the parquet. There is no cleanup job.
6. **A week's final is the last good run.** A failed run never overwrites it.
7. **Tables keyed on `snapshot_date` take the week's anchor date:** the period end date in season, the ISO week's Sunday off season. No column changes.
8. **The week label becomes the Scoring Period** in `fact_fantrax_adp` and `fact_minor_eligibility`, from the next week on. Old rows are not relabelled; a dated registry note marks the switch.

## Alternatives considered

- **Keep every daily row and prune later.** Rejected: it needs a cleanup job, and until it runs the published tables hold history nobody asked for.
- **Postgres keeps dailies, the parquet keeps weekly finals.** Rejected: the two stores would disagree on what history is.
- **Hard-coded Thursday Close Day in season.** Rejected: periods and playoffs do not all end on one weekday.

## Consequences

- Dailies are gone for good once a week is overwritten. Raw captures stay 14 days in the raw store, for debugging only.
- A step that fails on its Close Day runs on a later Daily Run, and its week is not final until it does.
- The weekly-history keys change in their own ticket, which merges before #373.
- Rookie-rankings history is not specified here; it is recorded on #375.
