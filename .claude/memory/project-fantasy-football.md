# Fantasy Football League — Project Context

## Branch Convention

- `main` — stable/production. **Never commit directly.**
- Work on a **feature branch → `main` via PR**. `gh pr create --base main --head <branch>`; **squash-merge** with a body-of-work description, `--delete-branch`. Merged so far: PR #3 (dynasty rankings), #4 (semantic-model PascalCase + measures + AI metadata), #5 (notebooks/data write-leak fix), #6 (Dim_School SchoolAbbr + new report page), #7 (discord_bot scaffold), #8 (untrack notebooks/.env + harden .env ignore), #9 (dynasty single-EAV refactor + project docs/memory + ADR-0001..0005), #10 (discord_bot hardening on the EAV schema), #16 (discord_bot adp/player/cap/roster expansion, merged 2026-07-11). One logical change per PR (e.g. model vs ETL split into #4/#5; refactor vs bot split into #9/#10 — #9 merged first since the bot reads its schema).
- **`CONTRIBUTING.md` describes a `dev` branch that doesn't exist** (no local or remote `dev` — checked 2026-07-11). Actual practice, matching recent PR history: feature branch off `main` directly, PR to `main`, squash-merge, delete branch. Follow the actual practice, not the stale doc.
- **Current branch (2026-07-11): `data-2026-draft-cap-update`**, off `main` (`b89671c`). Scope: 2026 startup-draft ingest (both divisions), $500M→$300M cap change, `Fact_FantasyTeams`/`Dim_FantasyTeams` cap-consistency fix, the `04z` crosswalk universe fix, `discord_bot/capmath.py`. The pending singular/plural table rename (`Dim_FantasyTeams`→`Dim_FantasyTeam` etc., see powerbi-semantic-model.md) is agreed to land as a **separate commit on this same branch**, not yet done.
- `gh` CLI on PATH (v2.93, winget). Commit only when asked; leave unrelated working-tree changes (e.g. `pbi/Mouserat2.pbix`, untracked `skills/`, `workspace/`) out unless told otherwise.
- **Push rule (GitHub email privacy ON)**: commits must use the noreply author email `38588919+benjamininja@users.noreply.github.com` or `git push` is rejected ("push declined due to email privacy restrictions"). Repo `user.email` is set to it; if a commit slips through with `benjamin.hanna77@gmail.com`, `git commit --amend --reset-author` before pushing.

## Power BI layer

- Beyond the binary `pbi/Mouserat2.pbix`, there is now a **PBIP project** (TMDL model + PBIR report) at `pbi/mouserat2/` — **see [powerbi-semantic-model.md](powerbi-semantic-model.md)** for naming convention, rename-cascade, dynasty measures, and Prep-for-AI gates. Model table/column names are PascalCase; parquet/ETL stay snake_case (bridged by `sourceColumn`).

## Discord bot layer

