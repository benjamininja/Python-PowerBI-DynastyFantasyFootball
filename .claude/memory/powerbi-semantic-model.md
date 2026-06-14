# Power BI Semantic Model & Report (PBIP / TMDL / PBIR)

The dynasty project has a **PBIP project** (source-control format) alongside the
legacy binary. Established/standardized 2026-06-07 (merged to `main`, PRs #4+#5).

## Location & format
- Project root: `pbi/mouserat2/Mouserat2.pbip`
- **Semantic model (TMDL)**: `pbi/mouserat2/Mouserat2.SemanticModel/definition/`
  — `model.tmdl`, `relationships.tmdl`, `database.tmdl`, `cultures/en-US.tmdl`
  (Q&A linguistic schema), `tables/*.tmdl`, `diagramLayout.json`.
- **Report (PBIR)**: `pbi/mouserat2/Mouserat2.Report/definition/`
  — `report.json`, `pages/<id>/page.json`, `pages/<id>/visuals/<id>/visual.json`.
- Legacy `pbi/Mouserat2.pbix` (binary) still exists — user's separate file; leave
  out of commits unless told.
- **Edit TMDL/PBIR files in place** (git-tracked local repo; user reviews diff).
  Not a live Fabric model. The `anthropic-skills:semantic-modeling-prepforai`
  skill is HISD-flavored but its TMDL rules/gates apply here.

## Naming convention (set 2026-06-07)
- **Tables** → `Fact_` / `Dim_` PascalCase. **Acronyms UPPERCASE**: NFL, ADP, GSIS,
  PFR, PFF, ESPN, ESB, OTC, ID, UID. e.g. `Dim_NFLPlayers`, `Fact_FantraxADP`,
  `Fact_DynastyRankingMetrics`. `_Measures` + system date tables keep their names.
- **Columns** → PascalCase, same acronym rule. **Shorthand that is NOT an
  initialism is Title-case, not uppercased** — e.g. `OVR` (overall) → `Ovr`
  (`DraftOvr`). `gsis_id`→`GSISID`, `source_uid`→`SourceUID`, `nfl_team`→`NFLTeam`.
- **CRITICAL: `sourceColumn` stays snake_case** (it maps to the parquet column).
  So parquet/ETL output = snake_case, model display = PascalCase, bridged by
  `sourceColumn`. Power Query M is **untouched** (reads source columns). Don't
  rename the data layer to match unless the user explicitly asks (big change).
- **Relationships** named `{FromTable}_to_{ToTable}_via_{Key}` (business key term);
  leave the system `LocalDateTable` relationship as its GUID.

## Rename cascade (renaming a table/column touches MANY files)
Update: table decl + `partition` line; `sortByColumn`; DAX `Table[col]` (incl.
quoted `'Table'[col]` — e.g. the LocalDateTable Calendar expr); `relationships.tmdl`
`fromColumn`/`toColumn` **and** relationship names; `cultures/en-US.tmdl`
(`ConceptualEntity`/`ConceptualProperty` + `"Table.col"` keys); **and the report**
(`Entity`, `Property`, `nativeQueryRef`, `queryRef`). 
**Protect (do NOT change):** `File.Contents("...parquet")` paths, Power Query M
source-column refs (`[col]`, `{"col",...}`), `sourceColumn:`, measure names.
- Build the **column map from `sourceColumn`→decl** = exactly the old→new the
  report/culture need. Scope replacements to reference keys (display titles also
  contain words like "Season"/"Status").
- Auto-generated Q&A entity-key stubs in the culture file are stemmed
  (`Fact_X.game_played`) — their *bindings* point to real PascalCase objects;
  leave the stubs, Power BI regenerates them.

## Prep-for-AI gates (TMDL metadata)
- `///` description (≤200 chars, no filler) on **every** table, column (incl
  hidden), and measure.
- Dual `annotation Synonyms = a|b|c` + `annotation SynonymCollection = ["a","b","c"]`
  (identical terms, 3–7) on every **visible** table/column/measure. Hidden objects
  get a `///` but **no synonyms**.
- Preserve `lineageTag`/`sourceLineageTag` + non-AI annotations
  (`SummarizationSetBy`, `PBI_FormatHint`, `changedProperty`, `sortByColumn`).
  Never add phantom annotations.

## Dynasty measures (`_Measures` table)
User's chosen aggregation: **latest snapshot, average across format**, player-grain.
- Hidden bases: `Metric Value` (`MAX(ALLSELECTED(SnapshotDate))` → `AVERAGE(MetricNum)`
  at that snapshot), `Metric Value Total` (`AVERAGEX` over `SourceUID` — values/ranks),
  `Metric Count Total` (`SUMX` over `SourceUID` — crowd counts kept/traded/cut).
- Player-grain leaves filter on **stable `MetricKey`** (NOT `MetricLabel` — user
  relabels). `(total)` subtotal-correct variants live in folder
  `Dynasty Rankings - extra`. Refactors preserve `lineageTag`.
- Legacy `Metric Sum` = raw `SUM(MetricNum)` → **double-counts format-agnostic
  metrics** (KTC kept/traded/cut, trends are duplicated per format row). Prefer the
  per-metric measures / `Metric Value`. Swap report matrix `[Metric Sum]`→`[Metric Value]`.
- **Caveat**: latest-snapshot measures are NOT usable for historical trend visuals
  (every snapshot row shows the latest value). Use raw `MetricNum` for trends.
- The measures still hold post-2026-06-12 refactor (filter on `MetricKey`, AVERAGE over
  `SourceUID`); ranks are now metric_keys too. See "Dynasty model refactor" below.

## Git hygiene (PBIP)
- `.gitignore`: `**/.pbi/` + `*.abf` (local cache/settings). Commit `.platform`,
  `definition.pbip`/`.pbism`/`.pbir`, all TMDL, report JSON, `StaticResources`.
- Squash-merge PRs into `main` with a body-of-work description.

## Dynasty model refactor (2026-06-12, via /grill-me)
Two-layer → **single EAV fact**. Changes are in the TMDL + notebooks; *pending* a
pipeline rerun (04b→04x→04y→04c) and the user deleting `Fact_DynastyRankings` (table file,
its `ref` in model.tmdl, its 4 relationships) from the model:
- `Fact_DynastyRankings` **retired**; `overall_rank`/`positional_rank` folded into
  `Fact_DynastyRankingMetrics` as source-prefixed metric_keys (`ktc_/ds_/fp_*`).
- `GSISID` column added to the metrics fact → its own active relationship to
  `Dim_NFLPlayers` (name/pos/team/age come from the dim, not the fact; no-gsis players drop).
- `SourceName` **removed** from the metrics fact — source now lives on
  `Dim_DynastyMetric.SourceName` (one source per metric_key); `source_name` stays in the
  parquet because the partition load keys on it.
- `MetricNum` + rank columns → `summarizeBy: average`. `SnapshotDate` → `dateTime`.
- Dead `MetricIndex` column + its hardcoded-`"20260606-"` Power Query step **removed** —
  this resolves the old cross-snapshot-collision latent bug.
- `adp` split into `ktc_adp`/`ds_adp`; new `composite_adp` percentile blend (notebook 04y).
