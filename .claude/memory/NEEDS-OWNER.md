# NEEDS-OWNER — what is waiting on the owner

Every session appends here when it needs the owner (protocol in
`GOAL-RUN.md`). The `owner-queue` mod reads this file and shows it live, so
keep the format:

- two sections only, `## Decisions` and `## Actions`;
- one item per `### [ ] Title`;
- fields as `- Label: value`. Decisions carry Ticket, Context, Options,
  Recommended, Blocks, Raised. Actions carry Ticket, Steps, Context, Blocks,
  Raised;
- a Decision's choices are written `- Options: (a) ...; (b) ...` and
  `- Recommended: (a), because ...`. The pane shows one button per
  option;
- secrets are named, never written. No owner PII, no team names.

The owner answers by a button in the pane, or in chat. A button writes
`- Answer: ...` as the last field of the entry and sends the answer to
that session's chat. **No agent writes, edits or removes an `Answer:`
line.** A pane answer is the owner's wherever it lands: the session that
picks it up records it on the ticket, acts, and removes the entry (or
marks an Action `[x]` until the next state-back).

The pane reads the **main checkout's** copy of this file, from any
session or worktree. That copy is the queue; a worktree's copy is not
shown.

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

### [ ] Tighten the builders' file after the dry dispatch
- Ticket: #166
- Steps: 1. Move `builders.settings.json` from your user folder into the
  repository as `.claude/builders.settings.json`. 2. Apply section 3 of
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/166#issuecomment-6129778615 :
  three lines out of `allow`, six lines into `allow`, eleven lines into
  `deny`. 3. Commit it on a branch and open a PR; say "approved" and the
  manager merges it.
- Context: the dry dispatch of 2026-10-12 showed your user-level allow
  rules reach a builder (`python -c`, `gh api`, `gh issue`), so only a
  deny rule holds. You chose the two-key merge, so the builder loses
  `gh pr merge`.
- Blocks: the first real dispatch, #186.
- Raised: 2026-10-12, by the builder manager

### [ ] Create the managers' settings file
- Ticket: #166
- Steps: create `.claude/managers.settings.json` from the JSON block in
  section 4 of
  https://github.com/benjamininja/Python-PowerBI-DynastyFantasyFootball/issues/166#issuecomment-6129778615 ,
  in the same PR as the builders' file or its own.
- Context: it binds a manager started from the CLI. A manager in the
  desktop app reads your project and user settings instead; the entry
  below covers that case.
- Blocks: nothing today; the manager works through prompts until then.
- Raised: 2026-10-12, by the builder manager

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
