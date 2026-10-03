# Regression-testing standard: pytest, pre-commit, CI and post-run checks

- Status: accepted — **BUILT 2026-07-11**; **amended 2026-10-03 (#88)**: post-run checks, publish gate and CI, designed through HITL grilling, not yet built ([amendment](#amendment-2026-10-03-publish-gate-post-run-checks-ci-88))
- Date: 2026-07-11
- Scope: `pyproject.toml`, `tests/`, `discord_bot/tests/test_offline_smoke.py`,
  `.pre-commit-config.yaml`, `requirements.txt`, `discord_bot/requirements.txt`

## Context

Regression testing has been flagged repeatedly as "painfully lacking" for
this repo — no `pytest`, no `pyproject.toml`, no `.pre-commit-config.yaml`,
no CI, at all, despite two real regression-testing artifacts already
existing in hand-rolled form: `discord_bot/tests/offline_smoke.py` (a script
run directly via `.botvenv`, not discovered by any standard runner) and
`scripts/check_sources.py`'s own `validate` mode (already deferred to
"wire into pre-commit" in this repo's own `PLAN.md` per ADR-0007).

Design was grilled and agreed in a prior session (general regression-testing
standard synthesized into `project-memory-template`'s
`docs/regression-testing-standard.md` in parallel), including a new
constraint: no JS/TS dashboard exists yet, but the standard shouldn't have to
be torn up when one shows up.

## Decision

1. **`pyproject.toml`** adds `[tool.pytest.ini_options]` scoping `.venv`'s
   pytest run to `tests/` only — `discord_bot/tests/` runs under its own
   `.botvenv`, per the repo's existing deliberate two-venv split. Two
   separate invocation commands, not a merged runner:
   ```
   .venv\Scripts\python.exe -m pytest tests\
   discord_bot\.botvenv\Scripts\python.exe -m pytest discord_bot\tests\
   ```
2. **`tests/test_etl_helpers.py`** — first real unit tests, covering the
   pure, I/O-free functions already isolated in `etl_helpers.py` per its own
   "modular extraction rule": `clean_player_name`, `clean_name_for_match`,
   `generate_player_key`, `parse_height_to_inches`, `fold_ranks_long`. The
   I/O-heavy functions (`resolve_dynasty_crosswalk`, `add_players_from_source`,
   `ingest_ranking_source`, `_make_session`) are integration-test candidates,
   deliberately out of scope for this pass.
3. **`discord_bot/tests/offline_smoke.py` → `test_offline_smoke.py`** —
   renamed to pytest's default discovery pattern, `main()`/`_check`/
   `_expect_error` wrapped into `test_rankings`/`test_adp`/`test_player`/
   `test_cap`/`test_roster` functions. Same assertions, same monkeypatched
   local-parquet fetch, same embed-limit checks — logic unchanged.
4. **`.pre-commit-config.yaml`** wires exactly one local hook: `check_sources.py
   validate` (the already-built ADR-0007 script), scoped to changes touching
   `docs/sources.yml`, `docs/SOURCES.md`, or `notebooks/`. It deliberately does
   **not** run the full pytest suite — pre-commit stays local/fast/advisory;
   see Alternatives rejected.
5. **`pytest>=8.0`** added to both `requirements.txt` and
   `discord_bot/requirements.txt` (mirrors the existing curated,
   loosely-pinned convention — not a `pip freeze`).

## Alternatives rejected

- **Running the full pytest suite in pre-commit** — too slow for a
  commit-time gate, and the wrong enforcement point for "tests must pass
  before merge" — that's CI's job (see Consequences/deferred below), not a
  local hook that only catches commits made through the tool that installed
  it.
- **A single merged test runner across both venvs** — would require
  collapsing the deliberate `.venv`/`.botvenv` split (see CLAUDE.md), for no
  real gain; two documented commands is simpler and matches
  `project-memory-template`'s own YAGNI stance (a wrapper script is future
  work if/when a third venv or suite appears).
- **`tox`/`nox` as the orchestrator instead of `pre-commit`** — Python-only;
  `pre-commit` was chosen specifically because a future non-Python surface
  (e.g. a `web/`-style dashboard folder with its own `package.json` +
  vitest/playwright) adds one more entry to `.pre-commit-config.yaml`
  without requiring the Python layout or venv split to change. See
  `project-memory-template/docs/regression-testing-standard.md`.

