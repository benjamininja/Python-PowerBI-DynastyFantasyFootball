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

### [ ] #109: how pick legs inside one trade are resolved
- Ticket: #109 (task, map #69). PR open, built and green locally; parked on
  this one question from the `cap-ledger-auditor`.
- Context: a trade row names a future pick by year and round only. `02d`
  replays ownership leg by leg, in order: a leg moves the one pick of that
  year and round its sender holds at that moment; if the sender holds
  several, the row's owner hint (a team name) picks one; otherwise the leg
  goes to review and stays out of `fact_trade_log`. On today's data all 95
  pick legs resolve (90 by slot, 5 future), 0 in review, and the replay
  ends on Fantrax's owner for 280 of 280 future picks. All 5 future legs
  carry a hint. The open case is not in the data: two teams swap picks of
  the same round in one trade and a hint is missing or names a renamed
  team. In sequence, the second sender then holds two picks and the leg
  goes to review.
- Options: (a) keep it: in sequence, hint as tie-break, else review;
  (b) resolve every leg of one trade against the holdings before the
  trade, so a same-round swap needs no hint (a pick passing through two
  teams inside one trade then goes to review instead).
- Recommended: (a). Nothing is silently wrong under it, the hint has been
  present on every future leg so far, and a leg in review is one line to
  look at.
- Blocks: merging the #109 PR, and #108's first migration (it needs
  `fact_trade_log` keyed). Does not block #77, #149 or #86.
- Also yours to see in the PR (the agent's calls, no answer needed unless
  you disagree): `pick_owner_hint` is no longer written; all 1,260 picks
  are minted; every leg of an asset that moves twice inside one trade goes
  to review, because the key `(transaction_id, asset_id)` cannot hold both;
  `04u` stays manual.
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
