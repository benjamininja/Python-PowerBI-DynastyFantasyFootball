# mouserat_trade-bud ships as precomputed static JSON, not a hosted backend

- Status: accepted
- Date: 2026-07-27
- Scope: `mouserat_trade-bud/`, `.github/workflows/pages.yml` (this repo's
  first GitHub Action)

## Context

The trade tool ran only on `localhost:8420` — a static `frontend/index.html`
talking to a local FastAPI backend that reads this repo's parquet. Sharing it
with the league means giving them a URL.

The reference app this project was adapted from,
[hod-decision-engine](https://github.com/Spunkylysis/hod-decision-engine), is
already hosted: GitHub Pages (legacy branch build) serving a single 176KB
`index.html` that queries Supabase client-side, with a separate ETL repo doing
a weekly TRUNCATE-reload. The two frontends are architecturally the same thing.
**The only real difference is where the compute lives** — theirs is SQL views
inside the database, so a static page can reach it; ours is Python/pandas in a
FastAPI process, which Pages cannot run. That is the entire porting problem.

What made the third option viable, established by inspection rather than
assumed:

- **Every GET is a pure function of committed parquet.** `/teams`, all 28
  `/assets`, all 56 `/profile` variants, `/positional-strength/league` — same
  answer on every request until the pipeline reruns. No writes, no auth, no
  per-user state.
- **The data is tiny.** Every endpoint is a projection over ~1300 rows; the
  full export is 411 KB of JSON, ~12 KB per team's assets, and the UI loads two
  teams at a time.
- **All required parquet are git-tracked**, so CI can build from a plain
  checkout with no scraping and no secrets.
- **`/trade/evaluate` is the only endpoint taking user input, and moving it
  client-side duplicates no valuation logic.** `routers/assets.py` already sets
  each asset's `value` by calling the very function `/trade/evaluate` sums, so
  the values the client holds are the values the endpoint summed. What moves to
  JS is the summation — about six lines.

## Decision

**Precompute every endpoint to static JSON at build time and serve the whole
app from GitHub Pages. No server, no database, no secrets in production.**

`export_static.py` calls the existing router functions directly and writes
their return values. It reimplements nothing: `positional_strength.py`,
`profiles.py`, `pick_value.py`, `pareto.py` and `routers/*.py` stay the single
source of truth for every number that reaches the browser.

The FastAPI backend is kept as the local dev server and as the exporter's
source of truth. `main.py`'s docstring claim that it is never deployed stays
true.

## Alternatives considered

- **Mirror the reference app's Supabase design.** Rejected. Supabase's value is
  a live queryable database with auth, and we need neither half. It would mean
  rewriting `positional_strength.py`, `profiles.py`, `pick_value.py` and
  `pareto.py` as SQL views, plus a new secret and an external dependency that
  pauses on inactivity — to serve answers that are identical every time until
  the next pipeline run.
- **Host FastAPI on Railway** alongside the Discord bot (the guess recorded in
  the plan's earlier "Deployment / Discord sharing" note). Rejected: zero
  backend changes, but it is a live server recomputing constants, and the app
  dies whenever it does.

## Consequences

**The site refreshes on the pipeline's cadence for free.** `run_pipeline.py`
already commits refreshed `data/*.parquet` to `main`, and the workflow triggers
on that path. Worth confirming after the first real pipeline run rather than
assuming.

**Nothing generated is committed** (`_site/` is gitignored). The site rebuilds
from parquet on every deploy, so it cannot drift from the data the way a
checked-in artifact could.

**Enabling Pages was a manual repo-settings step** — build type "GitHub
Actions", done 2026-07-27. The workflow cannot enable it itself.

**The exporter memoizes three `data_access` readers with `lru_cache`, and that
must stay inside the exporter.** It is a ~5x speedup (29s -> 6s for a full
export, byte-identical payloads) that is only safe in a one-shot process; in
the long-lived dev server it would serve stale data after a pipeline run until
restarted.

**Client-side checks are affordances, not controls.** The same-conference trade
rule is re-checked in JS on the static site. There is no trust boundary left to
defend — it is a read-only calculator with no writes and no server.

**The site is public.** This repo is public, so every number shown is already
published as parquet; Pages changes discoverability, not exposure. A `noindex`
tag keeps it out of search results while staying shareable by link.

## The bug this round's verification caught

Worth recording, because the export ran clean and looked correct.

Diffing exported JSON against the live API failed **27 of 86 checks**. The
payloads carry genuine NaNs (a player with no contract value, an unnamed roster
copy); the API renders them `null`, but `json.dumps` writes a bare `NaN`
literal, which is **not valid JSON**. `JSON.parse` rejects the *entire file*,
so one missing contract value would have blanked a whole team — 27 of 28 teams
affected, silently.

Fixed with a recursive non-finite sanitizer plus `allow_nan=False`, so a future
miss is a hard error rather than silent invalid output.

The generalizable part is the verification, not the bug: **Python's `json.load`
accepts `NaN` by default**, so "I loaded every generated file and they all
parsed" passes on exactly this defect. Browser-strict checking needs
`parse_constant` raising. Match verification to the real consumer's strictness;
a permissive re-parse in the producing language proves nothing.