## Consequences

- `pytest tests/` and `pytest discord_bot/tests/` are now real, discoverable,
  standard-runner checks — no more manually remembering to invoke a
  standalone script.
- A deliberately broken pure function (e.g. `clean_player_name`) now fails a
  test instead of silently rotting until it surfaces downstream.
- `pre-commit run --all-files` catches `sources.yml`/notebook drift at
  commit time — the ADR-0007 deferred item is done.
- **Deferred, not built this pass** (logged here and in `PLAN.md`):
  - **CI (GitHub Actions)** — the architecturally correct place to gate
    merges on the full suite passing; a local hook only catches this
    machine's commits. Zero `.github/workflows/` exist today; this is
    from-scratch future work, not a small addendum. *Decided in the
    2026-10-03 amendment below (decision 14).*
  - **Power BI visual regression** — heavier lift (screenshot-diffing
    infrastructure); a seed idea in the general standard doc, not built.
  - **Python lint/format in pre-commit** — a separate decision (rule
    selection, auto-fix policy, how much existing code would flag);
    deserves its own grill session, not a rider on this one.

## Amendment 2026-10-03: publish gate, post-run checks, CI (#88)

Designed through HITL grilling on 2026-10-03
([#88](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/88));
not yet built. The July decisions above stand.

- Amends:
  - [ADR-0014](0014-supabase-system-of-record-static-serving.md) decision 3: the publish unit is a Chain, not the whole run (decision 3).
  - [ADR-0018](0018-supabase-schema-and-rls.md) decision 11: `ops.review_check` gains `last_seen_at`, a `pending` state and one open row per finding (decisions 8 and 9).
- Settles the open item in [ADR-0019](0019-minor-is-a-pre-1st-contract-stage.md) decision 4: how a lagging graduation is told apart from a real mismatch (decision 9).
- Scope:
  - `scripts/run_pipeline.py`, a new `notebooks/etl_checks.py`, `docs/data_model.yml`
  - `.github/workflows/tests.yml`, `scripts/make_fixtures.py`, `tests/fixtures/fantrax/`
  - `ops.review_check` (ADR-0018)

### Context

- `run_pipeline.py` commits refreshed parquet even when a step has failed. Only `--dry-run` and `--no-commit` skip the commit. ADR-0014 decision 3 says to publish only a good run, and left the checks to #88.
- Since ADR-0014/0015 the snapshot publishes on every run (the daily run, each debounced Change Poll trigger, the weekly run), not once a week.
- One run mixes independent pipelines: the Fantrax core (`04a → 04z → 04v → 02d → 02e`, later `04t`/`04s`), the rookie scrapes `03a`–`03d` (external sites, every phase), the dynasty profile and nflverse (#86).
- ADR-0018 sends its dirty-edge FK checks here. ADR-0019 sends its Minor drift check here. ADR-0016 makes ledger replay a reconciliation check.
- No tests run in CI. The only workflows are `pii-scan` and `pages`.
- PR checks catch only email-shaped PII, so anything committed as a test fixture must be scrubbed by construction (ADR-0018 decision 10).

### Decision

1. **Every publish is gated.** One check suite runs before every publish, whatever triggered the run. An Update-Set's closing → closed step also runs Close checks. If they fail, it stays `closing` and an alert is sent.
2. **Two tiers.**
   - A **Gate check** fails when our pipeline produced something broken or incomplete. The publish is blocked, the last good snapshot keeps serving, and Discord alerts.
   - A **Review check** fails when the data faithfully mirrors Fantrax but disagrees with an expectation. It files to `ops.review_check`, and the publish goes ahead.
3. **The publish unit is a Chain.**
   - Each Chain (Fantrax core, rookie, dynasty profile, nflverse) publishes its own tables once its steps and Gate checks pass. Each Chain writes in one DB transaction.
   - A failed Chain keeps its last good tables, and the other Chains still publish.
   - Before cutover, a failed Chain's parquet is restored from git `HEAD`, so its files never reach the commit.
4. **Gate checks:**
   - a step exits non-zero;
   - grain uniqueness on each table's registry grain (the primary key enforces it after cutover);
   - row-count collapse (decision 6);
   - coverage: Roster State has 28 teams, 14 per Conference; Period Scoring has every Scoring Period from 1 to the last closed one; required keys (`scorer_id`, `team_key`, `period`) are non-null;
   - schema: columns and dtypes match `docs/data_model.yml`. This catches a renamed Fantrax field that leaves a parser silently writing an all-null column.
5. **No FPts-YTD-non-decreasing check.** A drop during a closing period is a normal stat correction. A change to a closed period is Drift, which is already checked.
6. **Collapse** means a table shrinks by more than 20%, or to zero rows, against the last published snapshot.
   - A table can set its own limit in `docs/data_model.yml`.
   - A manual (`workflow_dispatch`) run can pass `--accept-shrink <table>` for a known rollover.
   - Growth never blocks.
7. **Close checks:**
   - the period's Roster State covers all 28 teams;
   - every Starter in the period roster has an `ACTIVE` live-scoring entry;
   - per team, the Starter FPts sum equals Fantrax's `totalFpts` for the period, to 0.01.

   Matchup completeness waits for #81's fact model. *Defined in [ADR-0016's 2026-10-03 amendment](0016-roster-state-from-snapshot-ledger-is-provenance.md#amendment-2026-10-03-in-season-fact-model-81) (decision 10): all 14 matchups present, pairs mirror, and schedule FPts = `totalFpts` = the Starter sum.* Bench completeness is not checked: 15 non-starters were missing from `BENCH` in final period 1, unexplained ([#79](../research/inseason-schema-extraction.md)).
8. **Filing.**
   - `ops.review_check` holds one open row per `(check_name, table_name, row_key)`.
   - A repeat finding only updates `last_seen_at` and the run id.
   - When a run no longer sees it, the row auto-resolves (`resolution = 'cleared'`). A recurrence opens a new row.
   - This needs `last_seen_at` and a partial unique index on open rows.
9. **Grace.** Each Review check has a `grace_periods` setting.
   - A finding inside its grace is filed as `pending` and is not surfaced. If it clears first, it resolves silently.
   - The Minor drift check uses one period, in both directions: an ineligible player still on `Minor`, and an eligible player on `1st` or `FA`. A player who passes 19 games in period N is due on `1st` only from N+1, and a claimed player can sit on `FA` until the commissioner flips them.
   - Replay reconciliation (`replay_reconcile`, ADR-0016) uses zero.
10. **Dirty edges file one row per distinct orphan key**, limited to what someone can act on.
    - `scorer_id`: only players in Roster State.
    - `position_raw`: one row per unmapped value, fixed by a `dim_position` row.
    - `player_key`: one row per distinct key.
    - Orphans outside that scope appear only as a count in the run summary.
11. **Drift sweep.** The daily run re-fetches every closed period (public `getTeamRosters(period)` and authed `getLiveScoringStats(period)`) and compares it with the closed Update-Set. Change Poll runs never sweep.
12. **Discord posts on events plus a daily digest.**
    - Posted immediately: a Gate failure, a Close-check failure, Drift, an Update-Set closing, and a poll-triggered publish.
    - New Review findings past their grace go into one counts-by-check line on the daily run's post, only when there are any.
13. **Parser tests on generated fixtures.**
    - A committed `scripts/make_fixtures.py` trims each `data/raw` payload: 2 teams, about 10 players, 1 period. It keeps only allowlisted keys, so owner and user fields are dropped by construction. The output goes to `tests/fixtures/fantrax/`, is committed, and is regenerated when Fantrax changes shape.
    - Covered parsers: `04a` `getPlayerStats`; `04s` standings, live scoring and roster info; `04t` transaction history; `04u` public rosters and picks; `02d` draft results; the `getLeagueInfo` periods.
14. **CI: `.github/workflows/tests.yml`, a required check.**
    - It runs on every PR and every push to `main`.
    - One job builds a clean venv from `requirements.txt` and runs `pytest tests/`. A second job does the same from `discord_bot/requirements.txt` for `discord_bot/tests/`.
    - ADR-0018's throwaway-Postgres migration check joins with #108.
15. **Run flags.**
    - `--dry-run` still prints the plan.
    - New `--check-only` runs the whole suite against the current store, with no steps, no publish and no Discord.
    - `--no-commit` runs steps and checks and stops before publishing.
16. **Where checks live.**
    - Table-level Gate checks (grain, schema, shrink limit, required keys) take their parameters from `docs/data_model.yml`.
    - Domain checks (coverage, Close checks, Minor drift, dirty edges, replay, Drift) are functions in `notebooks/etl_checks.py`, which `run_pipeline.py` runs after each Chain.
    - Before cutover, findings go to `data/review/review_check.csv` with the `ops.review_check` columns. The #77 seam later swaps that for the table.
17. **Two build issues under #70.**
    - (a) [#115](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/115): the foundation, buildable on today's parquet pipeline: decisions 3–6, 8 and 13–16, which also fix the commit-on-failure bug.
    - (b) [#116](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/116): the in-season checks, which need Update-Sets, per-period Roster State and `04t` in the pipeline: decisions 7 and 9–12, plus replay.

### Alternatives considered

- **Gating only the publish that closes an Update-Set.** Rejected: daily and poll publishes would go out unchecked. **No separate Close checks** was rejected too: a period could freeze while still incomplete.
- **A third Warn tier** (Discord only, no queue row). Rejected: two tiers are enough. **Blocking on every finding** was rejected as well: one oddity on Fantrax's side would freeze the snapshot.
- **The whole run as the publish unit** (ADR-0014 as written). Rejected: one broken external scraper would freeze league rosters and cap for days. **Per table** was rejected too: a fact could publish while a sibling table in the same Chain had failed.
- **An FPts-YTD check, as a Review check or a Gate check.** Rejected: Drift covers it, and a Gate would false-alarm on every stat correction.
- **Blocking only on zero rows, or one flat 50% limit.** Rejected: the first misses a parser that loses half the rows, and the second fits no table well.
- **Appending findings every run, or resolving them only by hand.** Rejected: the first means unbounded duplicates; with the second, rows stay open after Fantrax fixes the problem.
- **Filing drift immediately.** Rejected: every legitimate graduation lag would raise a finding. **Checking only when a period closes** was rejected too: it needs eligibility history that `fact_minor_eligibility` does not keep.
- **One finding per orphaned fact row.** Rejected: thousands of rows nobody acts on, such as 4,285 `scorer_id` orphans in `fact_minor_eligibility`. **Counts only** was rejected too: it gives no per-key lifecycle.
- **A drift sweep that is weekly only, or daily-recent plus weekly-full.** Rejected: Drift could sit unseen for days, and the full sweep costs at most about 34 calls.
- **Posting every finding immediately, or a summary on every run.** Rejected: both are noisy, and the second contradicts ADR-0015's rule that silence means success.
- **Hand-trimmed or synthetic fixtures.** Rejected: hand-trimmed ones are scrubbed by eye and drift from Fantrax, and synthetic ones cannot catch real shape drift.
- **Advisory or local-only tests.** Rejected: a red run would not block a merge, and the gap between `.venv` and a clean venv would stay invisible.
- **A full rehearsal mode into a scratch store.** Rejected for now: it needs the #77 seam to support a scratch target.
- **Waiting for cutover before building checks, or asserting inside each writer.** Rejected: the commit-on-failure bug is live today, and checks that span tables would have no home.
- **A new ADR, or recording this in issues only.** Not chosen: the owner amended this ADR in place.

### Consequences

- **The commit-on-failure bug is fixed by build (a) #115,** before any Actions cutover (#93).
- **ADR-0014's "a failed run publishes nothing" now reads per Chain.** A failed Chain publishes nothing; the other Chains still publish.
- **`ops.review_check` is no longer append-only.** The generator emits a partial unique index on open rows, and the writer upserts.
- **The registry grows check parameters,** a shrink limit and required keys, beside ADR-0018's `pk`/`fk`/`sql_type`.
- **A Close-check failure delays freezing.** Drift is measured only against Update-Sets that actually closed.
- **Fixture regeneration is a deliberate PR.** A changed fixture shows the Fantrax shape drift in review.
- **Wiring.** #93 is blocked by #115. #116 is blocked by #115, #81 and #93.
