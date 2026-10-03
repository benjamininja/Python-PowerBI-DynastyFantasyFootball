# Storage-seam inventory — every parquet read/write call site

Research ticket #74 · child of map #69 (Supabase storage foundation) · 2026-09-26

**Question:** what `etl.read_table` / `etl.write_table` interface covers every
current parquet reader and writer, so the backend can later move from parquet
to Supabase Postgres without changing call sites?

**Answer (short):** three write modes cover all 27 tables: `replace`,
`replace_partition` (derived keys *or* an explicit value set), and `upsert`
on the natural key. Reads need `columns=` projection plus a `table_exists()`
check. The dtype contract belongs in `docs/data_model.yml`, which already
declares each table's columns, dtypes and grain. Before Postgres primary keys
can be declared, two tables need a grain fix
(`fact_dynasty_ranking_metrics` Composite rows, `fact_fantasy_teams`).

Method: I parsed the JSON of every `.ipynb` code cell (outputs ignored) and
grepped the `.py` files under `notebooks/`, `scripts/`, `discord_bot/` and
`mouserat_trade-bud/`. I read the actual schemas with pyarrow 24.0.0 and
pandas 3.0.3 (repo `.venv`). `data/raw/` was not read.

---

## 1. Counts

| Area | `read_parquet` | direct `to_parquet` | helper-routed writes | Notes |
|---|---:|---:|---:|---|
| `notebooks/*.ipynb` + `notebooks/*.py` (ETL) | 77 | 27 | 12 (`load_replace_partition` ×9, `upsert_dynasty_crosswalk` ×3) | plus 41 `add_players_from_source`/`ingest_ranking_source` refs in 03a–03x |
| `notebooks/etl_helpers.py` | 13 | 5 | — | the helpers themselves |
| `scripts/` | 4 | 2 | — | `apply_fantrax_crosswalk_review`, `check_data_model`, `run_pipeline` |
| **ETL total (in seam scope)** | **94** | **34** | **12** | 27 distinct tables |
| `discord_bot/` (GitHub API) | 1 `fetch_parquet` choke point, 7 tables | 0 | — | out of seam |
| `mouserat_trade-bud/backend` (local files) | 1 `da.read_parquet` choke point, ~25 uses, 13 tables | 0 | — | out of seam |
| `pbi/` M `File.Contents` | 17 parquet paths in 16 TMDL tables | — | — | out of seam, absolute `C:\Users\benha\...` paths |

Path styles found in scope:

- **`DATA / "x.parquet"`** is most sites: all of 01–03, 02d/02e, 04e, 04f, 04u, 05a, and `etl_helpers`.
- **`f"{CFG.data_dir}/{name}.parquet"` or `Path(CFG.data_dir) / ...`** is used by 01a (writes), 03a–03d QA cells, 04a, 04b, 04c, 04v, 04x, 04y, and `resolve_dynasty_crosswalk(data_dir=)`.
- **`CFG.path(name)`** is used by 04d, 04z and 05a.
- **Hardcoded** paths are the non-compliant ones: `root / "data" / ...` in `scripts/apply_fantrax_crosswalk_review.py`, `REPO / "data" / ...` in `scripts/run_pipeline.py`, and `DATA_DIR` in `check_data_model.py`.
- **Name handles** also appear: `CFG.fact_name`, `crosswalk_name`, `nfl_players_name`, `rookie_prospect_name`, `alias_name`, `KCFG.*` and `MCFG.*`. `write_table` takes the **table name**, so all of these collapse to strings.

Existence checks (`X.exists()`) come before reads or writes at about 14 sites:
`ALIAS` ×3, `ASSET_PATH`, `PLACEMENT_PATH` ×3, `load_replace_partition`,
`upsert_dynasty_crosswalk`, 04a `load_fact`, 04v ×2, 01f, 04c, and the 04a
dim fallbacks. The seam therefore needs `table_exists()`.

Read-time column projection (`columns=`) appears at 04a
(`dim_nfl_players[gsis_id,birth_date]`), 04c (`metric_key`) and 04f
(`source_name, metric_key`). Every other projection or filter happens in
pandas after the read. **No call site filters rows at read time.**

---

