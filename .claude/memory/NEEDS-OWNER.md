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

### [ ] May a builder call Fantrax's public API?
- Ticket: #166
- Context: stage B ran `04p` and `04u`, which call Fantrax's public API
  with no login. Two of the six rules in the #166 addendum allow them.
- Options: (a) allow both exact commands; (b) leave both out, and a
  builder that needs them parks.
- Recommended: (a). They are exact commands with no wildcard and cannot
  reach a login step.
- Blocks: nothing until a stage C builder needs a refresh.
- Raised: 2026-10-12, #166 addendum

### [ ] How does an item from the planner or the manager reach this queue?
- Ticket: #166, #167
- Context: on 2026-10-12 four by-hand items from the #166 grilling sat in
  chat only. The planner may not write `.claude/memory/*`; and each
  worktree has its own copy of this file, so the pane shows only the copy
  of the folder its session runs in.
- Options: (a) rule only: any session that leaves something for the owner
  sends the manager a ready entry, and the manager writes it (the builder
  writes it while one runs); (b) rule (a), and the `owner-queue` mod reads
  the main checkout's copy from any worktree; (c) the queue moves out of
  the repo to one file per project under the user folder, so every
  session reads and writes the same one.
- Recommended: (b). The rule closes today's gap now; the mod change makes
  the pane the same in every session. It is an upstream change for #167.
- Blocks: nothing; until settled the planner hands entries to the
  manager, as now.
- Raised: 2026-10-12, by the owner

### [ ] Is `migrate.yml` live from the day #108 merges?
- Ticket: #108 (task, map #69)
- Context: ADR-0018 says `migrate.yml` applies migrations on merge. #108
  lands it in stage C; cutover comes later. #135's backfill needs the
  schema on the real project before cutover, and no agent may apply a
  migration through the connector or fire a workflow.
- Options: (a) live on merge from #108 on, with the database secret
  stored by you first; (b) merged switched off behind a repo variable,
  like the crons, and switched on at cutover.
- Recommended: (a). It is the only way the schema reaches the real
  project without an agent writing to it. With (b) the backfill and the
  restore drill wait for cutover.
- Blocks: #108's workflow, and the planner's README and CONTRIBUTING rows
  for `supabase/`.
- Raised: 2026-10-12, by the builder manager

### [ ] Delete the local branch `feat/77-seam-phase5`?
- Ticket: #77 (closed)
- Context: left by the stage B builder. It holds two wip commits that
  were never proven green and are not on `main`; phase 5 itself merged
  from another branch. The manager may not delete unmerged work.
- Options: (a) delete it: `git branch -D feat/77-seam-phase5`, by your
  hand or on your word; (b) keep it.
- Recommended: (a). #77 is closed and the guard test passes on `main`.
- Blocks: nothing.
- Raised: 2026-10-12, stage B closeout

## Actions

### [ ] Fresh 04t capture, after Thursday 2026-10-15
- Ticket: #97 (task, map #70)
- Steps: once the waiver run of 2026-10-15 has executed your claim and its
  conditional drop, run `python notebooks/04t_fantrax_transaction_history.py`
  from the repo root. Then say "04t done" in chat.
- Context: #97 PR 1 needs a ledger that holds a move made after a lineup
  lock. A session cannot run `04t` (deny rules in `.claude/settings.json`).
  The same row tests the bid rule of #68.
- Blocks: #97 PR 1, and through it the #110 rename and #108's first
  migration: all of stage C.
- Raised: 2026-10-11, #97 grill

### [ ] Merge PR #185, then PR #184
- Ticket: #166
- Steps: read and merge
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/185
  (`GOAL-RUN.md`: CLI dispatch, tiers, the wider relay). Then merge
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/pull/184
  (the three role files).
- Context: both are rule changes only you merge. #184 names things #185
  defines, so #185 goes first. Your merge of #185 is your confirmation of
  the ten decisions at
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/166#issuecomment-6129005307 .
- Blocks: every dispatch; closing #166.
- Raised: 2026-10-12, #166 grill

### [ ] Create the builders' settings file
- Ticket: #166
- Steps: 1. Create `.claude/builders.settings.json`. 2. Paste the one JSON
  block from
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/166#issuecomment-6129035556
  (heading "Proposal 1 of 2"). 3. Add to its `allow` list the lines you
  accept from the block under "Add to allow" in
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/166#issuecomment-6129147381 .
  4. Commit it on a branch, open a PR, merge it.
- Context: a dispatched builder runs in `dontAsk`; this list is its whole
  fence. No agent may write the file.
- Blocks: every dispatch, so #186 and stage C.
- Raised: 2026-10-12, #166 grill

### [ ] Add the builder manager's commands to your settings
- Ticket: #166
- Steps: add the allow rules in the table under heading "E. The manager's
  own commands" in
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/166#issuecomment-6129036173
  to the settings the manager session reads. Narrow `Bash(gh pr merge *)`
  to `Bash(gh pr merge * --squash --delete-branch)`. Leave `git branch -D`,
  `git worktree remove --force` and `claude rm` to a prompt.
- Context: dispatch, the `.venv` step and closeout need them.
  `settings.local.json` is copied into builder worktrees, so a rule there
  reaches builders too.
- Blocks: the dry dispatch.
- Raised: 2026-10-12, #166 grill

### [ ] Clear the leftover worktree folders
- Ticket: #164 (closeout)
- Steps: 1. Delete the folder `.claude/worktrees/vigorous-euclid-99dea6`
  (the stage B builder's; git no longer lists it). 2. Run
  `git worktree prune` in the main checkout. 3. If you want, also delete
  the older folders `agent-a11df4cfac048959e`, `brave-euclid-5d75b2` and
  `elegant-dirac-4c3411` beside it. Leave `metadata-principles`; it is a
  live worktree.
- Context: the manager's `git worktree remove` half-failed on a Windows
  file lock and was not forced. What is left is a `.venv` and ignored,
  regenerable output; no tracked file is uncommitted there.
- Blocks: nothing.
- Raised: 2026-10-12, stage B closeout

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
