# Owner manifest: Fantrax is upstream SSOT, the Google Sheet is a field-scoped synced mirror

- Status: accepted — **read-side BUILT 2026-06-14** (`01c` Fantrax-TeamId ingest;
  `dim_division` seed); the Sheet **write**-sync stays deferred (auth + PII gate)
- Date: 2026-06-13
- Scope: new owner-manifest sync notebook/script, `01c_dim_fantasy_teams_seed`,
  `dim_fantasy_teams`, new `dim_division`

## Context

`dim_fantasy_teams` is sourced from a league Google Sheet (id `1Fiz…`, gid
178660131) — today a **read** via the CSV-export URL ("anyone with link can
view"). The owner wants the Sheet to stay current with Fantrax automatically:
Fantrax becomes the upstream source of truth for owner/team attributes, the Sheet
a mirror that league members read. Settled via `/grill-with-docs` 2026-06-13.

The Sheet's live columns: `Division, Team Name, Team Abbreviation, Manager Email,
Other Manager Email, Team ID (A01–A14/B01–B14), Fantrax-TeamId`. Managers are not
unique (one email owns multiple teams), so the join key must be `Fantrax-TeamId`.

## Decision

A sync pulls team detail from Fantrax (commissioner team-admin) and **writes it
back into the Sheet**, with field-level SSOT:

- **Locked — never written by the sync** (owner-only structural columns):
  `Division`, `Team ID` (team_key), `Fantrax-TeamId`. A guard asserts the write
  range excludes these before any API call.
- **Synced from Fantrax** (owner-mutable attributes): `Team Name`,
  `Team Abbreviation`, `Manager Email`, `Other Manager Email`.
- **Join on `Fantrax-TeamId`, inner.** Update only matched rows' mutable cells.
  **Never add or delete rows** — row structure is owner-owned.
- **Diff-only writes:** compute Fantrax-vs-Sheet deltas, write only changed
  cells, idempotent (a no-op run writes nothing). Print the diff before writing.
- **Unmatched either side = soft-fail + review** (mirrors the 04z collision
  pattern): a Fantrax `teamId` absent from column G, or a Sheet row Fantrax
  doesn't return → log + `data/review/` CSV, continue. These signal a
  locked-field typo or roster change only the owner can fix.
- **The `Fantrax-TeamId` column is the bridge.** `01c` maps it
  (`Fantrax-TeamId → fantrax_team_id`) so `dim_fantasy_teams` carries the
  `teamId → team_key` resolution that the ledger build (ADR-0004) needs. One
  change, two payoffs.

**`dim_division`** (transformer table, `dim_position`/`dim_school` pattern) keyed
`(season_id, conference)` → `division_name`. `conference` = stable `A`/`B`;
`division_name` = the season's label (`Riddell`/`Wilson` for 2026-2027). The
Sheet's locked `Division` is the current-season point-in-time value; `dim_division`
holds the season-scoped history. `dim_fantasy_teams.conference` resolves to a label
by `(season_id, conference)` join — no downstream conditional.

## Alternatives rejected

- **Ingest Fantrax directly into the pipeline, never write the Sheet** — strictly
  cleaner on auth/PII (no Sheets-API write, no emails written to shared content),
  but defeats the actual goal: league members read the *Sheet*, so it must stay
  live. Kept on the table if the human-facing requirement ever drops.
- **Full-range overwrite of all 28 rows each run** — rewrites locked/human cells,
  risks clobbering mid-edit, every run a blind 28-row write. Diff-only is safer
  and auditable.
- **Seasonal division naming as columns on `dim_season`** (`division_a_name`,
  `division_b_name`) — pushes an `IF conference="A" …` conditional into every
  consumer, the exact downstream-if/else `dim_position`/`dim_school` were built to
  avoid. `dim_division` keeps it a join.

## Consequences

- The Sheet is **both written (sync) and read (01c)** — intentional: it is the
  *merge point* of Fantrax-owned attributes + owner-owned structural columns, not
  a pure mirror. This ADR exists mainly to explain that apparent circularity.
- **External-write + PII gate (build time):** writing the shared Sheet needs
  explicit owner go-ahead at run time and Sheets-API auth (OAuth/service account)
  the owner sets up — never credential entry by the assistant. Manager emails are
  PII written to shared content; writes stay scoped to the 4 mutable columns.
- Open at build time: confirm Fantrax commissioner-admin exposes co-manager email
  + abbreviation; Sheets-API write mechanism + auth; whether `Team Abbreviation`
  is truly Fantrax-owned or league-native (move to locked if the latter).

## Build amendment (2026-06-14) — read-side built

- **`01c` ingests `Fantrax-TeamId`** → `dim_fantasy_teams.fantrax_team_id` (28/28),
  lighting up the `teamId → team_key` join the ledger needs; the interim
  name-match heuristic was retired (see ADR-0004 build amendment).
- **`dim_division` built** by `01g_dim_division_seed.ipynb` → `data/dim_division.parquet`.
  Grain `(season_id, conference)`; names **derived** from `dim_fantasy_teams.division`
  (the Sheet's `Division`, ingested by 01c) rather than hardcoded, then stamped with
  the current `season_id`. v1 seeds only the known season (2026-2027: `A`→Riddell,
  `B`→Wilson, 2 rows); append future seasons as they gain themed names.
- **Still deferred**: the Sheet **write**-sync (Sheets-API auth + PII go-ahead).