## 2. Write inventory by table (27 tables)

| Table | Writer(s) | Write semantics today | Seam mode |
|---|---|---|---|
| dim_position | 01a c3 | full replace (seed) | `replace` |
| dim_school | 01a c5 | full replace (seed) | `replace` |
| dim_rookie_prospect | 01a c11; `etl.add_players_from_source`; 03z c5 | 01a full; helper = read, concat new, dedup `player_key`, write; 03z = read-modify-write | 01a `replace`; others `upsert keys=player_key` |
| dim_contract | 01b | full replace | `replace` |
| dim_fantasy_teams | 01c | full replace | `replace` |
| dim_nfl_teams | 01d | full replace | `replace` |
| dim_nfl_players | 01e | full replace (nflverse pull) | `replace` |
| dim_season | 01f | read existing years, union with calendar range, full write | `replace` (caller unions; unchanged) |
| dim_division | 01g | full replace | `replace` |
| fact_nfl_combine_pro_day_metrics | 02a | full replace | `replace` |
| fact_rookie_rankings | 02c (seed); `etl.ingest_ranking_source` | seed full; helper = read, concat, **first-non-null `rank_date` coalesce**, dedup keep-last on `(player_key, source_name, phase, draft_year)`, full write | seed `replace`; helper: caller computes coalesce, then `upsert` |
| dim_roster_asset | 02d ×3 (`mint_assets`) | read-modify-write; mints surrogate `asset_id = max+1` | `upsert keys=asset_id` (minting stays in caller) |
| fact_draft_pick | 02d | `load_replace_partition(part_cols=(draft_season,))` | `replace_partition keys=(draft_season,)` |
| fact_roster_transactions | 02d ×2 | (a) `load_replace_partition(season_id, event_type)`; (b) hand-rolled **delete `event_type IN TXN_EVENT_TYPES`** + append (explicit value set, deliberately not derived from df) | (a) `replace_partition keys=(...)`; (b) `replace_partition partition={"event_type": TXN_EVENT_TYPES}` |
| fact_trade_log | 02d | full rebuild from 04t capture | `replace` |
| fact_fantasy_teams | 02e | full derive | `replace` |
| dim_player_alias | 03y (rebuild); `add_players_from_source`; 03z `record_alias` | 03y full; others read, concat, dedup keep-last `(name_clean, position_raw)` | 03y `replace`; others `upsert` |
| fact_fantrax_adp | 04a `load_fact`; 04z c6; `apply_fantrax_crosswalk_review` | 04a: hand-rolled replace-by-`(season, week)` + safety dedup `(scorer_id, season, week)` + **`score→fpts` schema-migration shim**; 04z/apply: read, overwrite FK columns, full write | 04a `replace_partition keys=(season, week)`; FK backfill `replace` for now (later: column update) |
| dim_dynasty_crosswalk | `etl.upsert_dynasty_crosswalk` (04b, 04x, 04f) | replace-by-`source` | `replace_partition keys=(source,)` |
| fact_dynasty_ranking_metrics | 04b, 04x, 04f, 04y via `load_replace_partition` | replace-by-`(snapshot_date, source_name)` | `replace_partition` (default keys) |
| dim_dynasty_metric | 04c | full replace (seed) | `replace` |
| dim_pick_value_curve | 04d via `load_replace_partition` (default cols) | replace-by-`(snapshot_date, source_name)` | `replace_partition` |
| dim_position_ceiling | 04e via `load_replace_partition(snapshot_date,)` | replace-by-snapshot | `replace_partition keys=(snapshot_date,)` |
| fact_draft_pick_future | 04u via `load_replace_partition(draft_season,)` | replace-by-draft_season | `replace_partition` |
| dim_fantrax_crosswalk | 04z c5; `apply_fantrax_crosswalk_review` | 04z full; apply = read, patch rows, full write | `replace` (or `upsert keys=scorer_id` for the patch) |
| fact_roster_placement | 04v `load_placement` | hand-rolled replace-by-`(season, week)` + dedup `(team_id, scorer_id, season, week)` | `replace_partition keys=(season, week)` |
| fact_minor_eligibility | 04v `load_eligibility` | hand-rolled replace-by-`(season, week)` + dedup `(scorer_id, season, week)` | `replace_partition keys=(season, week)` |

