# `Minor` is a pre-1st contract stage

- Status: accepted. Designed through HITL grilling on 2026-10-02; not yet built.
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
6. **`02d` takes each Roster Move's contract from the latest Roster State at or before the move.** A default applies only when there is no snapshot to read: the preseason draft history, or a claim and drop inside one period.
   - Default: `Minor` if the player is eligible. Otherwise `1st` for a drafted player, or `FA`/the inherited contract for a claim.
   - The hard-coded `CONTRACT_ID = "1st"` becomes that fallback.
7. **`dim_contract` gains one row:**

   | contract_id | contract_type | contract_label | salary_type | contract_year | total_years | cap_hit_pct | guaranteed | cap_exempt | min_salary |
   |---|---|---|---|---|---|---|---|---|---|
   | `Minor` | `minor` | Minor | Fixed Salary | NULL | NULL | 0.0 | False | False | NULL |

   - NULL years mean open-ended and off the clock. A player can stay on `Minor` across seasons, for example a rookie who is injured.
   - `cap_exempt = False` because the contract never exempts anyone; only the Minors slot does.

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
- **Dead money (#96) needs no special case.** `capmath` prices only Cut players on Guaranteed contracts, and `Minor` is not guaranteed.
- **Build work, in one issue under #70:**
  - the `01b` seed row;
  - `02d` contract sourcing with the eligibility-aware fallback, where `Minor` writes a NULL `contract_year`;
  - tests;
  - a `cap-ledger-auditor` review.
- **The drift check is an input to the #88 grill.** It files to `ops.review_check` once that table exists (ADR-0018).
- **The `contract_id` FK becomes a normal clean edge** once the row lands.
- **The `contract_year` rollover clock is still unbuilt** (noted in ADR-0010). Decision 3 defines when the clock starts, but nothing advances it yet.
- **ADR-0011's "Zero `Minor` contracts exist" stays in its body as the record of July's data.** The status line points readers here.
