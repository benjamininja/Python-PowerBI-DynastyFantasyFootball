# mouserat_trade-bud

Dynasty trade-diagnostic tool for the league. Pick your team and a
counterparty, read each side's positional surplus/need, build a mixed
player+pick basket, and see the Pareto asymmetry and cap impact update live.

Published at
**<https://benjamininja.github.io/Python-PowerBI-DynastyFantasyFootball/>**

Adapted from [hod-decision-engine](https://github.com/Spunkylysis/hod-decision-engine)
(a baseball keeper-league app) but re-grounded in this league's actual domain:
points-based IDP dynasty football, draft picks as first-class tradeable assets,
positional strength instead of rotisserie category gaps. See
[ADR-0012](../docs/adr/0012-static-export-for-trade-bud.md) for the hosting
decision and [PLAN.md](../PLAN.md) for the design log.

## Two ways it runs, one source of truth

The same code serves both. **The backend is a dev tool; production has no
server at all.**

| | Local dev | Published site |
|---|---|---|
| Serves | `uvicorn main:app` on `:8420` | GitHub Pages, static files |
| Data | reads `data/*.parquet` per request | precomputed JSON, built in CI |
| Freshness | live, every request | as of the last deploy (`meta.json`) |
| Secrets | none | none |

`export_static.py` bridges them by **calling the router functions directly**
and writing their return values as JSON. It reimplements nothing —
`positional_strength.py`, `profiles.py`, `pick_value.py`, `pareto.py` and
`routers/*.py` remain the single source of truth for every number that reaches
the browser (the same don't-copy-paste rule `etl_helpers.py` follows).

## Layout

```
backend/            FastAPI app - local dev server + the exporter's source of truth
  data_access.py      parquet readers; imports discord_bot/capmath.py for cap logic
  positional_strength.py  per-team, per-position rank/gap vs the league
  profiles.py         stance / risk / trade-activity inference + confidence tiers
  pick_value.py       draft-pick valuation off dim_pick_value_curve
  pareto.py           asset valuation + trade asymmetry math
  routers/            teams, assets, positional, trade
frontend/index.html Single dependency-free page. No build step, no framework.
export_static.py    Renders every GET endpoint to JSON; copies index.html
_site/              Build output. Gitignored - never committed.
```

## Running it

**Static site (what users get):**

```bash
python mouserat_trade-bud/export_static.py --out mouserat_trade-bud/_site
python -m http.server --directory mouserat_trade-bud/_site 8500
```

Then open <http://127.0.0.1:8500/>. It **must** be served over HTTP — opening
`_site/index.html` as a `file://` path fails, because the relative `data/`
fetches are blocked.

**Backend dev server** (for changing endpoint logic):

```bash
cd mouserat_trade-bud/backend
uvicorn main:app --port 8420
```

There is no `--reload` in that invocation, so restart it after editing a `.py`.
Note the frontend no longer talks to it — it reads static JSON — so after a
backend change, re-run the exporter to see the effect in the browser.

## Deployment

`.github/workflows/pages.yml` rebuilds and deploys on every push to `main`
touching `data/**.parquet`, `mouserat_trade-bud/**`, or the workflow itself,
plus manual `workflow_dispatch`. A plain checkout is a complete build
environment: no secrets, no database, no scraping.

Because `scripts/run_pipeline.py` already commits refreshed `data/*.parquet`
to `main` on its scheduled run, **the site refreshes on the pipeline's cadence
for free** — no extra scheduling.

Nothing generated is committed. The site is rebuilt from parquet on every
deploy, so it cannot drift from the data the way a checked-in artifact could.

## Things that will bite you

- **NaN is not valid JSON.** These payloads carry real NaNs (a player with no
  contract value). `json.dumps` writes a bare `NaN` literal, which
  `JSON.parse` rejects *wholesale* — one missing value blanks a whole team.
  `_nulls_for_nan()` plus `allow_nan=False` handle it. Validate generated JSON
  the way a browser parses it; Python's `json.load` **accepts** `NaN` and will
  happily pass a file no browser can read.
- **Don't move the exporter's `lru_cache` into `data_access.py`.** It is a
  ~5x speedup that is only safe in a one-shot process. In the long-lived dev
  server it would serve stale data after a pipeline run until restarted.
- **The frontend's whole network layer is one function**, `api(path)`. All
  call sites route through it; keep it that way.
- **Trade math lives in two places on purpose.** Valuation is Python
  (`pareto.asset_value`, already baked into each asset's `value` field);
  only the ~6-line summation is duplicated in JS as `evaluateTradeLocal()`,
  because it takes live user input. Change one, check the other — the JS
  points at `backend/pareto.py` in a comment.
- **The same-conference rule is checked client-side only** on the static
  site. That is a UX affordance, not a control: the published app is a
  read-only calculator with no writes and no server to defend.

## Privacy

The site is public — this repo is public, so every number it shows is already
published as parquet. Pages changes *discoverability*, not exposure. A
`<meta name="robots" content="noindex">` keeps it out of search results while
staying shareable by link; delete that one line to make it fully public.