04t and 04w only write `data/raw/*.json`, and the review files are CSVs
under `data/review/`. Both are file artifacts, **not tables**, and stay out
of the seam.

## 3. Read inventory (in scope)

The most-read tables are `dim_rookie_prospect` (×11), `dim_nfl_players` (×8),
`dim_position` (×8), `fact_rookie_rankings` (×6),
`fact_dynasty_ranking_metrics` (×7), `fact_fantrax_adp` (×6),
`fact_roster_placement` (×4), `dim_fantasy_teams` (×5), `dim_player_alias`
(×4) and `dim_contract` (×2).

Almost every write site also re-reads the same table in a QA cell
(`len(pd.read_parquet(path))` or a `df.head()` check). These become
`read_table(name)`, or they use the row count that `write_table` returns.

---

## 4. Partition-replace idioms and how they collapse

Five hand-written variants exist today. All of them become one of the three
seam modes:

1. **`etl.load_replace_partition(df, path, part_cols)`** (9 call sites). It
   derives the key tuples from `df`, deletes matching rows, appends and
   returns the total row count. This is `replace_partition(keys=part_cols)`
   and is the canonical shape.
2. **Hand-rolled replace-by-`(season, week)`** in 04a `load_fact`, 04v
   `load_placement` and 04v `load_eligibility`. It is a copy-paste of #1 with
   a trailing safety `drop_duplicates` on the grain, which is a violation of
   the modular-extraction rule. It becomes `replace_partition(keys=("season",
   "week"))`. The seam's grain-uniqueness check replaces the silent dedup:
   callers dedup explicitly and the seam raises if the batch still has
   duplicates.
3. **Explicit value-set delete** in 02d's transaction events: it deletes
   `event_type ∈ TXN_EVENT_TYPES` even when the new batch holds zero rows of
   some type. Derived keys cannot express that case (an empty type would
   leave stale rows). It becomes `replace_partition(partition={"event_type":
   TXN_EVENT_TYPES})`.
4. **`etl.upsert_dynasty_crosswalk`**. Despite the name, it replaces by
   `source` and is not a per-row upsert. It becomes
   `replace_partition(keys=("source",))`.
5. **Read, concat, dedup keep-last on the natural key**, used by the alias
   ×2, `add_players_from_source`, `ingest_ranking_source` and `mint_assets`.
   These are true upserts and become `upsert(keys=grain)`. Special case:
   `ingest_ranking_source` has a "first non-null `rank_date` wins" coalesce.
   That is business logic and stays in the caller (read the existing rows,
   compute, then upsert). The seam does not grow per-column merge policies.

`load_replace_partition` and `upsert_dynasty_crosswalk` stay as thin
deprecated shims (`Path(path).stem` becomes the table name) until every call
site is migrated, then they are deleted.

---

## 5. Dtype and shape hazards for a Postgres round-trip

The pyarrow audit of all 27 `data/*.parquet` files turned up two kinds of
problem: hazards that need handling in the seam, and places where the
current data breaks a candidate primary key.

**Hazards that need handling in the seam**