- **`discord_bot/`** (PR #7) — a `discord.py` command bot that fetches dynasty parquet from this repo via the **authenticated GitHub contents API** and posts a per-position rankings board. v1 = `/rankings` (hybrid slash+prefix). Authored from the **`discord-bot-github-fetch`** skill (`~/.claude/skills/`) — that skill is the source of truth for architecture, config, security gates, Railway deploy, first-run setup, and triage; keep it in sync.
- **PR #16 (merged 2026-07-11)**: expanded to `/adp`, `/player`, `/cap`, `/roster` (same cog-per-command shape as `/rankings`). `cap.py`/`roster.py` share cap math via `discord_bot/capmath.py` (added 2026-07-11, see "Cap architecture" below) instead of reading a cached `dim_fantasy_teams` column.
- **Status (merged to main 2026-06-14, PR #10)**: scaffolded, hardened (code-review + simplify), and **live** — bot `DeadMoney-LiveData#6589` runs locally and `/rankings` answers in the guild. Hardening (config guild-id guard, null-safe rendering, `asyncio.to_thread` fetch, `len(embed)` cap, fail-fast startup, `railway.json`, `.botvenv/` ignore) **plus the `rankings.py` rewrite onto the single-EAV schema** (reads `fact_dynasty_ranking_metrics` + `dim_nfl_players`, joins on `gsis_id`, groups by `position_group`, re-ranks 1..N — ADR-0002) are now on `main`. Local test venv = `discord_bot/.botvenv/` (gitignored, untracked).
- **Privacy = standing policy (2026-06-08)**: bot replies are **private by default**, public **only on explicit per-invocation opt-in** — every command must follow this. Ephemeral is interaction-only, so: slash defers `ephemeral=not share` with both a `share:true` option and a requester-restricted "Post publicly" button (`ShareView`); prefix can't be ephemeral, so in a public channel it **DMs the requester** (📬 react; redirect + no data if DMs closed), and replies in-place when already in a DM. Closed-DM/error paths never leak data; generic user error + `log.exception` server-side. Routing lives in `_deliver_embeds`/`_deliver_text` for reuse.
- **Data caveat baked into the bot**: no single (format, source) spans all positions — `SF`/`TEPP` = offense (KTC primary), `IDP` = defense (FantasyPros only; KTC has no IDP). So `/rankings` is **format-scoped** and auto-picks the primary source per format.
- **First-run is gated by Discord setup, not code** (the actual blockers we hit): invite must use **Guild Install + `bot` + `applications.commands`** scopes (missing `applications.commands` → `403 50001 Missing Access` on slash sync though login succeeds); **Message Content intent** must be ON (else `PrivilegedIntentsRequired`); `DISCORD_GUILD_ID` must match the server. Full triage in the skill's `references/railway-deploy.md`.
- **Least-privilege invite permissions = integer `85056`** — exactly five: View Channels, Send Messages, Embed Links, Read Message History, Add Reactions (the 📬 react). **Never Administrator/Manage\***; `Use Slash Commands` permission not needed (scope handles it); DM path needs no guild perm but per-channel overrides still win.
- **Crash-loop guards** (Railway): bot fails fast with `SystemExit(1)` on `LoginFailure`/`PrivilegedIntentsRequired` (in `main`) and sync `Forbidden` (in `setup_hook`, not wrapped around the whole gateway); `railway.json` bounds restarts (`ON_FAILURE`, `restartPolicyMaxRetries: 5`). `railway.json` is the **single** start-command source — no `Procfile` (Railway silently overrides it). Self-trigger loop is non-issue: `process_commands` ignores bot authors.
- **Local testing**: can't run a slash command from an editor — monkeypatch `rankings.fetch_parquet` to read the local parquet, build embeds, assert Discord limits, exercise error paths; one live authenticated fetch confirms the network path. Live command test = `python bot.py` + type `/rankings` in the Discord client.
- **Hosting**: Railway worker (deploy from GitHub, `rootDirectory: discord_bot`, secrets as service variables). The `use-railway` plugin/skill drives the Railway ops. Bot config lives in gitignored `discord_bot/.env` locally (Discord bot token + least-priv GitHub PAT, Contents read-only). **Not yet deployed to Railway** (running locally only as of 2026-06-08).

## Secret hygiene (remediated 2026-06-08)

- `notebooks/.env` had been **tracked since 66b79d8** (`*.env` only ignores *untracked* files). Untracked via `git rm --cached` (PR #8); local copy kept. `.gitignore` hardened so every `.env` variant is ignored (`.env`, `*.env`, `.env.*`) while `.env.example` stays tracked (`!**/.env.example`).
- **Credential rotation: DONE** (user, 2026-06-08) and `.env` files updated. The newer Discord/GitHub keys were never committed (working-tree only). Only the `git filter-repo` history scrub of `notebooks/.env` may remain outstanding (user-owned; low urgency since creds are rotated).

## Overview

Dynasty fantasy football league. Ben is the commissioner and data engineer.
Project path: `C:\Users\benha\OneDrive\Documents\GitHub\Python-PowerBI-DynastyFantasyFootball\`
Data path: `C:\Users\benha\OneDrive\Documents\GitHub\Python-PowerBI-DynastyFantasyFootball\data\`
Power BI file: `pbi\Mouserat2.pbix`

## League Structure

- 28 teams, 2 conferences, 14 teams each
- **Riddell conference** = A (A01–A14)
- **Wilson conference** = B (B01–B14)
- Salary cap: $300,000,000 per team
- FA minimum salary: $2,000,000
- Draft year in active development: 2026

## Team Owner Registry

Google Sheet (publicly viewable):
- Sheet ID: `1Fiz_KHH5bexSAHIfL0uVIqgHU6jTgnOmDs86kjR8TZc`
- GID: `178660131`
- Columns: Division, Team ID, Team Name, Team Abbreviation, Manager Email, Other Manager Email
- Team IDs match `team_key` format (A01, B01, etc.)
- Ben's team: A10 "Pac & Big L Deadly Combo" (benjaninja77@gmail.com)

## Ranking Sources Registry

Same Google Sheet, GID `1580509551`. Sources split across notebooks 03a–03x:

### Scraped Sources (03a–03d)

**FantasyPros** (03a) — `ecrData` JSON in page HTML, no Selenium needed
- `rank_ecr` → `global_rank`, `rank_ave` → `grade`, `pos_rank` → `positional_rank`
- PPR + Superflex only. IDP removed from 03a (see manual sources below).

| Source key | URL slug |
|---|---|
| `FantasyPros_PPR` | `dynasty-rookies-overall.php` |
| `FantasyPros_Superflex` | `dynasty-rookies-superflex.php` |

**WalterFootball** (03b) — `<b>` tags in `<article>`, positional rank only
**KeepTradeCut** (03c) — `KTC_Consensus`
**DraftSharks** (03d) — `<ol><li>` list, top 90 free tier

### Manual Extraction Sources (03x)

File: `data/raw/RookieRankings_2026_ManualExtraction.xlsx` (gitignored `data/raw/`) — each sheet = one source.

| Sheet | source_name | source_site | phase | rows |
|---|---|---|---|---|
| rotoballer | RotoBaller | RotoBaller | post_draft | 100 |
| mystery_iono | mystery_iono | mystery_iono | post_draft | 48 |
| dynastyleaguefootball | DynastyLeagueFootball | DynastyLeagueFootball | pre_combine | 60 |
| fantasycalc | FantasyCalc | FantasyCalc | post_draft | 70 |
| fantasypros_idp | FantasyPros_IDP | FantasyPros | post_draft | 109 |

**FantasyPros IDP note**: `dynasty-rookies-idp.php` raw HTML `ecrData` serves a
full veteran draft board (Type: "Draft", 426 offensive players). The actual defensive
rookie table renders client-side only. Must be manually extracted into the Excel sheet.

## Contract Types (dim_contract)

All 10 rows unique — `contract_id` is the PK:

| contract_id   | salary_type           | years | cap_hit_pct | guaranteed |
|---------------|-----------------------|-------|-------------|------------|
| 1st           | Fixed Salary          | 1/3   | 50%         | Yes        |
| 2nd           | Fixed Salary          | 2/3   | 40%         | Yes        |
| 3rd           | Fixed Salary          | 3/3   | 0%          | No         |
| 4th           | New Value             | 1/3   | 50%         | Yes        |
| 5th           | New Value             | 2/3   | 40%         | Yes        |
| 6th           | New Value             | 3/3   | 0%          | No         |
| Franchise Tag | New Salary            | 1     | 50%         | Yes        |
| X             | Fixed Salary          | 1     | 50%         | No         |
| Minor         | Fixed Salary          | 1     | 0%          | No (exempt)|
| FA            | League Minimum Salary | 1     | 0%          | No (exempt)|

`contract_year` (1/2/3) tracks position within term for ETL advancement.

## Notebook Inventory

All ETL notebooks `.ipynb` in `notebooks/`. Storage: parquet everywhere; review files CSV in `data/review/`.
**Naming convention (formalized 2026-06-06)**: `NN<letter>_name` — group prefix is the project pattern: `01`=core **dimension** tables, `02`=core **fact** tables, `03`=**rookie-ranking** tables/processes, `04`=**dynasty-ranking** tables/processes (incl. Fantrax). Letter = order within group; `x`/`y`/`z` reserved for late-stage / apply / resolver steps. `notebooks/README.md` is the source of truth.
Exception: `04a_fantrax_weekly_scrape.py` is a `.py` script (scheduled headless-browser scrape — not a notebook).
Shared helpers/config live in `notebooks/etl_helpers.py` (imported, not copied). Each folder has a README (`data/`, `notebooks/`, `pbi/`).
**Launch `.py` scripts via `.\run.ps1 <script.py>` from repo root** (added 2026-06-14; new file `run.ps1`) — it pins `.venv\Scripts\python.exe` and passes extra args through. VS Code "Run Python File" / a bare `python x.py` select **anaconda base** (no `playwright` → `ModuleNotFoundError`; broken `pyarrow` → "Repetition level histogram size mismatch"). Repo has two venvs (`venv\` and `.venv\`); the launcher pins the right one. This is the recurring "won't run" trap — not a venv defect.
**Dependencies (added 2026-07-11)**: root `requirements.txt` is the `.venv` source of truth (`pip install -r requirements.txt`) — curated/loosely-pinned like `discord_bot/requirements.txt`, not a full freeze. Includes `nbformat`/`nbclient`/`nbconvert` (headless notebook execution only — `.venv\Scripts\python.exe -m nbconvert --to notebook --execute --inplace <nb>`, **not** `python -m jupyter nbconvert`, which can dispatch to a different interpreter via PATH) and `nflreadpy`. `openpyxl` is documented there but was still missing from `.venv` as of 2026-07-11 (needed by `03x`/`04x`) — install before running those.

| # | Notebook | Primary output |
|---|---|---|
| 01a | `01a_dim_rookie_prospect.ipynb` | `dim_position`, `dim_school`, `dim_rookie_prospect` |
| 01b | `01b_dim_contract_seed.ipynb` | `dim_contract` |
| 01c | `01c_dim_fantasy_teams_seed.ipynb` | `dim_fantasy_teams` (from Google Sheet) |
| 01d | `01d_dim_nfl_teams_seed.ipynb` | `dim_nfl_teams` |
| 01e | `01e_dim_nfl_players_seed.ipynb` | `dim_nfl_players` (central player registry) |
| 02a | `02a_fact_nfl_combine_pro_day_metrics.ipynb` | `fact_nfl_combine_pro_day_metrics` (all seasons) |
| 02b | `02b_fact_fantasy_teams_seed.ipynb` | `fact_fantasy_teams` (schema seed) |
| 02c | `02c_fact_rookie_rankings_seed.ipynb` | `fact_rookie_rankings` (schema seed only) |
| 02d | `02d_fact_roster_transactions.py` | `fact_roster_transactions` (ledger, replay from `04w` draft-results JSON) + `dim_roster_asset` + `dim_draft_pick` |
| 02e | `02e_fact_fantasy_teams_derive.py` | `fact_fantasy_teams` (ledger replay → current roster). Since 2026-07-11 this is the **only** location for contract/salary/cap-hit data — no longer rolls anything up into `dim_fantasy_teams` (see "Cap architecture" below) |
| 03a | `03a_fantasypros_rankings.ipynb` | FantasyPros PPR + Superflex (scraped) |
| 03b | `03b_walterfootball_rankings.ipynb` | WalterFootball positional ranks (scraped) |
| 03c | `03c_ktc_rankings.ipynb` | KeepTradeCut consensus (scraped) |
| 03d | `03d_draftsharks_rankings.ipynb` | DraftSharks top 90 (scraped) |
| 03x | `03x_manual_rankings.ipynb` | RotoBaller, mystery_iono, DLF, FantasyCalc, FP IDP (from Excel) |
| 03y | `03y_dim_player_alias.ipynb` | `dim_player_alias` (persistent name→player_key decisions); backfills from applied reviews |
| 03z | `03z_apply_fuzzy_review.ipynb` | Applies `review_fuzzy_matches.csv`; appends decisions to `dim_player_alias` |
| 04a | `04a_fantrax_weekly_scrape.py` | `fact_fantrax_adp` (Fantrax projection board + season-actuals backfill; Playwright scrape) |
| 04b | `04b_ktc_dynasty_rankings.ipynb` | `fact_dynasty_ranking_metrics` + `dim_dynasty_crosswalk` (KTC, embedded-HTML scrape) |
| 04c | `04c_dim_dynasty_metric.ipynb` | `dim_dynasty_metric` (metric_key index: label/group/order/direction/**source_name**; matrix column axis) |
| 04w | `04w_fantrax_draft_results.py` | Raw `fantrax_draftresults_{season}_{divisionId}.json` per division (live startup-draft capture via Playwright, reuses `04a`'s auth). E-step only — `02d` does the parse/identity resolution. Re-run during the live draft to refresh |
| 04x | `04x_manual_dynasty_rankings.ipynb` | ↑ metrics fact ← DynastySharks (SF/TEPP) + FantasyPros (SF/IDP) manual Excel |
| 04y | `04y_composite_dynasty_metrics.ipynb` | `composite_adp` + `sources_count` (cross-source percentile blend of `ktc_adp`/`ds_adp`; Composite partition; runs after 04b+04x) |
| 04z | `04z_fantrax_crosswalk.ipynb` | `dim_fantrax_crosswalk` (scorer_id -> gsis_id/player_key); back-fills fact FKs. **Universe extended 2026-07-11**: unions in scorer_ids from `04w`'s draft-results JSON, not just `fact_fantrax_adp` — draft-only picks (deep bench/IDP/unranked rookies) never appear in ADP and were silently falling through to null gsis_id/player_key downstream (`dim_roster_asset`, `02d`) without ever hitting the review CSV, since they were outside the crosswalk's old input universe entirely |

## Fantrax Weekly Scrape (notebook 04a)

Scheduled headless-browser pull of the Fantrax draft-ranking board for league `v744203wmmvjqzv6`.
- **Auth**: Playwright persistent context (`data/.pw_profile`); creds from gitignored `.env` (`FANTRAX_EMAIL`/`FANTRAX_PASSWORD`). Self-heals: POST `getDraftRanks` → if response carries `WARNING_NOT_LOGGED_IN`, log in (Angular Material form: `input[formcontrolname='email'|'password']`, submit via Enter) and retry once. HTTP 200 ≠ success — must check the body's `pageError.code`.
- **Login form note**: no `type=email` / `placeholder` attrs; SPA never reaches `networkidle` (use wait-for-URL-off-`/login`).
- **Endpoint**: `POST https://www.fantrax.com/fxpa/req?leagueId=...`, method `getDraftRanks`. Response `responses[0].data.fullStats` = full ~8600 scorer universe; the real board = the ~280 rows with non-null ADP (`statsAll[4]`). `statsAll` order: `[bye, salary, fpts, fptsPerGame, adp, percentOwned]`.
- **Columns added 2026-06-06**: `overall_rank` (Fantrax "Rk" = full-pool rank by FPts, computed; validated vs `getPlayerStats` `scorer.rank`), `fpts` (renamed from `score`) + `fpts_per_game`, `age` (from `dim_nfl_players.birth_date` via crosswalk gsis_id). **Phase-aware** (`resolve_season_or_projection`): preseason → season projection (`PROJECTION_0_23l_SEASON`, real FPts), in-season → YTD actuals (`SEASON_23l_YEAR_TO_DATE`). `load_fact` is now replace-by-`(season, week)`.
- **GP / per-stat splits** are NOT on the draft-ranks board — only on the Players grid (`getPlayerStats`). **Wired in 2026-06-06** as a second snapshot type via `backfill_player_stats(CFG, season=2025, week="YTD")`: pulls completed-season actuals (incl. real GP) into the SAME fact as a counterpoint to projections. Must pull per position group (`FOOTBALL_OFFENSE`+`FOOTBALL_DEFENSE`, 18 pages total) — the `ALL` group drops GP. First 2025 YTD load = 2,282 active-roster rows; `games_played` null on board rows, populated here. New scorer_ids → `gsis_id` ~28% null until 04z re-runs.
- **E+T+L in one file**: scrape → write raw JSON (`data/raw/fantrax_draftranks_{season}_wk{NN}.json`, audit/replay) → parse ADP board → append to `fact_fantrax_adp.parquet`.
- **Board now includes IDP**: ~280 offense (ADP) + ~1,374 active-roster IDP = ~1,653 rows. IDP have null ADP (Fantrax global ADP is offense-only) but are kept for salary/bye/Rk via filter `teamShortName != "(N/A)"`. The defensive position set is derived from `dim_position` (`side_of_ball=="Defense"`), with a hardcoded fallback.
- Dual-eligible players (e.g. Travis Hunter `WR,DB`) appear twice in the board with one `scorer_id`; dedup collapses them.
- **Identity crosswalk (04z)**: `dim_fantrax_crosswalk` maps `scorer_id` → `gsis_id` (via `dim_nfl_players`) + `player_key` (via `dim_rookie_prospect`). `dim_nfl_players` (24,966-row full nflverse registry) covers ~100% — incl. signed rookies; `dim_rookie_prospect` only catches draft-class. So `gsis_id` is the universal key. 04a joins the crosswalk on load (`_load_crosswalk`); new `scorer_id`s stay null until 04z re-runs. Matcher: exact cleaned-name → disambiguate by **position** (strongest) / active status / team / recency → fuzzy ≥90. As of 2026-06-06 (after the 2025 YTD backfill): **2,288 scorer_ids, ~98% gsis** (a few nickname vets manually fixed, e.g. Cameron→Cam Skattebo).

## Roster-transactions ledger — BUILT + MERGED 2026-06-14 (ADR-0003/0004, PR #15)

Event-sourced `fact_roster_transactions` (acquisition ledger; `fact_fantasy_teams`
derived by replay). Grill 2026-06-14 (this session) corrected a load-bearing
assumption and resolved v1 scope — *full design in data-model.md + ADR-0003/0004,
live status in PLAN.md.*
- **Reality correction**: the league is at the **STARTUP DRAFT now, and it is a
  snake/linear DRAFT — NOT an auction** (auctions = FA / re-sign, next offseason,
  i.e. ~2027). The ADRs' `startup_auction` event is **misnamed** → use
  `startup_draft`. (ADR-0003/0004 text amendment pending Phase 0.)
- **v1 decisions**: full ADR-0004 (build `dim_roster_asset` + `dim_draft_pick` +
  `dim_season` + `pick_allocation`/`trade` + polymorphic `asset_id`). Each pick →
  Initial contract yr1 (`dim_contract` "1st", 0.50 cap_hit, guaranteed);
  `contract_value` = **the Fantrax `salary` field** (already in `fact_fantrax_adp`),
  as-of the pick. Pick horizon = **current + 2** (2026/2027/2028). `asset_id` =
  **monotonic integer sequence**, persisted in `dim_roster_asset`, never re-derived.
- **Source = `getDraftResults`, fetched by NEW `notebooks/04w_fantrax_draft_results.py`**
  (reuses 04a's `FantraxScraper`/`.pw_profile`). Request (from the 2026-06-14
  /draft-results HAR): `msgs=[getDraftResults{}, getFantasyLeagueInfo{},
  getRefObject{FantasyDraftPickType}]`, `v 183.1.5` (getDraftRanks was 182.4.8).
- **⚠ Fantrax gotcha (cost a debug cycle)**: the draft board is served via Fantrax's
  **service worker** (`fx-sw.js`), so a DevTools HAR records the response *size* but
  **NOT the body** (`_fetchedViaServiceWorker:true`, empty `content.text`). A HAR
  cannot deliver `getDraftResults` — must fetch through the authed request context
  (what 04w does). Same applies to any other SW-served fxpa method.
- **Identity (in the parse step)**: player `scorerId → gsis_id/player_key` via
  `dim_fantrax_crosswalk` (04z); team `teamId → team_key` via
  `dim_fantasy_teams.fantrax_team_id` — the league **Sheet now carries the
  `Fantrax-TeamId` column** (ADR-0005 locked col; user added it 2026-06-14), so 01c
  ingests it (28/28). A name-match heuristic crosswalk (01g) was built then
  **retired** once the Sheet column landed (it had inferred the right mappings;
  re-running 01c also fixed drifted team names — A08 was a stale "Metallica").
- **Build outcome (S1–S4, verified on the live Riddell capture, `.venv`)**:
  `01f`→`dim_season`; `02d` (live-loop)→`dim_roster_asset` (137; monotonic
  `asset_id` minted on `scorer_id`, persisted) + `dim_draft_pick` (490 slots) +
  `fact_roster_transactions` (137 `startup_draft`); `02e`→12-col `fact_fantasy_teams`
  + cap rollup; `05a` got a non-destructive "Drafted By" availability column. 137/137
  picks resolve to gsis_id+salary.
- **⚠ Finding — startup picks WERE traded** (some teams hold 2 picks/round). So
  getDraftResults' slot `teamId` = *current* owner → `dim_draft_pick` is keyed on
  the slot `(draft_season, divisionId, overall_slot)` and `original_owner` is left
  NULL until `draftPicks.go` is captured (which also lights up `pick_allocation`/
  `trade`, dormant v1, + 2027/2028 forward picks). Made-pick fact unaffected.
- **Status update 2026-07-11**: both divisions now live — Riddell 485/490 picks made,
  Wilson 450/490 (near-complete, re-run `04w` to refresh). `02d`/`02e` scale to both
  divisions cleanly: 935 total picks, all 935 resolve to gsis_id/player_key (04z
  universe-extension fix, above) and cap-hit. 122 picks still have a null
  `contract_value` — that's Fantrax's own payload missing a `salary` field on those
  specific picks (draft-in-progress state), unrelated to identity resolution; re-check
  after Wilson finishes. **Open**: `draftPicks.go` capture (pick trading/allocation,
  dormant v1); ADR-0003/0004 text amendments (startup_draft rename, slot-keyed pick,
  Sheet identity) → next Phase 0.

## Cap architecture (changed 2026-07-11)

**`Fact_FantasyTeams`/`fact_fantasy_teams.parquet` is the only location for
contract/salary/cap-hit data.** `Dim_FantasyTeams`/`dim_fantasy_teams.parquet`
only carries `original_cap`/`reinvestment_cap` — the two cap facts true
independent of the roster. It used to also cache an ETL-frozen rollup
(`active_roster_salary`, `cap_hits_current_yr`, `remaining_cap_current_yr`,
etc., written by `02e`) that a real Power BI bug traced back to — see
powerbi-semantic-model.md "No ETL-frozen rollups" for the full root-cause
writeup. Fixed end-to-end, not just in PBI:
- **ETL** (`01c`, `02e`): schema trimmed, `02e` no longer writes anything back
  into `dim_fantasy_teams.parquet`.
- **Power BI**: `_Measures.tmdl` computes `'Active Roster Salary'` (`SUM(CapHit)`),
  `'Contract Value'` (`SUM(ContractValue)`, total deal size — different from
  Active Roster Salary, which is just this year's charge), `'Dead Money'`
  (`SUM(DeadMoney)`, previously unused anywhere in the report), `'Remaining
  Salary Cap'`, `'Percent of Cap Used/Remaining'`, `'Player Pct of Team Cap'` —
  all live off `Fact_FantasyTeams` + `Dim_FantasyTeams[OriginalCap|ReinvestmentCap]`.
- **Discord bot**: new `discord_bot/capmath.py` — `teams_with_cap(cfg)` computes
  the identical formula in pandas at read-time (`cap.py`/`roster.py` call it
  instead of reading a cached column). Kept in sync in the
  `discord-bot-github-fetch` skill.
- Dead money's actual home is `Fact_FantasyTeams.DeadMoney` (contract-value
  grain — needs a specific player's contract, which `Dim_Contract`'s shared
  10-row rule table can't hold). `Dim_Contract.Guaranteed` is the *rule* that
  determines whether a dropped contract carries dead money; the dollar amount
  is necessarily fact-grain.
- One formula, implemented twice on purpose (DAX + pandas — neither consumer
  has the other's engine), cached nowhere.

**Follow-on finding (same session, same principle)**: `Fact_FantasyTeams.CapHit`
and `.Conference` were ALSO redundant stored columns — `CapHit` = `ContractValue
x Dim_Contract.CapHitPct` (100% derivable once the missing `Fact_FantasyTeams.
ContractID → Dim_Contract.ContractID` relationship was added), `Conference` =
100% derivable via the existing `TeamKey → Dim_FantasyTeams.TeamKey`
relationship. Both removed from `fact_fantasy_teams.parquet`/`02e`/the TMDL;
`_Measures.tmdl` derives `CapHit` via `RELATED()`; `discord_bot/capmath.py`
gained `roster_with_cap_hit()` for the same join in pandas. `DeadMoney` was
**not** touched — no simple single-row formula exists yet (needs real
drop-event tracking, ledger `drop` event type doesn't exist); the user is
building the 3-version design (current/next/total year) live in `_Measures.tmdl`
themselves — **see PLAN.md "Active — dead money"** for the full spec, don't
duplicate it here as it'll drift. `dim_season.relative_nfl_season_number`
(one of that design's dependencies) is **built** (`01f`, 2026-07-11) — 0 =
season containing today via the fantasy window, negative=past/positive=future.
Not yet in the PBI model (`dim_season` isn't a TMDL table yet).

**New task (2026-07-11, not started)**: identify Minor League squad + plan the
draft-completion transition mechanics — **see PLAN.md "Active — identify Minor
League squad"**. Ties into the dead-money work above (a drop is a cap event).

## Dynasty Rankings (section 04) — single EAV fact

Whole-roster (veteran+rookie) dynasty value/ranks from multiple sources with
**incompatible metric vocabularies** (KTC trade value/tiers/trends; DynastySharks
1/3/5/10-yr projections; FantasyPros best/worst/avg/std-dev). Everything stored long/EAV.
**Refactored 2026-06-12 (via /grill-me): the two-layer model collapsed to one fact** —
*see `data-model.md` for full schema + rationale.*
- **`fact_dynasty_ranking_metrics`** — the only dynasty fact. Grain `snapshot_date +
  source_name + source_player_id + format + metric_key → metric_num | metric_text`.
  `overall_rank`/`positional_rank` folded in as **source-prefixed** keys (`ktc_/ds_/fp_*`);
  carries `gsis_id` for its own relationship to `dim_nfl_players` (player name/pos/team/age
  come from that dim; no-gsis players drop out). `fact_dynasty_rankings` backbone retired.
- **`dim_dynasty_crosswalk`** — unified `(source, source_player_id) → gsis_id + player_key + match_method` (all dynasty sources in ONE table, unlike per-source `dim_fantrax_crosswalk`).
- **`dim_dynasty_metric`** (04c) — curated `metric_key` index: `metric_label`, `metric_group` (incl. new `Rank`), `metric_order`, `value_type`, `direction`, and **`source_name`** (one source per key — the attribution source-of-truth now that the fact's `SourceName` is dropped from the model). Powers the PBI **matrix column axis**.
- **`adp` split + composite** (04y): `adp` → `ktc_adp`/`ds_adp` (crowd Elo vs projection model, incommensurable scales); 04y blends → `composite_adp` (percentile-within-(source,format) → mean → re-rank) + `sources_count`, written as a `Composite` gsis-keyed partition.
- **Format** is a dimension (`SF`, `TEPP`, `IDP`, `1QB` reserved); time = **manual-cadence** snapshots (`snapshot_date`, now a real date). Load = replace-by-`(snapshot_date, source_name)`.
- **`source_uid` = `source_name|source_player_id`** on the fact + crosswalk — ETL identity key (`source_player_id` alone collides across sources); the fact now also joins `dim_nfl_players` directly via `gsis_id`.

### Sources & shared resolver — *see `data-model.md` for schemas + full detail*
- **KTC** (04b): full ~500-asset DB embedded as `var playersArray` in the dynasty page HTML (one `requests.get` + regex, no browser); `superflexValues` → `SF`, nested `.tepp` → `TEPP`; format-agnostic metrics duplicated onto both rows; RDP picks excluded. KTC `adp`/`startup_adp` 0 = "no data" sentinel (treated missing).
- **Manual** (04x): DynastySharks SF/TEPP + FantasyPros SF/IDP from `data/raw/DynastyRankings_2026_ManualExtraction.xlsx`; Pos token `QB1`→QB+rank 1; `source_player_id` = name slug. Parse with `df.to_dict("records")` (itertuples mangles headers like `1yr. Proj`).
- **Identity**: shared `etl_helpers.resolve_dynasty_crosswalk` — ONE matcher for all sources (exact → disambiguate position/ACT/recency → fuzzy ≥90; `manual` override map for nickname vets; `rookie` fallback). Each notebook builds identities, calls it, upserts its `source` rows.
- Pre-refactor load 2026-06-06: ~2,089 backbone + 20,064 metric rows, gsis 99.5–99.8%, ~2 unresolved (Daylan Smothers, Mark Fletcher — 2026 rookies absent from both registries). Counts shift after the 2026-06-12 rerun (ranks become metric rows; backbone gone). Review CSV = projection of crosswalk unresolved rows (rebuilt each run).

## Fuzzy Review & Player Alias (dedup of repeated questions)

- **All review CSVs live in `data/review/`** (not `data/` root). Notebooks 03a–03x write `data/review/review_fuzzy_matches.csv`; 04z writes `data/review/review_fantrax_crosswalk.csv`. Applied files archived in-place as `*.applied_YYYYMMDD.csv`.
- **`dim_player_alias`** (03y) is a persistent decision/transformer table, key `(name_clean, position_raw)` → `player_key`, with `decision` (match|new). It stops the fuzzy review from re-asking the same player across sources/runs.
- **Why it was needed**: previously a `match` (manual *or* auto ≥90) recorded nothing — so the variant re-surfaced every run AND `ingest_ranking_source` dropped its ranking (clean name absent from `dim_rookie_prospect`). The alias fixes both: matchers (`add_players_from_source`) skip `(name_clean, position_raw)` already in alias; `ingest_ranking_source` folds alias into `name_to_key` (via `setdefault`) so variants attribute to the resolved key.
- **Auto-matches (≥90) are also recorded** to the alias (`decision="auto"`) by the matcher itself — they never hit the review file, so the matcher must persist them or their rankings drop (this was a live bug: RotoBaller ingested 98/100 until fixed).
- **Apply flow (03z)**: appends every match/new decision to `dim_player_alias`; only archives a review when **every `action` is filled** (a blank `action` = not reviewed; `*.applied_` = a reliable "done" tell). When *Claude* resolves rows itself, it fills `action` too.
- **Watch out**: review CSVs open in Excel/OneDrive lock the file — rename/truncate then fails; close it so 03z can archive cleanly.

## dim_rookie_prospect — Current State (as of 2026-05-30)

- Base 319 (nflverse combine) → **~470 players** after all ranking passes.
- Threshold: auto-link ≥ 90, review 70–89, new < 70. Repeat-review eliminated by `dim_player_alias` (03y/03z).
- Review CSVs + `*.applied_YYYYMMDD.csv` archives now live in `data/review/` (gitignored).

## Key Config Values (LeagueConfig dataclass)

```python
draft_year: int = 2026
total_cap: int = 300_000_000
num_teams: int = 28
num_conferences: int = 2
initial_contract_years: int = 3
extension_contract_years: int = 3
fa_minimum_salary: int = 2_000_000
data_dir: str = "data"
fuzzy_auto_threshold: int = 90
fuzzy_review_threshold: int = 70
team_sheet_id: str = "1Fiz_KHH5bexSAHIfL0uVIqgHU6jTgnOmDs86kjR8TZc"
team_sheet_gid: str = "178660131"
```

Cap hit % and dead money live in `dim_contract` rows — never in LeagueConfig.

## In-Season Tables (deferred — not yet built)

- `fact_nfl_player_stats` — weekly stats from nflreadpy
- `fact_nfl_season_injuries` — weekly injury reports from nflreadpy
