# Contributing & Branch Convention

## Branch structure

```
main        ← the only long-lived branch. Never commit directly.
<type>/<n>-<slug>  ← short-lived branch per change, e.g. feat/109-pick-legs, docs/readme-truth-up
```

Every change goes feature branch → pull request → `main`. One logical change
per pull request. Merge by squash and delete the branch
(`gh pr merge <n> --squash --delete-branch`).

**Allowlisted data-PR exception (2026-07-13, changed by #361):** the scheduled
pipeline (`scripts/run_pipeline.py`, via `run_weekly.ps1`) lands its
**machine-generated `data/*.parquet` refreshes by its own data PR**, gated by
the three required checks below, and merges that PR itself. Nothing is pushed to
`main`, no ruleset or repository setting is changed and nothing is bypassed.
This is deliberate and narrowly scoped: the orchestrator stages only the
tracked parquet of the Chains that passed their steps and Gate checks (ADR-0008
amendment, #115), restores a held Chain's parquet from `HEAD`, verifies every
staged path matches `data/*.parquet` (aborts otherwise) and skips the commit
entirely when nothing changed. It then commits to a new branch
`data/<date>-<phase>-wk<NN>` (with a `-2`, `-3` suffix when an earlier run's
branch still exists), rebases it on `origin/main`, pushes the branch and
opens a PR titled `data: pipeline refresh <date> (<phase>, wk <NN>)`. It polls
the PR for `pii-scan`, `tests` and `bot-tests` for up to 30 minutes, then merges
with `gh pr merge --rebase --delete-branch`. The run log reads `published` only
once the PR has merged, and its `snapshot_commit_sha` is the commit as it
landed on `main`. A failed check, a timeout or a refused merge leaves the PR
open, ends the run `failed` with the PR number in its error, and sends the
Discord notice. `--no-push` keeps its meaning: commit locally, push nothing,
open no PR. Manual-only tables (no `chain:` in `docs/data_model.yml`) and
brand-new parquet files are never staged by the pipeline — they reach `main` by
a PR of their own.
Code, notebooks, PBI, and docs always go feature branch → PR.
Watchpoint: parquet history growth — revisit (LFS/releases) only if repo size
becomes a problem.

## Required checks

A ruleset on `main` blocks the merge until all three pass:

| Check | Workflow | What it guards |
|---|---|---|
| `pii-scan` | `.github/workflows/pii-scan.yml` | No owner personal data in a public repo (`scripts/check_pii.py`) |
| `tests` | `.github/workflows/tests.yml` | The regression suite in `tests/` ([ADR-0008](docs/adr/0008-regression-testing-standard.md)) |
| `bot-tests` | `.github/workflows/tests.yml` | The Discord bot's tests |

## Session workflow

```bash
git fetch origin
git checkout -b docs/short-slug origin/main

# ... do the work ...

git add <files>
git commit -m "docs: #<ticket> short summary"
git push -u origin docs/short-slug
gh pr create --base main --title "docs: #<ticket> short summary" --body "..."
gh pr merge <n> --squash --delete-branch   # once the three checks pass
```

Agent sessions that run side by side each work in their own git worktree,
never in the main checkout.

## One-time environment setup

Wires the pre-commit hooks into `git commit`. Without this step,
`.pre-commit-config.yaml` exists but nothing runs it:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt   # pulls in pre-commit
.venv\Scripts\python.exe -m pre_commit install                # wires .git/hooks/pre-commit
```

The hooks: `check-pii` (owner personal data), `check-sources`
(`docs/sources.yml` against the notebooks), `check-data-model`
(`docs/data_model.yml` against the parquet files), `nbstripout` on the
owner-sheet notebook, and `check-in-hygiene`.

Verify with `.venv\Scripts\python.exe -m pre_commit run --all-files`.

## Commit message format

```
<type>: #<ticket> <short imperative summary (≤72 chars)>

- Bullet detail on what changed and why
- Reference any notebook numbers (03x, 04z, etc.)

Co-Authored-By: <the assisting model's attribution line, when one helped>
```

`<type>` is one of `feat`, `fix`, `docs`, `chore`, `refactor`, `test`. The
squash-merge title follows the same shape and becomes the commit on `main`.
Commits use the GitHub noreply author email, already set as this repo's
`user.email`.

## What lives in git

| Included | Excluded (see .gitignore) |
|---|---|
| `notebooks/*.ipynb`, `notebooks/*.py` | `data/.pw_profile/` (Playwright session, contains tokens) |
| `data/*.parquet` (the published snapshot) | `data/raw/`, `data/review/`, `data/outputs/` |
| `pbi/mouserat2/` (PBIP: TMDL model + PBIR report) | `**/.pbi/`, `*.abf`, auto date tables (Power BI local files) |
| `scripts/`, `tests/`, `discord_bot/`, `mouserat_trade-bud/` | `mouserat_trade-bud/_site/` (rebuilt on every deploy) |
| `docs/`, `.claude/memory/`, `.env.example` | `.env`, `*.env`, `.env.*`, `api_key.txt` (credentials) |
| | `.venv/`, `docs/reference/`, `.claude/settings*.json` |

`pbi/Mouserat2.pbix` is the legacy report. It is tracked but no longer
edited; the PBIP project is the source.

## How a schema change reaches the project

The registry (`docs/data_model.yml`) is the source; nothing edits the
database by hand. Run `scripts/generate_migrations.py` to write the new file
in `supabase/migrations/` and commit it with the registry change. On the PR,
the `validate` job in `.github/workflows/migrate.yml` applies every migration
to a throwaway Postgres and tests it. When the PR merges to `main`, the `push`
job runs `supabase db push` against the real project, using the Actions secret
`SUPABASE_MIGRATE_DB_URL` in the `etl` environment (limited to `main`). A
failed push run is not re-run: it goes to the planner with the log, because it
may have applied part of a migration.

### A column change on a published table

Adding, dropping or renaming a column of a table that has a
`data/<name>.parquet` needs the registry change and its migration in one PR,
and the code that fills the column; nothing else by hand. After the migration
is on the project, the next run exports each table from the database
(`export_published`). If the table's snapshot has other columns than the
registry, the export treats that as an intended change: the snapshot is
written in the registry's shape and the run log (`ops.etl_run_log.cadence`,
key `column_changes`) and the run summary list the column names added and
dropped, never a value. A rename shows as one dropped and one added name, as
the registry marks no rename. A frame that is not the registry's columns is
drift: the export raises, the run aborts and the database is reloaded from
the snapshot at HEAD. Between the merge and the next run the snapshot keeps
its old columns; a consumer that reads a new column waits for that run.

## Security rule

`data/.pw_profile` is gitignored. It holds the Playwright browser session for
the Fantrax headless scraper (`04a_fantrax_weekly_scrape.py`) and contained a
Mapbox token in the original commit history. That history was rewritten via
`git filter-repo` on 2026-05-30. **Never force-add this directory.**
`data/raw/` and `data/review/` gitignored. Not relevant for git repo.