| Hazard | Where | Handling |
|---|---|---|
| **Nullable ints stored as float64 + NaN** | `dim_nfl_players.draft_year/round/number/height/weight`, `fact_fantrax_adp.overall_rank/games_played/age`, `fact_roster_transactions.contract_*/cap_hit/draft_round/pick_*`, `fact_fantasy_teams.contract_*`, combine `draft_*`/`bench_press`/`broad_jump`, `dim_contract.min_salary` | Phase 1: DDL mirrors the pandas dtype (`double precision`) so the round-trip is the identity. Tightening to `integer` is a later schema decision, not a seam concern. |
| **Arrow int64 read back as float64** | `fact_trade_log.draft_round/pick_in_round/draft_year` (the pandas metadata says object) | The registry dtype is authoritative, so the read coerces to it. |
| **pandas `Int64` (nullable ext.)** | `fact_rookie_rankings.draft_year/global_rank/positional_rank` | Postgres `bigint`. The read must restore `Int64` from the registry (a plain read gives float64/object). |
| **int32 vs int64** | `dim_nfl_players.years_of_experience/entry_year/last_season`, combine `season` | `integer`, but the read returns int64. Coerce from the registry, or `check_data_model` drift fires. |
| **All-NULL columns (arrow `null` type)** | `dim_nfl_teams.team_id_pfr/team_stadium`, **`dim_rookie_prospect.gsis_id`**, `dim_roster_asset.pick_ref`, `fact_draft_pick_future.pick_in_round/overall_slot`, `fact_minor_eligibility.games_played`, combine `ten_split/hand_size/arm_length/wingspan` | Postgres needs a real type, but `data_model.yml` records `object`. Each needs a declared SQL type (text / int / double) before DDL. |
| **Timestamps (all tz-naive)** | `snapshot_date` (us) on dynasty fact, pick curve, position ceiling; `event_date` (us) on the txn ledger and trade log; `dim_season.*_date` (ms, meta `[s]`) | `timestamp without time zone` (or `date` for the date-grain columns). The read must restore `datetime64[us]`/`[ms]` exactly. **No tz-aware columns exist**, so keep it that way (the seam rejects tz-aware input). |
| **Dates stored as ISO strings** | `capture_date`, `resolved_date`, `added_date`, `decided_date`, `rank_date`, `birth_date` | Keep them `text` in phase 1 so the round-trip is the identity. Promoting them to `date` is a separate modeling ticket, because date types are mixed across tables (`snapshot_date` is a timestamp, `capture_date` is a string). |
| **EAV `metric_num` NaN** | `fact_dynasty_ranking_metrics`: 500 rows NaN `metric_num` with `metric_text` set (text metrics); never both null | Normalize NaN to SQL `NULL` on write. Postgres `double precision` accepts a real `'NaN'` value, and a COPY-based loader would store NaN instead of NULL. That breaks `IS NULL` and the `summarizeBy: average` measures in Power BI. No `inf` values are present. |
| **Column-name casing** | `divisionId` (`fact_draft_pick`, `fact_draft_pick_future`), the only non-snake name | Postgres folds unquoted names to lowercase. Either quote it always (SQLAlchemy does) or rename it to `division_id`, which is a PBI `sourceColumn` cascade. Recommendation: rename before the backfill. All names are ≤63 chars. `format`, `round`, `value`, `status`, `position`, `source` and `week` are non-reserved in Postgres, so they are fine. |
| **pandas 3.x `str` dtype** | every string column (`pd=str`) | `text`. The read must return `str`, not `object`, to match the `check_data_model` expectations (it already treats `str`/`string`/`object` as equivalent). |
| **No categoricals, lists or structs, no mixed-type object columns** | — | Nothing to handle. |

**Grain violations (block PK declaration)**

The grain is checked from `docs/data_model.yml`. 25 of 27 tables are unique
and non-null on the declared grain. Two are not:

- **`fact_dynasty_ranking_metrics`**: 1,812 **Composite** rows (written by
  04y) have a null `source_player_id` and are keyed by `gsis_id` instead.
  The declared grain has 1,808 duplicates. Fix: 04y sets `source_player_id
  = gsis_id` (and `source_uid = "Composite|<gsis_id>"`), or the grain
  becomes source-specific. This needs a decision before the PK.
- **`fact_fantasy_teams`**: 29 rows have null `gsis_id` **and** null
  `player_key` (unresolved Fantrax players), which gives 15 duplicates on
  `(team_key, gsis_id)`. The grain needs to become `(team_key, asset_id)`
  (via `dim_roster_asset`) or `(team_key, scorer_id)`, which means adding
  that column.
- `fact_trade_log` is **not declared** in `data_model.yml`: it has no
  registry entry and no grain. Add it (likely `(transaction_id, asset_kind,
  scorer_id | pick ref)`; to be determined).

---

## 6. Consumers outside the seam (must be cut over separately)

