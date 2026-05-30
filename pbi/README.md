# `pbi/`

Power BI reporting layer. Connects to the Parquet tables in `../data/` — refresh after
running the ETL notebooks.

## Contents

| Path | Format | Notes |
|---|---|---|
| `Mouserat2.pbix` | Binary `.pbix` | The packaged report + model. Open in Power BI Desktop. |
| `mouserat2/` | **PBIP** (Power BI Project) | Source-control-friendly export of the same report. |

### `mouserat2/` (PBIP)

- `Mouserat2.pbip` — project entry point
- `Mouserat2.SemanticModel/` — model as TMDL (tables, measures, relationships) — diff-friendly text
- `Mouserat2.Report/` — report layout as JSON

The PBIP folder is the preferred format for tracking model/report changes in git (text-based,
reviewable diffs) versus the opaque binary `.pbix`. Save from Power BI Desktop via
**File → Save as → Power BI project (.pbip)**.

## Refresh

The model reads the Parquet files in `../data/`. After an ETL run, refresh in Power BI Desktop
so visuals reflect the latest `fact_*` / `dim_*` tables.
