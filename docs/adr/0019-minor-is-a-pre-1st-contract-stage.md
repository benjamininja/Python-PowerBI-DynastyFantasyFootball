# `Minor` is a pre-1st contract stage

- Status: accepted. Designed through HITL grilling on 2026-10-02. Built 2026-10-03 (#113): the `dim_contract` row and `02d` contract sourcing. The drift check (decision 4) and the `contract_year` clock are still unbuilt.
- Date: 2026-10-02
- **Supersedes the headline of** [ADR-0011](0011-minors-is-placement-not-contract.md) ("there is no Minor contract type"). The rest of ADR-0011 stands: `04v` is read-only, the repo has no Fantrax write path, IR charges full salary, and only the Minors slot is cap-exempt.
- [ADR-0010](0010-minors-stash-season-boundary.md) stays superseded. Its stash rule does not come back (decision 5).
- Settles [ADR-0018](0018-supabase-schema-and-rls.md) decision 6: the `contract_id` FK is no longer provisional once `dim_contract` has its `Minor` row.
- Scope:
  - `notebooks/01b_dim_contract_seed.ipynb` (`dim_contract`)
  - `notebooks/02d_fact_roster_transactions.py` (contract on each Roster Move)
  - the #88 post-run checks
  - `CONTEXT.md`

## Context

- ADR-0011 rested on the 2026-07-18 capture: 987 `1st` and 5 `FA` contracts, zero `Minor`. That capture was right for its day.
- The in-season capture (#79, [findings §4](../research/inseason-schema-extraction.md)) shows a `Minor` contract on 351 roster rows in period 1 and 349 in period 3.
- `Minor` tracks eligibility, not placement:
  - 349 of 351 `Minor` rows are minors-eligible.
  - In period 3, only 138 `Minor` players sit in the Minors slot. The others are Starter (76), Bench (110) and IR (25).
- The other commissioner settled on the fluid design. `Minor` is the contract for anyone inside the eligible window. The Minors slot is where a team holds players off the cap, and players move in and out of it freely.
- `dim_contract` has no `Minor` row (10 rows: `1st`–`6th`, `Tag`, `X`, `FA`, `Pick`), so about a third of Roster State contracts find no match.
- `02d` stamps `contract_id = "1st"` on every drafted player and `FA` (or the inherited contract) on claims. That is wrong for eligible rookies.

## Decision

1. **`Minor` is a contract: the stage before `1st`.** A player holds it while minors-eligible (career plus current regular-season games played ≤ 19, computed by Fantrax). Three concepts stay separate:
   - **Minors Eligibility**: a flag on the player.
   - **Minor**: the contract.
   - **Minors**: the Roster Slot. It is the team's lever and the only cap exemption.
2. **A Minor drop costs no Dead Money.** `cap_hit_pct = 0` and `guaranteed = False`, the same terms as `FA`.
3. **A Minor player moves to `1st` immediately, mid-season,** in the Scoring Period after they pass 19 games. That season counts as year 1 of 3. The salary carries over unchanged.
4. **Contracts are observed, never derived.** The contract always comes from Fantrax's Roster State. A post-run check (#88) files each mismatch to `ops.review_check`, and it never blocks the run. The mismatches are:
   - an eligible player on `1st` or `FA`;
   - an ineligible player on `Minor`.
5. **Any eligible player is on `Minor`,** however they were acquired: draft, auction or claim. Protection follows eligibility, not a team's stash, so ADR-0010's season-boundary stash rule stays dead.
6. **`02d` takes each Roster Move's contract from the latest Roster State at or before the move.** A default applies only when there is no snapshot to read: the preseason draft history, or a claim and drop inside one period. *The per-period Roster State is `fact_roster_state` ([ADR-0016's 2026-10-03 amendment](0016-roster-state-from-snapshot-ledger-is-provenance.md#amendment-2026-10-03-in-season-fact-model-81), decision 3), which replaces `fact_roster_placement`.*
   - Default: `Minor` if the player is eligible. Otherwise `1st` for a drafted player, or `FA`/the inherited contract for a claim.
   - The hard-coded `CONTRACT_ID = "1st"` becomes that fallback.
   - *Built in #113, with these rules settled on 2026-10-03:*
     - *The preseason snapshot is not read (owner's decision). It was taken before Fantrax moved eligible players to `Minor`, so it shows `1st` on players who were `Minor` by week 1. Only in-season snapshots count, and every preseason move takes the default.*
     - *A move reads only snapshots captured before its own day and inside the copy's current stint on the team: stint start ≤ capture day < move day (owner's decisions, after the `cap-ledger-auditor` review).*
       - *`04v` stamps a snapshot with the day it ran, so a capture dated the move day may have been taken after the move.*
       - *A copy dropped and claimed back starts a new stint. A snapshot from the old one can show a contract the player has since left.*
       - *A draft pick and a claim start a stint, so both always take the default.*
       - *A copy with no stint on record (the ledger never saw it join the team) reads any snapshot before the move day.*
     - *A snapshot row with a blank contract or no capture date is not an observation.*
     - *These rules cover the contract only. Salary is sourced on its own (#125): a draft pick or a claim reads the first snapshot after the move, inside the stint it starts, and the preseason snapshot is read for it. Its salaries match the in-season rosters.*
     - *A player is eligible on the day of a move if either neighbouring eligibility snapshot lists them: the first one on or after the move day, or the last one before it (owner's decision).*
       - *Games played only grow, so a player eligible later was eligible that day.*
       - *A player listed before the move and not after it graduated in between, on an unknown side of the move. The earlier list stands.*
       - *`02d` prints how many moves the earlier list decided, in two counts: moves made after the newest snapshot, and moves by a player who had dropped off the next one.*
     - *`02d` warns when a move takes the default more than 8 days after the newest eligibility snapshot. The label is kept (owner's decision).*
     - *An ineligible player whose inherited contract is `Minor` gets `1st`: they graduated (decision 3).*
     - *A trade with no source row and an ineligible player keeps an unknown contract. Nothing is invented.*
     - *Amended 2026-10-04 (#117): the lookup reads `fact_roster_state`, by the Scoring Period Fantrax says the move takes effect in, not by capture day ([ADR-0016's amendment](0016-roster-state-from-snapshot-ledger-is-provenance.md#amendment-2026-10-03-in-season-fact-model-81), decision 3). It needs the copy on the move's team (the "from" team for a trade). The day rules above are replaced:*
       - *A trade and a drop read the latest Roster State inside the copy's stint and before the move's period: stint-start period ≤ p < move period.*
       - *A draft pick and a claim no longer always default (owner's decision, 2026-10-03). Each reads contract and salary off the first Roster State inside the stint it starts: move period ≤ p < the period the copy next leaves the team in. A draft pick takes effect in period 1. The default applies only when no such row exists: a copy that left before a roster showed it.*
       - *The preseason capture is still never read for a contract. It now lives in `fact_preseason_salary`, which holds salaries only. (Amended by #96, below.)*
       - *The eligibility rules above are unchanged, and the eligibility captures are read for the draft's own season only.*
     - *Amended 2026-10-04 (#96, owner's decision): the preseason capture is read for a contract, by a stint that only that capture saw. A draft pick or a claim that no Roster State row covers takes the capture's contract when the capture was taken inside the stint the move starts (after the move day, before the copy next left the team): `Minor` if the player is minors-eligible, else the contract the capture shows. `fact_preseason_salary` gains `contract_id` for it.*
       - *Measured 2026-10-04 against Fantrax's Salary Remaining: four claims the capture shows on `1st` were dropped before a period-1 roster showed them. The ledger had them on `FA`. Half their salary is the whole of Fantrax's gap on the two teams that made them, to the dollar.*
       - *Eligibility wins over the capture. It predates the `Minor` label (987 rows on `1st`, 5 on `FA`), and the minors-eligible players it shows on `1st` were dropped and not charged.*
       - *A Roster State row still wins over the capture. A trade or a drop reads nothing new: it keeps the contract of the stint it ends.*
       - *The ledger's `contract_source` records where each row's contract was read: `roster_state`, `preseason` or `default`. A trade or a drop with no Roster State row of its own carries the source of the stint it ends.*
       - *An eligible player's `Minor` is `default`, whether or not the capture shows the stint (owner's decision, 2026-10-04, after the `cap-ledger-auditor` review). Eligibility set it, not the capture. The capture still gives that stint its salary.*
7. **`dim_contract` gains one row:**

   | contract_id | contract_type | contract_label | salary_type | contract_year | total_years | cap_hit_pct | guaranteed | cap_exempt | min_salary |
   |---|---|---|---|---|---|---|---|---|---|
   | `Minor` | `minor` | Minor | Fixed Salary | NULL | NULL | 0.0 | False | False | NULL |

   - NULL years mean open-ended and off the clock. A player can stay on `Minor` across seasons, for example a rookie who is injured.
   - `cap_exempt = False` because the contract never exempts anyone; only the Minors slot does.
   - *Built in #113. Both year columns are nullable integers (`Int64`), so the NULLs do not turn them into floats.*
   - *`dim_contract.cap_exempt` is True on `FA` and `Pick` and read by nothing. The owner chose to document it as a descriptive flag rather than drop it (2026-10-03).*

## Alternatives considered

- **`Minor` as a label that mirrors eligibility,** priced like `1st`. Rejected: the contract has terms of its own (no dead money, off the clock).
- **50%/40% Dead Money on a Minor drop,** as for `1st`. Rejected by the owner: a prospect can be dropped for free.
- **Graduation at season rollover.** Rejected by the owner: `Minor` ends the period after eligibility ends, and that season is year 1.
- **Graduation whenever the commish sets it.** Not chosen as the rule. Decision 4 covers the lag in practice: the ETL reads what Fantrax shows, and the drift check catches a missed flip.
- **Deriving the contract from eligibility in the ETL.** Rejected: it gives two contract truths. **Observing with no check** was rejected too: mismatches would go unseen.
- **Claims stay on `FA`.** Rejected: the eligible window, not the acquisition route, decides the contract.
- **Moves carry no contract.** Rejected: a claim and drop inside one period would have nothing to price. **Deferring to #81** was rejected too: #81 needs this settled first.
- **Re-valuing salary at graduation.** Rejected: it would change the cap mid-season with no rule to drive it.
- **`0/0` or `1/1` years.** Rejected: `0` reads oddly, and `1/1` implies a yearly renewal that does not happen.
- **Rewriting ADR-0011 in place, or fully superseding it.** Rejected: rewriting loses the July reasoning, and full supersession duplicates the parts that still stand.

## Consequences

- **The cap path is unchanged.** Only the Minors slot is exempt, in the same four places ADR-0011 lists: `capmath.py`, `02e`, and the `Active Roster Salary` and `Remaining Salary Cap` measures.
- **Dead money (#96) needs no special case.** `capmath` prices only Cut players on Guaranteed contracts, and `Minor` is not guaranteed. *The ledger's own `cap_hit` column, which nothing reads and #97 replaces, shows 0 on a `Minor` draft row.*
- **Build work, in one issue under #70** *(#113, built 2026-10-03)*:
  - the `01b` seed row;
  - `02d` contract sourcing with the eligibility-aware fallback, where `Minor` writes a NULL `contract_year`;
  - tests;
  - a `cap-ledger-auditor` review.
- **The drift check is an input to the #88 grill.** It files to `ops.review_check` once that table exists (ADR-0018). *Settled in [ADR-0008's amendment](0008-regression-testing-standard.md#amendment-2026-10-03-publish-gate-post-run-checks-ci-88) (decision 9). It is a Review check with one Scoring Period of grace: a mismatch surfaces only if it is still there once the next period starts.*
- **The `contract_id` FK becomes a normal clean edge** once the row lands.
- **The `contract_year` rollover clock is still unbuilt** (noted in ADR-0010). Decision 3 defines when the clock starts, but nothing advances it yet.
- **ADR-0011's "Zero `Minor` contracts exist" stays in its body as the record of July's data.** The status line points readers here.