| Consumer | Mechanism | Tables |
|---|---|---|
| **discord_bot** | `github_fetch.fetch_parquet(path, cfg)`: GitHub Contents API, TTL 600s cache, repo-relative `data/*.parquet` constants in `adp.py`, `cap.py`, `capmath.py`, `player.py`, `rankings.py`, `roster.py` | fact_fantrax_adp, dim_nfl_players, fact_fantasy_teams, dim_fantasy_teams, dim_division, dim_contract, fact_dynasty_ranking_metrics |
| **trade-bud** | `backend/data_access.py`: `read_parquet(name)` from local `data/`, plus it monkeypatches `capmath.fetch_parquet` to a local reader. `export_static.py` wraps `da.read_parquet` in `lru_cache`. `pages.yml` rebuilds on `data/**.parquet` pushes | dim_nfl_players, fact_dynasty_ranking_metrics, fact_fantrax_adp, dim_position_ceiling, fact_draft_pick, fact_draft_pick_future, dim_pick_value_curve, dim_position, fact_fantasy_teams, dim_fantrax_crosswalk, dim_fantasy_teams, fact_trade_log, dim_contract (via capmath) |
| **Power BI** | `Parquet.Document(File.Contents("C:\Users\benha\...\data\<t>.parquet"))` in 16 TMDL partitions (17 paths; Fact_DraftPick unions pick + future) | Dim_Contract, Dim_Division, Dim_DynastyMetric, Dim_FantasyTeams, Dim_NFLPlayers, Dim_NFLTeams, Dim_Position, Dim_RookieProspect, Dim_School, Dim_Season, Fact_DraftPick(+future), Fact_DynastyRankingMetrics, Fact_FantasyTeams, Fact_FantraxADP, Fact_NFLCombineProDay, Fact_RookieRankings |
| **run_pipeline.commit_data** | `git add data/*.parquet` allowlisted direct-to-main commit | all |
| **discord_bot tests** | `test_offline_smoke.py` reads local parquet and uses fake frames keyed by filename | — |

Both non-PBI consumers already have **one choke point each**
(`fetch_parquet`, `da.read_parquet`), so cutting them over is a one-function
swap per consumer. They should not import `etl_helpers`: the bot deploys
standalone on Railway, and trade-bud CI installs only
`backend/requirements.txt`. Give them a small read-only client instead
(supabase REST or psycopg) behind the same function name.

---

## 7. Proposed seam interface

It lives in `notebooks/etl_helpers.py`, in a "Storage seam" section, per
the modular-extraction rule. The Postgres backend goes in a sibling module,
`notebooks/etl_storage_pg.py`, that is **lazy-imported** only when
selected, so the parquet path never needs sqlalchemy or psycopg.

```python
from typing import Collection, Literal, Mapping, Sequence

WriteMode = Literal["replace", "replace_partition", "upsert"]

def read_table(name: str, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """Whole table (or a column projection), dtypes coerced to the
    docs/data_model.yml registry. Raises TableNotFound if absent."""

def table_exists(name: str) -> bool: ...

def write_table(
    name: str,
    df: pd.DataFrame,
    *,
    mode: WriteMode = "replace",
    keys: Sequence[str] | None = None,
    partition: Mapping[str, Collection] | None = None,
) -> int:
    """Write df to table `name`; return the table's total row count after.

    replace            table := df
    replace_partition  delete rows matching the partition, then insert df.
                         keys=cols        -> partition = distinct df[cols] tuples
                                             (today's load_replace_partition)
                         partition={c: v} -> explicit value set, works with an
                                             empty df (02d TXN_EVENT_TYPES)
                         exactly one of keys / partition; neither -> the
                         (snapshot_date, source_name) default is NOT implied:
                         be explicit.
    upsert             insert-or-replace rows on keys (default: registry grain);
                         other rows untouched.
    """
```

These rules apply in every mode and on both backends:

- **Grain guard**: `df` must be unique and non-null on the registry grain.
  If it is not, the write raises instead of silently deduping; callers dedup
  explicitly.
- **Schema guard**: `df` columns must equal the registry columns. The seam
  coerces dtypes to the registry, rejects tz-aware timestamps and
  normalizes NaN/NaT to NULL.
- **Atomic write**: the parquet backend writes a temp file and then calls
  `os.replace` (today a crash mid-`to_parquet` can truncate a table). The
  Postgres backend runs delete + insert in one transaction.
