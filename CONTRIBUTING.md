# Contributing & Branch Convention

## Branch structure

```
main        ← the only long-lived branch. Never commit directly (one exception below).
<type>/<n>-<slug>  ← short-lived branch per change, e.g. feat/109-pick-legs, docs/readme-truth-up
```

Every change goes feature branch → pull request → `main`. One logical change
per pull request. Merge by squash and delete the branch
(`gh pr merge <n> --squash --delete-branch`).

**Allowlisted data-commit exception (2026-07-13):** the scheduled pipeline
(`scripts/run_pipeline.py`, via `run_weekly.ps1`) commits **machine-generated
`data/*.parquet` refreshes directly to `main`**. This is deliberate and
narrowly scoped: the orchestrator stages only the tracked parquet of the
Chains that passed their steps and Gate checks (ADR-0008 amendment, #115),
restores a held Chain's parquet from `HEAD`, verifies every staged path
matches `data/*.parquet` (aborts otherwise), skips the commit entirely when
nothing changed, and rebases on `origin/main` before pushing. Manual-only
tables (no `chain:` in `docs/data_model.yml`) and brand-new parquet files are
never staged by the pipeline — they reach `main` by PR.
Code, notebooks, PBI, and docs still always go feature branch → PR.
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

## Security rule

`data/.pw_profile` is gitignored. It holds the Playwright browser session for
the Fantrax headless scraper (`04a_fantrax_weekly_scrape.py`) and contained a
Mapbox token in the original commit history. That history was rewritten via
`git filter-repo` on 2026-05-30. **Never force-add this directory.**
`data/raw/` and `data/review/` gitignored. Not relevant for git repo.
