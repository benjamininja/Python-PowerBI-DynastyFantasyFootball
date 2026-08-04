# RESUME — trade-bud: #57 design resolved + adversarially reviewed (2026-08-04)

**Files touched this session**: `.claude/memory/MEMORY.md`,
`.claude/memory/mouserat-trade-bud.md`, `.claude/memory/RESUME.md`,
`mouserat_trade-bud/frontend/index.html` (all committed as `2807541`,
pushed to `docs/plan-update-ticket-56-closed`), then `PLAN.md` +
memory updates from this consolidation (**uncommitted**).

**Next task**: Build ticket [#57](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/57)
— edit `notebooks/04z_fantrax_crosswalk.ipynb` **cell id `253b3f55` only**,
per the approved plan at
`C:\Users\benha\.claude\plans\review-and-let-s-think-merry-bird.md`.

## No code changed this session — design only

#57 was a grilling ticket. The design is **approved but not implemented**;
no `.py`/`.ipynb` file was modified.

### What was decided

Restructure `04z`'s universe-extension section in cell `253b3f55` into one
`_scorer_extras(scorers, known)` helper (holding the 5-field mapping once:
`scorer_id`, `player_name`, `position_raw` via `re.sub(r"<[^>]+>", "", …)`,
`nfl_team`, `is_rookie`) fed by two collectors: the existing draft-results
glob, plus a **new** `fantrax_txn_history_*.json` collector walking every
row's `scorer` object. `_known` must be **recomputed from `fact_latest`
before each union**. Missing txn file → `02d`-style `[info] … (run 04t)`
message and continue.

The adversarial review reversed 3 answers the grilling itself had produced:
1. **warn-and-skip, not hard-fail** — `04z` is in `run_pipeline.py` (all 3
   phases), `04t` is not scheduled anywhere, `data/raw/` is gitignored, and
   a `raise` cascades via `needs` into `04v → 02d → 02e`.
2. **all txn rows, no view filter** — filtering on `filterSettings.view`
   costs more code than not filtering; `02d` walks all rows too.
3. **shared helper, not a second block** — cell 3's `_known` is computed
   *before* the draft concat, so a copied block re-appends `03ccz`, making
   `scorer_id` non-unique → cell 6 `.map()` raises `InvalidIndexError`
   *after* cell 5 already wrote the parquet.

Use `02d`'s season-agnostic glob `fantrax_txn_history_*.json` (mtime-sorted),
**not** `{CFG.snapshot_season}` — the latter breaks at season rollover.

### Exact commands to run next

```powershell
git checkout -b fix/04z-claim-only-match-universe
# edit notebooks/04z_fantrax_crosswalk.ipynb cell 253b3f55
.\run.ps1 notebooks\04z_fantrax_crosswalk.ipynb
.\run.ps1 notebooks\02d_fact_roster_transactions.py
.\run.ps1 -m pytest tests\
```

**Acceptance criterion** (the real one — downstream, not the notebook):
null-identity rows in `dim_roster_asset` / `fact_roster_transactions` go
**1 → 0**. Also assert `xwalk["scorer_id"].is_unique` (guards the finding-3
bug) and that `dim_fantrax_crosswalk` has exactly one `04cc5` row with
`gsis_id == "00-0033897"`, `match_method == "exact"`. Verify graceful
degradation by temporarily moving `data/raw/fantrax_txn_history_2026.json`
aside and confirming `04z` completes rather than raising.

## Loose ends, not blocking

- **Uncommitted**: `PLAN.md` + the memory files updated by this
  consolidation. Commit before or alongside the #57 build.
- The Spanish strings in `index.html` ("El Otro Perfil" / "El Otro Equipo")
  were **confirmed intentional** by Ben this session and are committed in
  `2807541` — no longer a loose end.
- Untracked `.agents/` and `GEMINI.md` are from another CLI tool; left
  alone deliberately, out of every commit.
- **New idea, needs its own grilling**: add/drop-count profile signal
  (`trade_count`-parallel roster-churn metric off the same `CLAIM_DROP`
  rows). Window, CLAIM-vs-DROP handling, and target `build_profile()` field
  all undecided. Recorded in `mouserat-trade-bud.md` + `PLAN.md`.