- **Backend selection**: `LeagueConfig.storage_backend = "parquet"` is the
  default, overridden by the env var `ETL_STORAGE=postgres` together with
  `SUPABASE_DB_URL`. Nothing changes at call sites.
- **Registry**: `docs/data_model.yml` (columns, dtypes, grain) is the single
  schema source. The same file drives Postgres DDL generation,
  `check_data_model.py` and read-side dtype coercion. `fact_trade_log` must
  be added first.
- **Out of scope for now (YAGNI)**: row filters or `where=` on read (no
  caller filters at read time today; add it when Postgres makes it pay),
  append-only mode (no caller needs one), and column-level `update` (FK
  backfills rewrite small tables; revisit later).

**How tests cover it.** Add `tests/test_etl_storage.py`, a contract suite
parametrized over backends:

- The parquet backend always runs, with `tmp_path` plus a monkeypatched
  `CFG.data_dir` and a tiny fixture registry.
- The Postgres backend runs only when `TEST_DATABASE_URL` is set (a local
  Supabase or Docker instance) and is skipped otherwise.

The cases:

- `replace` round-trips the data.
- `replace_partition` via `keys` leaves no orphans when composition shifts.
- `replace_partition` via `partition=` with an empty `df` clears the slice.
- `upsert` gives keep-latest behavior and leaves other rows untouched.
- A duplicate-grain batch raises.
- A column mismatch raises.
- A tz-aware input raises.
- The return value is the total row count.
- **Dtype identity** for each hazard class in section 5: `Int64`, float
  NaN, int32, `datetime64[us]`/`[ms]`, all-null column, bool, `str`, and a
  camelCase column.
- **Golden round-trip**: every `data/*.parquet` goes through `write_table`
  then `read_table` and passes `assert_frame_equal`. This is the backfill
  acceptance test.

Add a **static guard test** that fails on any `read_parquet` or
`to_parquet` in `notebooks/`, `scripts/` or `.ipynb` code cells outside the
seam section of `etl_helpers.py`. This locks in the migration.

---

## 8. Migration order

> **Decided 2026-10-02 in [ADR-0018](../adr/0018-supabase-schema-and-rls.md)
> (#75):** the prereqs below are settled there, and types are tightened at
> cutover through to the snapshot, superseding the "mirror pandas in phase 1"
> handling in section 5.

0. **Prereqs** (decision tickets): the Composite `source_player_id` grain,
   the `fact_fantasy_teams` grain, `fact_trade_log` in `data_model.yml`, SQL
   types for the all-NULL columns, and the `divisionId` rename.
1. **Land the seam with the parquet backend** plus the contract tests.
   There is no behavior change. Re-implement `load_replace_partition`,
   `upsert_dynasty_crosswalk`, `add_players_from_source` and
   `ingest_ranking_source` internals on top of the seam, keeping their
   signatures as shims.
2. **Partition-replace writers**: 04b, 04x, 04f, 04y, 04d, 04e, 04u and
   02d. These are the shared idioms with the highest leverage.
3. **Hand-rolled replace-by-week**: 04a `load_fact`, 04v
   `load_placement`/`load_eligibility`, and the 02d `TXN_EVENT_TYPES`
   delete. Drop the 04a `score→fpts` migration shim (the data is already
   migrated).
4. **Read-modify-write / upsert**: `dim_roster_asset`, `dim_player_alias`,
   `dim_rookie_prospect`, `fact_rookie_rankings`, and the FK back-fills in
   04z and `scripts/apply_fantrax_crosswalk_review.py`.
5. **Seeds and full rebuilds**: 01a–01g, 02a, 02c, 02e, 03y, 04c (mechanical).
6. **Readers**: every remaining `read_parquet` in notebooks, 05a,
   `run_pipeline` and `check_data_model`, which should validate the registry
   against `read_table`. Then turn on the static guard test. Delete the shims.
7. **Then** (separate tickets on map #69): the Postgres backend plus a
   backfill that passes the golden round-trip; consumer cutover for the bot
   (`fetch_parquet`), trade-bud (`da.read_parquet` / `export_static` /
   `pages.yml`) and PBI (`File.Contents` → PostgreSQL connector); and the
   fate of `run_pipeline.commit_data`.
