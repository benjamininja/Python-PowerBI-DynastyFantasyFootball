---
name: startup-draft-board-05a
description: "Tank-year startup draft board pipeline — script location, composite weights, judgment overlay CSV, known scoring quirks"
metadata:
  type: project
---

Benjamin's 2026 startup draft board lives at `notebooks/05a_startup_draft_board.py` in Python-PowerBI-DynastyFantasyFootball; output is `data/outputs/startup_draft_board.xlsx` ("Offense" + "Defense" sheets, 250 rows each, plus pivot-ready "Data" sheet). League rules + interaction prefs (grill-me before new features, caveman-lite, BEFORE/AFTER diffs) are source-of-truthed in the repo at `data/raw/Instructions-Fantasy Football Dynasty League Assistant.md` — read it before board/league work.

**Why:** Built 2026-06-09 via grill-me session; expanded same day with full dynasty-metric integration. Decisions locked: hybrid tiering (algo proposes, judgment overrides); weights 35% market (KTC value, DS value, FP avg, Fantrax rank, drafted%, KTC startup ADP, startup auction %) / 20% production (60% trailing FP/G + 40% DS Proj 1-Yr) / 25% window (70% age curve + 30% DS Proj 5-Yr) / 20% salary-efficiency + tank modifiers (+5 age≤25, −7 age≥28, −3 age≥30, Yo-Yo boost scaled by runway). Unified offense+IDP board.

**How to apply:** CRITICAL Yo-Yo semantics (Benjamin corrected this): a player is cap-exempt until his **20th career NFL game is PLAYED** — runway burns per game played, never by calendar or stash deadline. Track `ml_games_left = 20 − career_games` (exact via nflreadpy, entry_year≥2022), not a binary flag. Board is split: "Offense" and "Defense" sheets, 250 each, per-side 1a–4 tier ladders, cross-side `Score` + `Ovr Rank` kept; Defense sheet drops offense-only columns (ADP/KTC/projections). Judgment layer is `data/raw/draft_board_notes.csv` (gsis_id, tier_override, arc_note, strategic_note; ~385 rows — full offense 250 + defense top 100) — edit and rerun; blank cells fall back to rule notes; an auto metric suffix appends to every note. Known quirks: Fantrax ADP null for ALL IDP; KTC/DS offense-only; formula underprices TE-premium, SF-QBs, elite EDGEs, and the two-way Travis Hunter (WR,DB) — overrides handle. Fantrax crosswalk manual fixes (33: Skattebo, Sauce Gardner, Nnamdi Madubuike, Jaylon Jones CHI/IND collision, etc.) persist in `data/raw/fantrax_crosswalk_overrides.csv` (scorer_id → gsis_id or "new"); 04z consults it first (method=manual, score=100) and its dup-gsis check is a hard failure, so full re-runs keep the fixes (landed 2026-06-10 — `scripts/apply_fantrax_crosswalk_review.py` is historical, do not re-run). 7 deep 2026 UDFAs stay "new" until a dim_nfl_players refresh.

Related: [[data-model]], the 05a `METRIC_MAP` keying grill (open, see PLAN.md).
