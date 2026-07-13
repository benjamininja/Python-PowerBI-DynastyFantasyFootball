# Contributing & Branch Convention

## Branch structure

```
main   ← production / stable. Never commit directly (one exception below).
dev    ← active development. All session work lands here.
```

**Allowlisted data-commit exception (2026-07-13):** the scheduled pipeline
(`scripts/run_pipeline.py`, via `run_weekly.ps1`) commits **machine-generated
`data/*.parquet` refreshes directly to `main`**. This is deliberate and
narrowly scoped: the orchestrator stages only the `data/*.parquet` pathspec,
verifies every staged path matches it (aborts otherwise), skips the commit
entirely when nothing changed, and rebases on `origin/main` before pushing.
Code, notebooks, PBI, and docs still always go feature branch → PR.
Watchpoint: parquet history growth — revisit (LFS/releases) only if repo size
becomes a problem.

PRs flow `dev → main`. Claude Code sessions work on `dev` (or a short-lived
`feature/*` branch off `dev` for isolated tasks).

## Session workflow

```bash
# Start of session — ensure you're on dev and up to date
git checkout dev
git pull origin dev

# ... do work ...

# End of session — stage, commit, push, open PR
git add <files>
git commit -m "descriptive message"
git push origin dev
gh pr create --base main --head dev --draft --title "..." --body "..."
```

## One-time environment setup

Wires the ADR-0008 `check_sources.py` pre-commit gate into `git commit` —
without this step, `.pre-commit-config.yaml` exists but nothing runs it:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt   # pulls in pre-commit
.venv\Scripts\python.exe -m pre_commit install                # wires .git/hooks/pre-commit
```

Verify with `.venv\Scripts\python.exe -m pre_commit run --all-files`.

## Commit message format

```
<short imperative summary (≤72 chars)>

- Bullet detail on what changed and why
- Reference any notebook numbers (03x, 04z, etc.)

Co-Authored-By: Claude Sonnet 4.6; Opus 4.8 <noreply@anthropic.com>
```

## What lives in git

| Included | Excluded (see .gitignore) |
|---|---|
| `notebooks/*.ipynb` | `data/.pw_profile/` (Playwright session — contains tokens) |
| `notebooks/*.py` | `.env`, `api_key.txt` (credentials) |
| `data/*.parquet` | `.venv/` (Python environment) |
| `data/*.xlsx` | |
| `pbi/*.pbix` | |

## Security rule

`data/.pw_profile` is gitignored. It holds the Playwright browser session for
the Fantrax headless scraper (`04a_fantrax_weekly_scrape.py`) and contained a
Mapbox token in the original commit history. That history was rewritten via
`git filter-repo` on 2026-05-30. **Never force-add this directory.**
`data/raw/` and `data/review/` gitignored. Not relevant for git repo.
