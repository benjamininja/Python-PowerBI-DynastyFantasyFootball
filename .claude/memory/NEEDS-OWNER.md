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

This file is the one place for what waits on the owner, across every
session (owner, 2026-10-12). A session that may not write it (the
planner) sends the builder manager a ready entry. Each entry says who
raised it and when, and each answer is recorded on its ticket, so it
can be traced.

## Decisions

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
  fence. No agent may write the file. You accepted the two rules
  for the Fantrax public API scripts (`04p`, `04u`) on 2026-10-12.
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

### [ ] Store the database secret for `migrate.yml` (later)
- Ticket: #108 (task, map #69)
- Steps: when #108's PR names the Actions secret it reads, store that
  secret in the repository's `main`-only environment. Then say so in
  chat.
- Context: you ruled on 2026-10-12 that `migrate.yml` is live from the
  day #108 merges. It applies the migrations to the real project on
  merge, so the secret must be there first. No agent reads or writes a
  secret.
- Blocks: merging #108.
- Raised: 2026-10-12, by the builder manager

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
