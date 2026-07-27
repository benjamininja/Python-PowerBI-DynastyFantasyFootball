# Minors is placement + eligibility, not a contract type

- Status: accepted
- Date: 2026-07-26
- **Supersedes** [ADR-0010](0010-minors-stash-season-boundary.md) (stash
  durability across season boundaries), which modelled protection for a
  contract type that does not exist.
- Scope: `notebooks/04v_minor_contracts.py`, `tests/test_04v_minor_contracts.py`,
  `data/review/`, the Yo-Yo Rule wording in `PLAN.md` and
  `.claude/memory/data-model.md`

## Context

The Minors system was originally modelled as a **contract type**: a
minors-eligible player would be moved onto a distinct `Minor` contract, which
carried its own cap treatment and paused the 3-year clock, and a commissioner
worklist reconciled eligibility against contract type each week.

The commissioner confirmed that design was abandoned in favour of a simpler
process, and the live data agrees with the simpler one:

- **Zero `Minor` contracts exist.** `fact_roster_placement`'s 992 rows are 987
  `1st` + 5 `FA`. All **125** players sitting in the Minors squad section hold
  `1st`.
- Minors eligibility is a **flag on the player**, computed by Fantrax (GP <= 19):
  357 rostered copies are eligible, of which only 125 are actually *placed* in
  Minors — the other 232 sit in Active/Reserve. Eligibility permits placement;
  it does not compel it, and it does not touch the contract.

So there are two independent concepts and no third one:

- **Eligibility** — career+current regular-season GP <= 19, Fantrax-computed,
  league-wide, applies whether rostered or FA.
- **Placement** — which squad section a roster copy occupies this week
  (Active / Reserve / Minors). The team's own lever, and the sole cap
  exemption.

A player is minors-eligible for 20 games while holding an ordinary contract —
generally `1st`, barring injuries. Nothing about the contract changes when they
are placed in, or removed from, the Minors squad.

## Decision

**Minors is placement + eligibility. There is no Minor contract type, and no
contract state derives from Minors status.**

Consequences for the code that assumed otherwise:

1. **`04v` becomes read-only.** Its purpose is now exactly: pull eligibility,
   pull per-team placement, land `fact_minor_eligibility` and
   `fact_roster_placement`. Deleted outright: `build_worklist`,
   `apply_worklist`, `export_fa_csv`, `prev_eligibility`, the
   `admin_roster_payload`/`build_field_map`/`edit_payload` write-side helpers,
   and the `--apply` / `--dry-run` / `--teams` / `--max-teams` /
   `--export-fa-csv` flags.
2. **The repo's only write-side path to Fantrax is gone.** `04v --apply` was a
   deliberately grill-approved, attended-only exception to the standing
   no-write-side rule. Stripped of the worklist it existed to apply, it has no
   purpose, so the exception is retired rather than left as dead code. The repo
   is now uniformly read-only against Fantrax.
3. **The stale worklist artefacts are deleted** —
   `data/review/review_contract_actions.csv` (5,698 rows, every one of them
   "set contract → Minor") and `data/review/fa_contract_import.csv`. Both were
   untracked. Regenerating them is no longer possible.
4. **Nothing needs to replace the worklist.** Its remaining conceivable job —
   catching a player placed in Minors who is no longer eligible — is enforced
   by Fantrax at the source: an ineligible player cannot occupy a Minors slot,
   so the condition cannot arise in a pull.

## Consequences

**`04v` is load-bearing and must keep running.** It is the *sole* writer of
`fact_roster_placement`. `02e` stamps `roster_status` onto `fact_fantasy_teams`
from that snapshot, and `discord_bot/capmath.py` plus the DAX
`Active Roster Salary` measure exempt `roster_status == "Minors"` from the cap
charge. If 04v stops running, `roster_status` goes null league-wide and all 125
Minors-placed players begin charging full salary. Read-only does not mean
optional.

**The `contract` column stays on `fact_roster_placement`.** It records observed
site state (`1st`/`FA`) and remains useful; it is simply no longer diffed
against eligibility.

**Left in place, deliberately, for a separate cleanup pass** — all of it inert
(no rows, no callers) and none of it affecting the cap path:

- `dim_contract`'s `Minor` row (`contract_id="Minor"`) — orphaned, referenced
  by nothing.
- `derive_minor_events()` in `02d_fact_roster_transactions.py` and the
  `minor_assignment` / `minor_graduation` event types — have never emitted a
  single row and now never will.
- The `Minor` references in the PBI `_Measures.tmdl` and `Fact_FantasyTeams.tmdl`.

**IR cap treatment — raised here, DECIDED 2026-07-26: IR charges full salary.**
Only `"Minors"` is cap-exempt. `04v` builds its section map from Fantrax's own
`statusTotals` and passes unknown status ids through raw, so an **IR** section
will surface on its own once the season starts. The commissioner confirmed that
IR-placed players count against the cap exactly like Active/Reserve — IR is a
lineup convenience in this league, not cap relief. **This required no code
change**: the existing rule already charges anything whose `roster_status` is
not the literal `"Minors"`, so IR is handled correctly the day it appears.

Recorded so a future reader does not mistake the silence for an oversight: the
`<> "Minors"` literal is deliberate, not a TODO. Note it is duplicated in
**four** places, and any future change to which sections are exempt must land in
all four or the bot and the report will disagree about who is over the cap:
`discord_bot/capmath.py` (`cap_exempt`), `notebooks/02e_fact_fantasy_teams_derive.py`
(`cap_hit` zeroing), and the PBI `_Measures.tmdl` measures `Active Roster Salary`
and `Remaining Salary Cap`. A null `roster_status` charges normally by the same
rule (35 such rows today) — also deliberate, it is the safe default.

## Alternatives considered

- **Keep `apply_worklist`/`export_fa_csv` as dead code** in case a write-side
  path is wanted later. Rejected by the commissioner: "they no longer have
  value when stripped of purpose." Keeping a live Fantrax write path with no
  caller is a standing hazard for no benefit; git history preserves it.
- **Repurpose the worklist to flag ineligible players in Minors.** Rejected —
  Fantrax enforces this at the source, so the worklist would be empty by
  construction.
- **Delete the whole `Minor` contract apparatus in one pass** (dim_contract row,
  `derive_minor_events`, PBI measures). Deferred to keep this change scoped to
  neutralizing the live hazard; the remainder is inert and can be removed
  without urgency.
