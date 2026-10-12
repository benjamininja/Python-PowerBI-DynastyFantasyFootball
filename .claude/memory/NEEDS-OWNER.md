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
