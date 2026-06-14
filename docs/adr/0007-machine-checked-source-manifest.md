# Machine-checked source manifest: `sources.yml` + `check_sources.py`

- Status: accepted — **BUILT 2026-06-14**
- Date: 2026-06-14
- Scope: `docs/sources.yml`, `docs/SOURCES.md`, `scripts/check_sources.py`,
  `scripts/requirements.txt`
- Extends the hand-maintained [`docs/SOURCES.md`](../SOURCES.md) manifest (the
  external-input boundary doc, authored 2026-06-13).

## Context

`SOURCES.md` documents every place data crosses into the repo (8 live + 3
planned sources), with a `Feeds` column naming the ingesting notebook → table.
Its own anti-drift note (v1) was *"hand-maintained — update the row in the same
commit"* and explicitly deferred a machine-readable `sources.yml` + lint.

Hand-maintenance has a known failure: a notebook gets renamed, deleted, or
stops referencing a source, and the manifest silently rots. The `Feeds` column
is precisely the join that *could* be checked by machine, but only if the
manifest is data, not prose.

Settled via a `/grill-with-docs` session on 2026-06-14.

## Decision

1. **`sources.yml` is the SSOT; the `SOURCES.md` tables are generated from it**
   (grill Option A). The authored prose (boundary scope, secrets rule, the
   anti-drift instructions) stays hand-written Markdown; only the two tables are
   rendered, between `<!-- BEGIN/END GENERATED sources-table:{live,planned} -->`
   HTML-comment markers. This kills drift *between the two artifacts* — there is
   one place to edit. Rejected: a parallel hand-maintained yaml (reintroduces
   the very drift it's meant to remove) and deleting the readable table (loses
   human legibility for no gain).

2. **`match` (lint fingerprint) is a field separate from `locator` (display
   URL).** The literal display URL is often *not* in the code: Fantrax stores
   `league_id` + `endpoint` separately (rendered as a `?leagueId=` URL); the
   Google Sheet URL lives in `etl_helpers.CFG.team_sheet_csv_url`, not the feed
   notebook. So the lint matches a per-source token list (case-insensitive
   substring, **OR** across tokens), asserted present in **each** feed notebook,
   while `locator` stays human-facing. Tokens are chosen to be
   **notebook-resident** (e.g. the Sheet uses the config symbol
   `team_sheet_csv_url`, not the URL that lives in the helper).

3. **Validation scope** (`scripts/check_sources.py`, default `validate`):
   - **schema check** (all sources) — required fields, unique `id`, valid
     `status`, `feeds` is a list; live sources have non-empty `match` + `feeds`.
   - **notebook-exists + token-match** — **live sources only**. `planned`
     sources may have unresolved `feeds`/`match` (e.g. capture pending), so they
     get the schema check but are exempt from enforcement.
   - **reverse-drift (WARN)** — extract external hosts from notebook cell source,
     subtract registered source hosts + an in-yaml `ignore_hosts` allowlist;
     report leftovers. A new unregistered host means "register it or add to
     `ignore_hosts`."
   - `.ipynb` is parsed for **`cell.source` only** (never outputs — a token
     cached in a stale execution result must not produce a false match).

4. **Severity split: forward checks hard-fail (exit 1); reverse-drift WARNs.**
   Schema / notebook-exists / token-match are deterministic, so they earn the
   hard fail. Reverse-drift is heuristic (a `https://` in a comment can trip it),
   so it reports without blocking — the `ignore_hosts` allowlist is the noise
   valve, populated once and reviewed in the same file.

5. **Packaging: one standalone script, three modes** — `validate` (default),
   `--render` (rewrite the SOURCES.md table regions), `--check` (render in-memory
   and diff; fail if stale, the CI-style guard). Standalone over pytest: matches
   the repo's `scripts/` convention; no test framework exists to host it.
   PyYAML is the only new dep, pinned in `scripts/requirements.txt` (tooling
   only — not the notebook stack), installed into `.venv`.

## Alternatives rejected

- **`sources.json` (stdlib, zero deps)** — no comments, noisier to hand-edit;
  the file is a hand-edited SSOT where YAML's readability pays for the one tiny
  dep. Also contradicts the name fixed in PLAN/ADR history.
- **Match on the full display URL** — fails on the URL-form mismatch above even
  when the notebook clearly references the source; the token/`locator` split is
  the robust fix.
- **Notebook + helper-fallback search scope** — looser; would silently absorb a
  URL that moved into `etl_helpers.py`. Strict notebook-only scope surfaces that
  as a one-line `match` edit, keeping the manifest honest.
- **Reverse-drift as a hard fail** — too noisy to gate commits on; WARN + an
  allowlist gives the signal without the false-positive blocking.
- **Table-exists check** (assert each `feeds[].table` parquet is built) — parquet
  is a gitignored build artifact, frequently absent on a clean checkout; would
  fail spuriously. Out of scope.

## Consequences

- Editing a source is now a single yaml edit + `--render`; the readable table
  can never disagree with the SSOT (guarded by `--check`).
- A renamed/deleted/decoupled feed notebook trips `validate` (exit 1) instead of
  rotting silently.
- New external hosts surface as a WARN, prompting registration.
- `--check` is CI-ready if CI is ever added (none exists today). For now it's a
  manual / pre-commit-style guard.
- Deferred (noted, not built): wiring `--check` + `validate` into an actual CI or
  pre-commit hook; reverse-drift currently scans hosts only (not package-import
  or local-file sources), which is why nflverse/manual-Excel rely on token-match
  rather than host detection.
