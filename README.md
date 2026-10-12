# Python · Power BI · Dynasty Fantasy Football

Data pipeline and owner tools for a 28-team, dual-conference IDP dynasty
fantasy football league. Python notebooks pull league data from Fantrax, NFL
data from nflverse and expert rankings from several sites into a star-schema
set of tables. Those tables feed a Power BI report, a Discord bot and a
trade-diagnostic web app.

Built by millennial excellence; you're welcome. [League principles](docs/PRINCIPLES.md).

---

## League overview

| Setting | Value |
|---|---|
| Format | Dynasty · IDP |
| Teams | 28 (14 per conference) |
| Conferences | Riddell (A01–A14) · Wilson (B01–B14) |
| Salary cap | $300,000,000 per team |
| FA minimum | $2,000,000 |
| Draft year (active) | 2026 |

---

## What is in the repo

| Folder | What it holds | Read more |
|---|---|---|
| `notebooks/` | The ETL: numbered notebooks and scripts, plus the shared `etl_helpers.py` | [notebooks/README.md](notebooks/README.md) |
| `data/` | The published snapshot: one parquet file per table | [docs/DATA_MODEL.md](docs/DATA_MODEL.md) |
| `scripts/` | The scheduled orchestrator (`run_pipeline.py`) and the checks | [CONTRIBUTING.md](CONTRIBUTING.md) |
| `pbi/` | Power BI project (PBIP: TMDL semantic model + PBIR report) at `pbi/mouserat2/` | [pbi/README.md](pbi/README.md) |
| `discord_bot/` | League Discord bot: `rankings`, `player`, `adp`, `roster`, `cap` | [discord_bot/README.md](discord_bot/README.md) |
| `mouserat_trade-bud/` | Trade-diagnostic web app, published as a static site | [mouserat_trade-bud/README.md](mouserat_trade-bud/README.md) |
| `tests/` | Regression tests for the helpers, checks and tools | [ADR-0008](docs/adr/0008-regression-testing-standard.md) |
| `docs/` | Principles, data model, source manifest, decision records, research | below |

---

## Data model

A star schema of `dim_*` and `fact_*` tables. Three documents describe it,
and each is checked by a script so it cannot drift from the tables:

- [docs/DATA_MODEL.md](docs/DATA_MODEL.md): every table and how they join.
  Generated from `docs/data_model.yml`.
- [docs/SOURCES.md](docs/SOURCES.md): every outside source, what it feeds
  and how often. Generated from `docs/sources.yml`.
- [CONTEXT.md](CONTEXT.md): the league's vocabulary (Roster Asset, Draft
  Pick, Sign, Exercise, Trade and the rest).

The main groups of tables:

- **Players and identity:** `dim_nfl_players` (keyed by `gsis_id`),
  `dim_rookie_prospect` (keyed by `player_key` until a prospect signs), and
  the crosswalks that map each source's own player ids to both.
- **League structure:** teams, conferences and divisions, seasons, scoring
  periods, contract types.
- **Rosters and money:** the ledger of roster moves, the roster as it stood
  at each period's lineup lock, dead money, trades, draft picks.
- **In-season results:** points by scoring period and the weekly matchups.
- **Rankings:** rookie rankings by source and phase, and one dynasty fact
  holding every source's values and ranks as rows.

Storage: the tables are being moved to Supabase Postgres as the system of
record, written through one storage seam in `etl_helpers`
([ADR-0014](docs/adr/0014-supabase-system-of-record-static-serving.md)).
Until that lands the parquet files are the store. Either way `data/*.parquet`
is the snapshot that Power BI, the bot and the trade tool read.

---

## Running the pipeline

`scripts/run_pipeline.py` runs the scheduled part of the ETL in dependency
order, checks each group of tables before publishing it, and commits only
the groups that passed. It runs weekly on Windows Task Scheduler through
`run_weekly.ps1`; a move to GitHub Actions is planned
([ADR-0015](docs/adr/0015-etl-on-github-actions-owner-pii-confined.md)).

```powershell
.\run.ps1 scripts\run_pipeline.py --check-only   # run the checks, no steps
.\run.ps1 scripts\run_pipeline.py --dry-run      # show what would run
```

Some steps stay manual by design: the live draft, the rankings that arrive
as Excel files, and the review of uncertain player matches. Notebook order
and run modes are in [notebooks/README.md](notebooks/README.md).

---

## Setup

```powershell
git clone https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball.git
cd Python-PowerBI-DynastyFantasyFootball
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pre_commit install
```

`requirements.txt` is the single list of dependencies. Run every notebook
and script from the repository root. Fantrax credentials go in a gitignored
`.env` file (template: `.env.example`); they are never committed.

---

## Power BI

Open `pbi/mouserat2/` in Power BI Desktop. The model reads the parquet files
in `data/`; refresh after a pipeline run. See [pbi/README.md](pbi/README.md).

---

## Discord bot

Answers league questions in Discord from the published snapshot. Replies are
private unless the person chooses to share. It reads this repository
read-only and never writes to it. See
[discord_bot/README.md](discord_bot/README.md).

---

## Trade tool (`mouserat_trade-bud/`)

Positional surplus and need, mixed player and pick baskets, and live cap
impact for a proposed trade. Published at
**<https://benjamininja.github.io/Python-PowerBI-DynastyFantasyFootball/>**.

It ships as static files with no server: every number is computed ahead of
time from the snapshot, and the site rebuilds whenever new data lands on
`main`. See [mouserat_trade-bud/README.md](mouserat_trade-bud/README.md) and
[ADR-0012](docs/adr/0012-static-export-for-trade-bud.md).

---

## Checks

Three checks must pass before anything merges to `main`: `pii-scan` (no
owner personal data in a public repo), `tests` and `bot-tests`. Branch and
commit conventions are in [CONTRIBUTING.md](CONTRIBUTING.md). Design
decisions are recorded in [docs/adr/](docs/adr/).
