# Contributing & Branch Convention

## Branch structure

```
main   ← production / stable. Never commit directly.
dev    ← active development. All session work lands here.
```

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

## Commit message format

```
<short imperative summary (≤72 chars)>

- Bullet detail on what changed and why
- Reference any notebook numbers (08e, 09a, etc.)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

## What lives in git

| Included | Excluded (see .gitignore) |
|---|---|
| `notebooks/*.ipynb` | `data/.pw_profile/` (Playwright session — contains tokens) |
| `notebooks/*.py` | `.env`, `api_key.txt` (credentials) |
| `data/*.parquet` | `.venv/` (Python environment) |
| `data/raw/*.json` | `__pycache__/`, `.ipynb_checkpoints/` |
| `data/review/*.csv` | |
| `data/*.xlsx` | |
| `pbi/*.pbix` | |

## Security rule

`data/.pw_profile` is gitignored. It holds the Playwright browser session for
the Fantrax headless scraper (`09_fantrax_weekly_scrape.py`) and contained a
Mapbox token in the original commit history. That history was rewritten via
`git filter-repo` on 2026-05-30. **Never force-add this directory.**
