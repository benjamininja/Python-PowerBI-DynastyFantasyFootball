# Season rollover 2027: contract labels, keep choices and the Mar 1 boundary

- Status: accepted. Decided in the owner grill of map [#557](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/557) (Ben, 2026-11-14, by pop-up: round 1 in the map's body, rounds 2 and 3 in its first comment), confirmed by Ben there. The three points of [How the pipeline reads a season](#how-the-pipeline-reads-a-season) were answered by Ben and the planner on [#558](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/558) (the planner's check, 2026-11-14). Docs only: nothing in this ADR is built by the PR that records it. The builds are listed under [Built for 2027](#built-for-2027).
- Date: 2026-11-14
- Builds on: [ADR-0019](0019-minor-is-a-pre-1st-contract-stage.md), whose unbuilt `contract_year` clock it plans (its decision 4, "contracts are observed", is kept), and decision 4 of [ADR-0016's #97 amendment](0016-roster-state-from-snapshot-ledger-is-provenance.md#amendment-2026-10-14-the-cap-module-the-current-roster-and-the-cap-table-97) (the roster's season). It reverses no decision.
- Scope:
  - `notebooks/01b_dim_contract_seed.ipynb` (`dim_contract`, the `X` row)
  - `notebooks/02d_fact_roster_transactions.py`, `notebooks/02e_fact_fantasy_teams_derive.py`, `notebooks/etl_cap.py`, `notebooks/02h_fact_team_cap.py`
  - `notebooks/04p_fantrax_league_info.py`, `notebooks/04r_fantrax_roster_state.py`
  - `scripts/run_pipeline.py` (the hold)
  - the choice table and loader of [#548](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/548), the price list of [#554](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/554)
  - the after-rollover check (`ops.review_check`)

## Context

- **Nothing in the repo moves a contract at a season boundary.** The planner found the gap while ruling #549's Q1 ([#553](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/553)). Ben chose to grill it on 2026-11-14.
- **The contract year lives only in the `contract_id` label.** `dim_contract` has a `contract_year` and `total_years` per label and no "next" column. `02d` and `02e` look the year up; nothing counts it forward. ADR-0019 says the `contract_year` clock is unbuilt.
- **Contracts are observed.** `04r` reads `contract.name` from `getTeamRosters` (ADR-0019 decision 4). Fantrax does not move contracts by itself: the commissioners relabel. 48 players past 20 games were still on `Minor` ([#116](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/116)).
- **The pipeline is pinned to season one.** `02d` builds `SEASON_ID` from `CFG.draft_year`. `etl_cap.roster_season` raises unless the roster holds one season. `dim_scoring_period` holds 2026-27 only. `04a`'s `snapshot_season` is 2026.
- **Season spans.** `dim_season` runs Mar 1 to the end of February (2026-27, 2027-28, 2028-29).
- **Dead money already carries.** `02f` charges a dropped `1st` its 2nd-year 40% in the next season. `fact_team_cap` has a next-season row.
- **What the data holds.** No `2nd` to `6th`, `Tag` or `X` contract exists yet. Season one holds `1st`, `Minor` and `FA` only.
- **A seed error.** `dim_contract`'s `X` row has `cap_hit_pct` 0.5. The bylaws penalty table says `X` is 0% and non-guaranteed. The contract step ([#559](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/559)) fixes the seed to the bylaws.

## Decision

These are decisions 1 to 10 of map #557, in the map's order.

1. **Who sets next season's contracts: the commissioners relabel in Fantrax, which stays the record** (ADR-0019 decision 4 is kept). The repo works out each rostered copy's expected 2027-28 label, from the bylaws ladder and the keep choices, as a checklist for the commissioners. After rollover it reads Fantrax and files each mismatch as a check.
2. **Scope: the 2027 boundary only.**
   - `1st` becomes `2nd` at the same salary;
   - a `Minor` stays `Minor` while eligible;
   - a kept FA becomes `X`;
   - an unkept rostered FA returns to the pool.

   This ADR records the whole bylaws ladder (below). A 2028 ticket builds `2nd` to `3rd` / `X`, the extensions and tags after the 2027 Year-2 deadline.
3. **A kept FA's 2027 salary** is the generated value locked at the 2026-11-12 pull. Correction of round 2: the source is Ben's hand Players export of 2026-11-12, **not** `fact_fantrax_adp`. Its 2026-11-12 capture matches the export on only 1,070 of 1,982 joined players, and holds $2M for 1,593 of them where the export holds $2M for 1,123. The grid pull does not carry the generated value; only the hand export does. The export's Salary is the generated value for every player, rostered or not (it equals the roster salary on only 9 of 305 and 15 of 307 `1st` contracts, per [#552](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/552)).
4. **The season boundary is Mar 1** (`dim_season`). A move between period 17 and Mar 1 belongs to 2026-27.
5. **Keep choices enter the repo through a tracked loader into the choice table #548 defines.** So #548's ADR lands before Mar 1, 2027. Claude runs the loader on Ben's word. It also stores each keep's locked value.
6. **An overdue Minor's expected 2027 label is `2nd`** (Ben's rule 3: the season the player passed game 20 is year 1). This applies to a copy that still shows `Minor` in Fantrax at the end of 2026-27 whose player played game 21 during 2026-27. That season was year 1, whether or not the commissioners relabelled the copy to `1st` in time, and whether or not a Scoring Period was left to do it in. A player whose game 21 is the season's last game is also expected on `2nd`.
   - "Passed game 20" uses the same test as the Minor to `1st` list of [#545](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/545): a copy on `Minor` whose player is not on the newest eligibility list the pipeline reads. Today that is Fantrax's list (ADR-0019 decision 1, as amended 2026-11-12). The switch of that read to the nflverse count is a question for Ben, and this decision follows whatever it settles. This ADR picks no source of its own; the brief of #559 names the source in force when it is written.
7. **Unkept rostered FAs are released by the commissioners in Fantrax between period 17 and Mar 1.** Each release is a 2026-27 FA drop, which costs 0%. The check flags any still on 2027-28's first roster.
8. **Locked values ([#554](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/554)):**
   - **8.2:** one pull a year, right after the commissioners run Recalculate Salaries after the trade deadline, before the re-sign deadline. The pull's date is recorded with its values.
   - **8.3:** Ben's hand Players export is the source, loaded by a tracked script. No login code and no Claude fetch. One export covers both conferences, because the value is player-level.
   - **8.4** (also #552 item 4, recorded at #552 issuecomment-6883220695): the pull is the price list. A player added after the pull carries the value he showed in that pull, so the repo keeps the whole export. Ben's note: the new salary takes effect next year, and the current season finishes with the salary held at re-sign time.
9. **The commissioners get a one-off xlsx per conference before each rollover,** listing each rostered copy's expected next-season label and salary. It is separate from [#545](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/545). The repo also uses the same expected labels for the after-rollover check.
10. **If Fantrax is renewed to 2027-28 before Mar 1,** the Fantrax chain's publish holds and a check is filed until Mar 1, so no table mixes the two seasons. (How this is built, and the late case, are in [How the pipeline reads a season](#how-the-pipeline-reads-a-season).)

**Settled by the ADRs, not asked.** The after-rollover check files each mismatch to `ops.review_check` and never blocks the run (ADR-0019 decision 4's pattern).

## The bylaws contract ladder

Quoted from [`docs/league/BYLAWS-2026-27.md`](../league/BYLAWS-2026-27.md), by section. The first four columns are the Contract Status and Penalty Table of section 12, row for row; the last column is what the bylaws say follows the status next season, with its section, and it quotes the table's own Notes cell where the row has one. A cell that says "not stated" means the bylaws text has no rule. The repo's `contract_id` is the status, except the table's `FranchiseTag`, which is `Tag` in `dim_contract`. `dim_contract` also holds a `Pick` id, which is not a bylaws status and has no row here.

| Status | Salary type | Cap hit penalty | Guaranteed | What follows it next season |
|---|---|---|---|---|
| `1st` | Fixed Salary | 50% Cap Hit Penalty | Guaranteed | `2nd`. 12.1: "3-year term. Base salary stays fixed for Years 1–3." |
| `2nd` | Fixed Salary | 40% Cap Hit Penalty | Guaranteed | `3rd` is the default step (12.1: the 3-year term); `X` as the other outcome is pending the 2028 grill (#560). Table note: "Re-valued post-deadline." 12.2: after the trade deadline in Year 2, "salaries for all Year 2 and (FA) players are updated based on production and projections"; 12.3: owners "decide to extend at the re-sign deadline"; 11.5.2: the extension price for Years 4–6 is generated by Fantrax's Recalculate Salaries. |
| `3rd` | Fixed Salary | 0% Cap Hit Penalty | Non-Guaranteed | End of the 3-year term. 12.3: a drafted player who is not re-signed "will remain on the team at their current salary through the end of Year 3 before entering the FA pool"; a re-signed player takes `4th`. 11.4.1: the Tag can be applied to an expiring contract "(end of Year 3 or Year 6)". |
| `4th` | New Value | 50% Cap Hit Penalty | Guaranteed | `5th`. Table note: "Extension period." |
| `5th` | New Value | 40% Cap Hit Penalty | Guaranteed | `6th`. Table note: "Extension period." |
| `6th` | New Value | 0% Cap Hit Penalty | Non-Guaranteed | Free agency. Table note: "Final year before UFA." 11.4.1: the Tag can be applied here too. |
| `FranchiseTag` (`Tag`) | New Salary | 50% Cap Hit Penalty | Guaranteed | One additional season (11.4). Table note: "Expiring contract." 11.4.1: "A player cannot be tagged more than two years in a row." |
| `X` | Fixed Salary | 0% Cap Hit Penalty | Non-Guaranteed | Table note: "Expiring contract." What follows `X` the season after is not stated, and is open for the 2028 grill (#560). The commissioners' wording of 2026-11-14 ([#116](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/116#issuecomment-6880314749)) says a kept FA becomes `X` the next year, which "may be franchise-tagged at year end". |
| `Minor` | Fixed Salary | 0% Cap Hit Penalty | Non-Guaranteed | Two moments. **Inside a season:** the copy stays `Minor` until the player hits 20 NFL games played, then "they graduate and must be moved to the Active/Reserve roster" or be released (3.4); the contract becomes `1st` in the next Scoring Period of that same season, and that season is year 1 (ADR-0019 amendment 2026-11-14, rule 3). **At the season boundary:** a copy whose player is still eligible at the season's end stays `Minor`; a copy that still shows `Minor` in Fantrax whose player played game 21 during the season that is ending is expected on `2nd` (decision 6). Table note: "Exempt from Cap." 3.3: Minor League slots are 100% exempt from the cap. |
| `FA` | League Minimum Salary 2 mil | 0% Cap Hit Penalty | Non-Guaranteed | Table note: "Set each year at the end of preseason." 12.5: the designation "ONLY resets if they finish an entire season in the Free Agent pool"; dropping and re-claiming mid-season does not reset it. 5.2: FA pickups "are treated as 2nd-year players at the re-sign deadline if they are offered a contract extension"; if the owner does not extend, "the player returns to the Free Agent pool at the conclusion of the season." |

The sections that sit around the table, quoted for the rules a row does not carry:

- **5.2 Mid-Season FA Extension.** As in the `FA` row.
- **5.3 The "Pure Free Agent" Exemption.** A player on the waiver wire with an "FA" designation "may be picked up and dropped freely", with "No Cap Penalties".
- **5.4 Contracted Player Waivers and Penalties.** A player under a fixed contract ("1st, 2nd, 3rd, 4th, 5th, or 6th-year designation") "remains tied to their specific financial terms regardless of their waiver status". Dropping one applies "the standard Cap Hit Penalties ... for the remainder of the guaranteed term". A new owner who claims him by waivers "inherits the full salary and the exact contract year status of that player. The contract does not 'reset' upon changing teams."
- **11.4 The Franchise Tag.** A bridge contract that keeps "an elite player for one additional season when a long-term extension isn't possible". Up to two tags a season (one more through the Reinvestment Tiers).
- **11.4.1 Eligibility.** Only expiring contracts (end of Year 3 or Year 6); not more than two years in a row.
- **11.4.2 Salary Calculation.** The GREATER of 120% of the previous year's salary and the average of the top 5 highest-paid players at the position in the league.
- **11.4.3 Guarantee and Penalty.** "Franchise Tags are 100% fully guaranteed. If a tagged player is dropped at any point, the team incurs a 50% Cap Hit penalty for the remainder of that season."
- **12.1 Entry Contracts.** 3-year term, base salary fixed for Years 1–3. "Undrafted rookies and unsigned free agents will be assigned a default salary of $2,000,000."
- **12.2 Re-Valuation Window (Year 2).** As in the `2nd` row.
- **12.3 Extension Decision.** As in the `2nd` and `3rd` rows.
- **12.4 Injury Clause.** "Injured players are re-evaluated once healthy (Jan). Decisions must be made regardless of injury severity."
- **12.5 Reset Rule.** As in the `FA` row.

**The bylaws text and decisions 2 and 3, side by side.** Decision 2 turns a kept FA into `X`, with decision 3's generated value as the 2027-28 salary. Section 5.2 reads as a kept FA being a 2nd-year player offered an extension, and 12.1 and the `FA` row set a $2 mil default. The planner's ruling on [#557](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/557#issuecomment-6885895208) settled it: decisions 2 and 3 stand. The commissioners' wording (relayed by Ben on 2026-11-14, [#116](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/116#issuecomment-6880314749)) is that a kept FA stays at $2M for the rest of 2026-27, then a new value applies and the player becomes an `X` (expiring) contract. So the $2M default holds for 2026-27, and the generated value is the 2027-28 salary. The bylaws' next edition (the #116 list) updates 5.2. What follows `X`, and whether a first-year `Tag` may be tagged again (11.4.1), are 2028 questions for #560.

## Built for 2027

Everything below is a child of map #557 and goes live by Mar 1, 2027. Nothing switches between 2026-12-03 and 2027-01-07.

- **[#548](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/548):** its ADR (its planned first PR) defines the choice table, and its loader takes Ben's 2026 FA keep handover (decision 5). It must land before Mar 1.
- **[#554](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/554):** the yearly price list, a table and a loader, with Ben's 2026-11-12 export loaded first (decision 8).
- **[#558](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/558):** season two in the pipeline. Five briefs, in the planner's order:
  1. this ADR;
  2. `02d` reads each leg's own season;
  3. the cap module across the rollover (the roster's season stays the anchor);
  4. `04p` and `04r` take a second season (test-first);
  5. the early-renewal hold (decision 10).
- **[#559](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/559):** the contract step: the expected labels (decisions 1, 2 and 6), the commissioners' xlsx (decision 9), the after-rollover check, and the `X` seed fix (`dim_contract` row `X` has `cap_hit_pct` 0.5; the bylaws say 0%). The `Minor` seed note still reads "becomes 1st the period after GP > 19"; the limit is 20 (ADR-0019 amendment 2026-11-14), so #559's seed edit corrects it too. It comes after #548, #554 and #558.
- **[#553](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/553):** the cross-season carry (bylaws 12.5): a contract held at the end of 2026-27 carries into a 2027-28 claim until the copy spends a whole season unrostered. It comes after #559. ADR-0019's amendment says `02d` carries a contract only within one season today.

## Waits for the 2028 grill

Not built for 2027, because no 2027 move reaches it:

- **#560, the 2028 ladder:**
  - `2nd` to `3rd` or `X`;
  - the Year 2 re-valuation and extension (12.2, 12.3, 11.5.2), after the 2027 Year-2 deadline;
  - `4th` to `6th`;
  - the Franchise Tag (11.4 to 11.4.3).

  The grill comes before the 2027 trade deadline.
- **[#561](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/561):** the 2027-28 ledger's new events: the rookie draft, the auction and cut day. The grill comes after 2026-12-03. `02d` knows none of these move kinds yet.

## How the pipeline reads a season

Three points, settled. None is open in this ADR.

1. **The season boundary is Mar 1, by `dim_season`.** A date's season is the `dim_season` span that holds it (decision 4). `02d` already stamps each leg's season from the `dim_season` spans, so the boundary is in place there. A move on 2027-02-28 belongs to 2026-27; a move on 2027-03-01 belongs to 2027-28.
2. **The early-renewal hold applies in both directions.** Decision 10 names the early renewal. Ben's ruling (the planner's check on #558, 2026-11-14, "Hold both ways (Recommended)") covers the late one too: whenever the season Fantrax reports differs from the `dim_season` season of the run date, the Fantrax Chain (`fantrax_core`) publishes nothing and files one check per run. The other Chains publish.
   - **Built as a runner step, not a Gate.** `scripts/run_pipeline.py` withholds the Chain: its tables go back to HEAD, and one Review row per run is filed to `ops.review_check`, naming the two seasons and no row value. A Gate would make `--check-only` fail for the whole hold, and so every PR's Green (a hold can last up to a month). Review checks never block (ADR-0008 amendment, decision 9; ADR-0019 decision 4).
   - **The hold ends by itself** on the first run whose date is in the season Fantrax reports.
3. **The roster's season is the anchor for every cap figure, never the calendar.** Ben's ruling of 2026-10-12 ([#206](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/206) part 1) stands, as decision 4 of [ADR-0016's #97 amendment](0016-roster-state-from-snapshot-ledger-is-provenance.md#amendment-2026-10-14-the-cap-module-the-current-roster-and-the-cap-table-97) records it: "This season is the roster table's `season`" in every cap figure, and `etl_cap.roster_season` stays the one source of it for `team_cap`, `02h` and the checks. The run date is used only by the hold.

Why the three fit: with the hold in both directions, the roster's season and the run date's season are equal on every run that publishes. They differ only during a hold, when the Fantrax Chain publishes nothing, so no cap figure is built from a roster of the other season.

`CFG.draft_year` stays the startup season, 2026, for good. `02d` uses it only for the startup draft; the 2027 rookie draft is the grill of #561. `04a`'s `snapshot_season` and `week1_thursday` stay outside #558; a separate ticket for the 2027 preseason is tied to [#523](https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/523).

## Alternatives considered

- **Derive next season's contracts in the ETL and write them as the truth.** Rejected: it gives two contract truths. Fantrax stays the record and the repo checks it (decision 1; ADR-0019 decision 4).
- **Build the whole ladder for 2027 (`2nd` to `6th`, extensions, tags).** Rejected: no 2027 move reaches those rows. The 2028 grill (#560) settles them against a season of data.
- **Take a kept FA's salary from `fact_fantrax_adp`.** Rejected: its 2026-11-12 capture matches Ben's export on 1,070 of 1,982 joined players (decision 3).
- **Re-pull the price list whenever a player is added.** Rejected: one pull a year is the price list, and a late addition carries the value he showed in it (decision 8.4).
- **Hold only in one direction (an early renewal).** Rejected by Ben: a late renewal would mix the two seasons the same way, so the hold is both ways.
- **Build the hold as a Gate on `fantrax_core`.** Rejected: it reuses the restore-from-HEAD path with no new runner code, but every `--check-only` would show a Gate failure for the whole hold, and so fail every PR's Green until Mar 1. A Review check never blocks.
- **Take the cap figures' season from the run date.** Rejected by Ben's ruling of 2026-10-12 (#206 part 1): the roster's season is the anchor.
- **Roll `CFG.draft_year` each year.** Rejected: the startup draft happens once.

## Consequences

- **This PR changes no behaviour.** It records the decisions and the ladder; the briefs of #558 and the children above build them.
- **Briefs 2 to 5 of #558 cite this ADR.** Brief 5's PR cites decision 10 and the hold's two directions.
- **A kept FA is missing from the next-season cap row until the labels roll.** The next-season row of `fact_team_cap` counts contracts with `contract_year < total_years`, plus `Minor` (ADR-0016's #97 amendment, decision 4). The `FA` row is year 1 of 1, so a kept FA's 2027-28 salary is not in that row before Mar 1. This ADR does not change the row's meaning. Whether keeps from the choice table (decision 5) count in it is left to the brief of #559, which comes after #548.
- **The `X` seed row is wrong until #559 lands.** `cap_hit_pct` 0.5 against the bylaws' 0%. No `X` contract exists in the data yet.
- **Mar 1, 2027 is the deadline for everything under Built for 2027,** and the early-renewal hold must be merged before Fantrax renews, which can be any day in February.
