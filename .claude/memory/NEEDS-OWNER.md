# NEEDS-OWNER — what is waiting on the owner

Every session appends here when it needs the owner (protocol in
`GOAL-RUN.md`). The `owner-queue` mod reads this file and shows it live, so
keep the format:

- two sections only, `## Decisions` and `## Actions`;
- one item per `### [ ] Title`;
- fields as `- Label: value`. Decisions carry Ticket, Context, Options,
  Recommended, Blocks, Raised. Actions carry Ticket, Steps, Context, Blocks,
  Raised;
- secrets are named, never written. No owner PII, no team names.

The owner answers in chat. The session then records the answer where it
belongs and deletes the entry (or marks it `[x]` until the next state-back).

## Decisions

### [ ] #77: three whole-number columns of fact_trade_log through the seam
- Ticket: #77 (task, map #69), phase 5. Every other write of phase 5 is
  built; this one write in `02d` is left as it was.
- Context: `draft_year`, `draft_round` and `pick_in_round` of
  `fact_trade_log` are stored in the parquet file as whole numbers (int64)
  with gaps. pandas reads a column like that back as float64, so the
  registry says `float64`. The seam casts a batch to the registry before it
  writes, so through the seam the file would hold decimals (double) in those
  three columns. Measured: old code against new code on the same inputs,
  the parquet type changes int64 → double for exactly these three columns;
  rows and values are the same. No other published table has a column in
  this state (checked all 32). The file had int64 there before #109 too.
  Power BI reads the parquet type, so it would see a decimal column.
- Options: (a) accept double until cutover, when ADR-0018 makes them
  `integer`; (b) declare the three columns `Int64` in the registry now and
  have `02d` write them so: the file keeps whole numbers, a pandas read
  gives `Int64` instead of `float64`, and the published file is rewritten
  once; (c) leave this one write outside the seam until cutover, with one
  named exception in the static guard test.
- Recommended: (b). It is where ADR-0018 already points (nullable integers
  become `integer`), the parquet type does not change, and the guard test
  needs no exception.
- Blocks: #77 phase 6 (the static guard test cannot pass while this write
  sits outside the seam with no decision). Does not block #149 or #86.
- Raised: 2026-10-12, stage B goal run

### [ ] #77: fact_fantasy_teams through the seam stops on a rostered player with no gsis_id
- Ticket: #77 (task, map #69), phase 5; touches #97, which rewrites `02e`.
  The `02e` write is left as it was.
- Context: the registry grain of `fact_fantasy_teams` is
  `(team_key, gsis_id)`, and the seam refuses a null or repeated grain key.
  `02d` can mint an asset with no `gsis_id` (an unsigned prospect, or a
  Fantrax player the crosswalk does not know yet), and the ledger accepts
  it. Through the seam, one such rostered player would stop the scheduled
  `02e` run; today the file is written with the row. Current data is clean
  (1,103 active rows, 0 null `gsis_id`, 0 repeated keys), so this would
  first show after a rookie draft. Found by the `cap-ledger-auditor`.
- Options: (a) it is a wanted hard stop: move the write to the seam as is;
  (b) change the grain so such a row is legal (for example key on the
  asset, or allow `player_key` where `gsis_id` is null), in #97's rewrite
  of `02e`; (c) leave this one write outside the seam until #97 lands, with
  one named exception in the static guard test.
- Recommended: (c) now and (b) inside #97. A stop on every rookie draft is
  a cost with no gain, and the grain is #97's to settle.
- Blocks: #77 phase 6 (the static guard test). Does not block #149 or #86.
- Raised: 2026-10-12, stage B goal run

## Actions

### [ ] Fresh 04t capture before #97 PR 1
- Ticket: #97 (task, map #70)
- Steps: run `04t` once after a lineup lock has passed with at least one
  claim or drop made after it. Tell the session it is done.
- Context: #97 PR 1 starts by measuring whether the public current-roster
  reply shows a post-lock move. It needs a ledger that holds such a move.
- Blocks: #97 PR 1, the only thing it still waits on (#96 closed
  2026-10-11). Through #97 it also blocks the last part of #110, the
  `roster_status` → `roster_slot` rename (the #97 grill put #97 first).
  Both now open stage C (2026-10-12), so #108's first migration waits
  on this capture too.
- Note 2026-10-11 (goal A): the capture of 2026-10-11 10:02 was taken on a
  Sunday morning, before period 5's lineup lock, so the session does not
  count it as this capture. Say so in chat if it should.
- Note 2026-10-11 (evening): the owner approved the session to run `04t`,
  but lines 34 and 39 of the project `.claude/settings.json` (deny rules
  for `04t_fantrax_transaction_history.py`) still block it. Either run
  `python notebooks/04t_fantrax_transaction_history.py` from the repo
  root, or delete those two lines and say so.
- Note 2026-10-11 (later): the owner placed a claim with a conditional
  drop after period 5's lock. Fantrax shows it "waiting for resolution",
  so it is not in the history until the waiver run executes it. The owner
  says that is Thursday morning, 2026-10-15. Run `04t` after that. The same
  row is the test for #68: it should carry a bid if the bid rule is right.
- Raised: 2026-10-11, #97 grill

### [ ] Fire the first Fantrax runner login (later)
- Ticket: #92, #93
- Steps: once stage D has merged the spike workflow, run it with
  `workflow_dispatch` and report the result in chat.
- Context: checkpoint 1. If the runner is blocked, authed captures stay on
  the home PC (ADR-0015).
- Blocks: enabling the crons.
- Raised: 2026-10-11, goal-run setup

### [ ] Cutover (later)
- Ticket: #93
- Steps: enable the crons, let the parallel week run, give the cutover go
  in chat, unregister the PC task.
- Context: checkpoint 2, after stages C and D.
- Blocks: closing #93 and maps #69, #70, #71.
- Raised: 2026-10-11, goal-run setup
