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

## Pending: singular/plural table-name rename (identified 2026-07-11, not yet done)

6 of 9 report-facing Dim tables are singular (`Dim_Contract`, `Dim_Division`,
`Dim_Position`, `Dim_RookieProspect`, `Dim_School`, `Dim_DynastyMetric`); 3 are
plural (`Dim_FantasyTeams`, `Dim_NFLPlayers`, `Dim_NFLTeams`). Facts skew
plural/collection-style throughout (`Fact_DynastyRankingMetrics`,
`Fact_FantasyTeams`, `Fact_RookieRankings`), which reads as a defensible
separate convention for facts — the inconsistency is dim-only. Agreed fix:
rename the 3 outliers to singular (`Dim_FantasyTeam`, `Dim_NFLPlayer`,
`Dim_NFLTeam`). Bigger blast radius than a typical rename — touches
`relationships.tmdl`, `cultures/en-US.tmdl`, and visuals across **all 4**
report pages (Fantasy Teams, Dynasty Rankings, Rookie Rankings, Rookie
Combine & Pro Day), not just one. Agreed to land as its own commit on
`data-2026-draft-cap-update` (see project-fantasy-football.md branch note),
separate from the cap-consistency fix. Use the full rename-cascade checklist
below.

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

## No ETL-frozen rollups on Dim tables (principle, fixed 2026-07-11)

Real bug found on the Fantasy Teams page: `Dim_FantasyTeams` carried an
ETL-precomputed cap rollup (`ActiveRosterSalary`, `CapHitsCurrentYr`,
`RemainingCapCurrentYr`, etc. — frozen snapshot from `02e`, team-grain, no
relationship to player attributes) that visuals bound to **directly alongside**
live `SUM(Fact_FantasyTeams[...])` aggregations in the same pivot table. Apply
any slicer (e.g. position) and the live sum shrinks while the frozen column
doesn't move — numbers stop reconciling. Same failure mode independently in a
measure that mixed `MAX(Dim_FantasyTeams[RemainingCapCurrentYr])` with a live
`SUM`. Also found: `CapHitsCurrentYr`'s docstring said "cap hits" but the ETL
actually computed it as `SUM(DeadMoney)` — a real dollar figure hidden under a
generic name (dead money's actual home is `Fact_FantasyTeams.DeadMoney`,
contract-value grain — `Dim_Contract` only holds the *rule* (`Guaranteed`)
that determines whether dead money applies, never the dollar amount, since
that needs a specific player's contract value).

**Fix, applied end-to-end (not just PBI)**: dimension tables get *only* facts
that are true independent of the roster (`OriginalCap`, `ReinvestmentCap` for
`Dim_FantasyTeams`). Everything roster-derived is computed live: DAX measures
here (`'Active Roster Salary'`, `'Contract Value'`, `'Dead Money'`,
`'Remaining Salary Cap'`, `'Percent of Cap Used/Remaining'`, `'Player Pct of
Team Cap'` — all in `_Measures.tmdl`, all resolve against `Fact_FantasyTeams`
+ `Dim_Contract`/`Dim_FantasyTeams[OriginalCap|ReinvestmentCap]`, none touch a
cached Dim column), and the equivalent pandas logic in
`discord_bot/capmath.py` for the bot (which has no DAX engine — same formula,
computed on read instead of cached at ETL time). **The rule going forward:**
if a number can be derived from a fact table, it's a measure, not a stored
Dim column — even if a non-PBI consumer (the bot) needs the same number; give
that consumer its own live computation rather than caching it back into a Dim.

**Follow-on finding, same session**: `Fact_FantasyTeams.CapHit`/`.Conference`
were the same anti-pattern one level down — stored fact columns 100%
derivable via a relationship (`CapHit` = `ContractValue x RELATED(Dim_Contract
[CapHitPct])`, needed adding the missing `ContractID→Dim_Contract.ContractID`
relationship first; `Conference` via the existing `TeamKey→Dim_FantasyTeams`
relationship). Both removed from the TMDL and `02e`'s output schema. `DeadMoney`
was deliberately left alone — no single-row formula exists yet, it needs real
drop-event tracking (ledger `drop` event type doesn't exist). Its
`dim_season.relative_nfl_season_number` dependency is now built (`01f`,
2026-07-11) but `dim_season` isn't in this semantic model yet — needs a table
+ relationship before the dead-money measures can reference it. Full 3-version
design (current/next/total year) is in the project's `PLAN.md`, being built
live by the user in `_Measures.tmdl`.

**Gotcha hit while fixing this**: the user had Power BI Desktop open on the
same `.pbip` and was independently fixing the same visuals/measures — file
mtimes changed on disk mid-session without any edit from me. Before large
TMDL/PBIR edits, check `git status`/file mtimes for unexplained recent
changes and ask whether Desktop is open before assuming the state you last
read is still current — Desktop autosaves TMDL on every model change.

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
