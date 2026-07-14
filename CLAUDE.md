# CLAUDE.md

Project: 28-team, dual-conference IDP dynasty fantasy football league — ETL
(Python/pandas/parquet) + Power BI (PBIP/TMDL) + a Discord rankings bot.
League details: [README.md](README.md). Branch/PR/commit conventions:
[CONTRIBUTING.md](CONTRIBUTING.md).

> **Always read overarching developer preferences from
> `C:\Users\benha\.claude\memory\preferences.md` before generating code.**

## Memory layout

Two memory stores, different scopes:

- **`.claude/memory/` (this repo, project-specific)** — moved here 2026-06-13
  from the global store:
  - [data-model.md](.claude/memory/data-model.md) — full star-schema, table
    grains, dynasty single-EAV-fact design, pipelines
  - [powerbi-semantic-model.md](.claude/memory/powerbi-semantic-model.md) —
    TMDL naming, rename cascade, Prep-for-AI gates, dynasty measures
  - [project-fantasy-football.md](.claude/memory/project-fantasy-football.md) —
    league context, notebook inventory, source registries, branch/secret state
- **`C:\Users\benha\.claude\memory\` (global, cross-project)**:
  - `preferences.md` — working style: caveman lite, grill-me before code,
    `AskUserQuestion` for design decisions, `.ipynb`-only notebooks, git/TMDL
    editing conventions, scraper standards, environment gotchas
  - `MEMORY.md` — index across all of Ben's projects

Read the relevant `.claude/memory/*.md` file before touching dynasty/PBI
tables — it has the grain, FK strategy, and FD rules that aren't obvious from
the parquet alone.

## Project-wide architectural rules

- **Dependencies**: `requirements.txt` (repo root) is the single source of
  truth for the `.venv` used by `run.ps1` — curated, loosely pinned (mirrors
  `discord_bot/requirements.txt`), not a full `pip freeze`. Hitting a
  `ModuleNotFoundError` while running a notebook/script means the package is
  missing from this file — add it there, don't just `pip install` ad hoc.
- **Storage**: parquet for every dim/fact table (`data/*.parquet`); CSV only
  for human-review staging (`data/review/*.csv`). Migration path to Fabric =
  swap `pd.read/write_parquet` for `spark.read.parquet` + `abfss://` — schema
  stays identical, so don't design around a future migration, just keep the
  schema clean.
- **Shared config/helpers**: `notebooks/etl_helpers.py` is the single source
  of truth — `LeagueConfig`/`CFG`/`DATA`/`REVIEW` (repo-root-anchored, CWD
  independent), `clean_player_name`, `generate_player_key`,
  `parse_height_to_inches`, `_make_session`, `resolve_dynasty_crosswalk`,
  `load_replace_partition`, `SOURCE_PREFIX`/`ZERO_IS_MISSING`/
  `fold_ranks_long`. Import it, never copy it. New writers use
  `DATA`/`REVIEW`/`CFG.path()` — never a bare `"data/..."` string.
- **Identity model**: `gsis_id` (→ `dim_nfl_players`) is the long-term player
  FK everywhere; `player_key` (→ `dim_rookie_prospect`, MD5 of name+pos+school)
  is the interim pre-signing FK. Per-source crosswalks
  (`dim_fantrax_crosswalk`, `dim_dynasty_crosswalk`) resolve source-native IDs
  to both.
- **Dynasty fact = single EAV** (`fact_dynasty_ranking_metrics`, refactored
  2026-06-12): one row per `(snapshot_date, source_name, source_player_id,
  format, metric_key)`. New sources/metrics add **rows**, never columns. Each
  `metric_key` maps to exactly **one** `source_name` (the FD that lets source
  live in `dim_dynasty_metric`, not on the fact). See data-model.md before
  adding/renaming any `metric_key`.
- **Transformer tables** (`dim_position`, `dim_school`): every notebook
  touching position/school joins these. Add a row for a new raw value — never
  add if/else downstream.
- **Communication**: caveman lite is the standing brevity preference. For any
  ambiguous architectural/design decision, use `grill-me` (one question at a
  time, recommended answer first) and get explicit sign-off before writing
  code — don't present a fait accompli.
- **Execution loop**: long agentic builds follow the token-gated
  `grill/plan → consolidate → compact → execute → compact ↺` loop (compact at
  ~35% Opus window) — see
  [ADR-0001](docs/adr/0001-token-gated-grill-execute-loop.md). `PLAN.md` is the
  heartbeat, updated every seam; ADR/CONTEXT/memory crystallize on real signal.
- **Git**: feature branch → `main` via PR, squash-merge,
  `--delete-branch`. One logical change per PR. Commits use the GitHub noreply
  author email (`38588919+benjamininja@users.noreply.github.com`) — repo
  `user.email` is already set to it. Commit only when asked. **One codified
  exception**: `scripts/run_pipeline.py` (the scheduled orchestrator) commits
  machine-generated `data/*.parquet` refreshes directly to `main`
  (allowlist-verified, change-detected, rebase-then-push — CONTRIBUTING.md).
- **Secrets**: never commit `.env`/`*.env`/`.env.*` (template `.env.example`
  is the exception), `data/.pw_profile/`, `data/raw/`, `data/review/`,
  `api_key.txt`. Bot/scraper code does no destructive or write-side calls to
  external services beyond what's specified.

## `notebooks/` & `scripts/` — Python / ETL standards

- **Format**: `.ipynb` for every ETL notebook. Bare `.py` only for: a
  scheduled headless script (`04a_fantrax_weekly_scrape.py`, Task Scheduler),
  a CLI consumer (`05a_startup_draft_board.py`), or standalone
  apply/review utilities in `scripts/` (e.g.
  `apply_fantrax_crosswalk_review.py`) — these share `etl_helpers` like
  notebooks do.
- **Naming**: `NN<letter>_name` — `01`=dim seeds, `02`=core facts,
  `03`=rookie-ranking pipeline, `04`=dynasty-ranking pipeline (incl. Fantrax).
  Letter = order within group; `x`/`y`/`z` reserved for late-stage/apply/
  resolver steps. `notebooks/README.md` is the source of truth for order.
- **Import bootstrap** (every notebook, CWD = repo root):
  ```python
  import sys
  from pathlib import Path
  for _p in (Path.cwd() / "notebooks", Path.cwd()):
      if (_p / "etl_helpers.py").exists():
          sys.path.insert(0, str(_p)); break
  import etl_helpers as etl
  from etl_helpers import CFG, DATA, REVIEW
  ```
- **Modular extraction rule**: if logic is needed by >1 notebook (matching,
  rank-folding, partition loads, source-prefix maps, sentinel-cleaning
  rules), it belongs in `etl_helpers.py`, not copy-pasted with "slight
  variation" per notebook — that's how the same bug gets fixed twice and
  missed once. `resolve_dynasty_crosswalk`, `load_replace_partition`,
  `fold_ranks_long`, `SOURCE_PREFIX`, `ZERO_IS_MISSING` are this pattern.
- **Editing `.ipynb` programmatically**: load JSON → mutate `cell["source"]`
  (`[l + "\n" for l in lines[:-1]] + lines[-1:]`) → `json.dump(nb, f,
  ensure_ascii=False, indent=1)`. Find cells by `cell["id"]`, never by index.
  Prefer a full-cell rebuild over >3 stacked patches in one session.
- **Network calls**: wrap in try/except with descriptive errors;
  `etl._make_session()` gives retry/backoff. HTTP 200 ≠ success for JSON APIs
  — check the response body for logical errors.
- **Fuzzy matching**: `thefuzz.fuzz.token_sort_ratio`, auto ≥90 / review
  70–89 / new <70, consult `dim_player_alias` first so decisions aren't
  re-asked.

## `pbi/` — Power BI / TMDL standards

PBIP project at `pbi/mouserat2/` (TMDL semantic model + PBIR report),
git-tracked source-control format — edit in place, user reviews the diff
(not a live Fabric model). Legacy `pbi/Mouserat2.pbix` is separate/untracked
in commits unless asked.

- **Naming**: tables `Fact_`/`Dim_` PascalCase; columns PascalCase. True
  initialisms UPPERCASE (NFL, ADP, GSIS, ID, UID); non-initialism shorthand is
  Title-case (`Ovr`, not `OVR`). **`sourceColumn` stays snake_case** — it maps
  to the parquet column; Power Query M is untouched. Relationships:
  `{FromTable}_to_{ToTable}_via_{Key}`.
- **Rename cascade**: a column/table rename touches table decl +
  `partition`/`sortByColumn`, DAX `Table[col]` refs, `relationships.tmdl`
  (`fromColumn`/`toColumn` + relationship names), `cultures/en-US.tmdl`
  (`ConceptualEntity`/`ConceptualProperty` + `"Table.col"` keys), and the
  report (`Entity`/`Property`/`nativeQueryRef`/`queryRef`). Build the
  `sourceColumn`→decl map first; never touch `File.Contents(...parquet)`
  paths or PQ source-column refs.
- **Prep-for-AI gates**: every visible table/column/measure gets `///`
  description (≤200 chars, no filler) + matching `Synonyms` /
  `SynonymCollection` annotations (3–7 terms, identical in both). Hidden
  objects get `///` only, no synonyms. Never add phantom annotations
  (`Copilot_*`, `FDA_*`, `AI_*`) not already present.
- **Fidelity**: preserve `lineageTag`/`sourceLineageTag` verbatim and all
  non-AI annotations (`SummarizationSetBy`, `PBI_FormatHint`,
  `changedProperty`, `sortByColumn`) on every edit.
- **Dynasty model (post 2026-06-12)**: `fact_dynasty_ranking_metrics` is the
  only dynasty fact, with its own `GSISID` → `Dim_NFLPlayers` relationship.
  `MetricNum` and rank columns default `summarizeBy: average` (sums of ranks
  are meaningless). Source attribution lives on `Dim_DynastyMetric.SourceName`
  (one source per `MetricKey`), not on the fact.
- **Measures**: dynasty `_Measures` use latest-snapshot + average-across-format,
  filtered on the stable `MetricKey` (not the user-editable `MetricLabel`).
  `(total)` subtotal-correct variants live in `Dynasty Rankings - extra`. Raw
  `MetricNum` for trend visuals (latest-snapshot measures collapse history).

## `discord_bot/` — bot standards

Source of truth: the `discord-bot-github-fetch` skill
(`~/.claude/skills/discord-bot-github-fetch/`) — keep it in sync with any
architecture change here.

- **Commands**: `@commands.hybrid_command` (slash + prefix from one
  definition). Slash needs no privileged intent; prefix needs Message Content
  intent ON.
- **Data access**: `github_fetch.py` — authenticated GitHub Contents API
  (PAT scoped **Contents: Read-only, this repo only**), TTL-cached. The bot
  performs **no writes** to GitHub, ever. Don't add a second ad-hoc fetch path
  — extend `github_fetch.py`.
- **Privacy-by-default**: replies are ephemeral unless the user opts in via
  the `share:true` slash option or the `ShareView` "Post publicly" button.
  Prefix commands in a public channel DM the requester instead (📬 react;
  redirect if DMs closed). Routing goes through `_deliver_embeds`/
  `_deliver_text` — reuse, don't fork new delivery paths.
- **Embed limits**: build against `len(discord.Embed)` (Discord's own
  accounting of title+fields+footer vs the 6000-char total cap) and
  `_MAX_FIELDS_PER_EMBED`/`_MAX_FIELD_VALUE`, not a hand-summed estimate.
  Render with `pd.isna`-aware formatting — pandas `NaN`/`pd.NA` break naive
  `x or ""` / `int(x)`.
- **Failure modes**: fail fast at startup on `LoginFailure` /
  `PrivilegedIntentsRequired` (`SystemExit(1)` in `main`) and slash-sync
  `Forbidden` (in `setup_hook`, not the whole gateway). Runtime errors during
  a command: generic user-facing message + `log.exception` server-side —
  never leak stack traces or data into the reply.
- **Deploy**: Railway, `rootDirectory: discord_bot`, secrets as service
  variables (never baked into image/repo). `railway.json` is the **single**
  start-command source — no `Procfile` (Railway silently prefers it and will
  override `railway.json`). Bounded restarts (`ON_FAILURE`,
  `restartPolicyMaxRetries: 5`).

## `workspace/`, `skills/`, `archive/`

- `workspace/` is scratch space (VS Code workspace file, ad-hoc probe
  scripts). Remove one-shot patch/probe `.py` files after use — don't let
  them accumulate as pseudo-history.
- `skills/` holds repo-local reference docs (e.g. Deneb visuals
  instructions) — not code, read on demand.
- `archive/` is historical/retired artifacts (old `.pbix`, pre-parquet CSVs)
  — don't build against it.
