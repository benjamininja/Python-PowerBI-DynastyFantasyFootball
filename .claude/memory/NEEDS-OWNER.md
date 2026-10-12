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

### [ ] Try owner-queue 0.3.0 in a fresh session
- Ticket: #167
- Steps: 1. Start a new manager or planner session (or reload the mod).
  2. Run /owner; the footer should name the main checkout's
  `NEEDS-OWNER.md` and a "Last read" time. 3. Press Refresh. 4. Ask the
  manager for a scratch decision; open it, press an option; the row
  should move to "Answered, waiting for pickup" and the answer should
  arrive in chat. 5. Press "Change answer". 6. Tell the planner what did
  not work.
- Context: the tests cover the logic, but no agent can press a button in
  the live pane. The type-check (`tsc`) was not run: this machine has no
  Node. Mouse selection inside the pane is not something a mod can switch
  on; "Copy name" and "Copy all" replace the old Copy.
- Blocks: nothing; 0.2.0 behaviour is unchanged apart from the buttons.
- Raised: 2026-10-12, by the planner

### [ ] Remove two scratch worktrees of the upstream repo
- Ticket: #167
- Steps: in `C:\Users\benha\OneDrive\Documents\GitHub\skills-plugins-hooks-agents`
  run `git worktree list`, then `git worktree remove` on the two entries
  under `AppData\Local\Temp\claude` (folders `oq39` and `spha-wt`), then
  `git branch -D owner-queue-030`.
- Context: `oq39` is the planner's, made today to put 0.3.0 on upstream
  PR #39 without touching your checkout; it is clean and pushed.
  `spha-wt` is from an earlier session. The planner does not delete a
  worktree or branch without your yes.
- Blocks: nothing.
- Raised: 2026-10-12, by the planner

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

### [ ] Finish and commit the two settings files
- Ticket: #166, #186
- Steps: 1. In `.claude/builders.settings.json` add to `allow`:
  `"Bash(.venv/Scripts/python.exe scripts/compare_tables.py *)"` and
  `"Bash(.venv/Scripts/python.exe notebooks/02d_fact_roster_transactions.py --raw-dir *)"`.
  2. Optional, same file, add to `deny`:
  `"Edit(.claude/managers.settings.json)"` and
  `"Write(.claude/managers.settings.json)"`. 3. Optional, in
  `.claude/managers.settings.json` add to `deny`:
  `"Edit(.claude/agents/**)"` and `"Write(.claude/agents/**)"`. 4. Both
  files are still untracked: commit them on a branch and open a PR, or
  say "commit the settings files" and the manager does that part.
- Context: both files now match the text on #166. #186 is merged, so
  its two proof commands exist and need one rule each; without them a
  stage C builder parks at its first "tables identical" proof.
- Blocks: stage C's proofs. Not #97's start.
- Raised: 2026-10-12, by the builder manager

### [ ] Free the last leftover worktree folder
- Ticket: #164 (closeout)
- Steps: 1. Archive or close the idle session "Fix null overall_rank in
  04a in-season pulls"; it sits in `.claude/worktrees/brave-euclid-5d75b2`
  and Windows will not delete the folder while it does. 2. Delete that
  folder. 3. Run `git worktree prune` in the main checkout.
- Context: on your word the manager deleted the other three leftover
  folders on 2026-10-12. `git worktree prune` is refused to the manager
  (it writes inside `.git`), so five stale entries stay under
  `.git/worktrees/` until you run it.
- Blocks: nothing.
- Raised: 2026-10-12, by the builder manager

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
