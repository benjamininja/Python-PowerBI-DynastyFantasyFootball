# Regression-testing standard: pytest + pre-commit + check_sources.py

- Status: accepted — **BUILT 2026-07-11**
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
    from-scratch future work, not a small addendum.
  - **Power BI visual regression** — heavier lift (screenshot-diffing
    infrastructure); a seed idea in the general standard doc, not built.
  - **Python lint/format in pre-commit** — a separate decision (rule
    selection, auto-fix policy, how much existing code would flag);
    deserves its own grill session, not a rider on this one.
